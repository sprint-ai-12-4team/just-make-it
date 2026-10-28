"""생성 작업 큐, Fallback 라우팅, 타임아웃, 생성 로그.

구조
- 기본(primary) 생성기 작업은 대기열 하나에 넣고 워커 `primary_concurrency`개가 처리한다.
  로컬 GPU 모델이면 1개(RAM 16GB 보호), API 모델이면 2~3개로 늘린다.
- 블로킹 생성 호출은 `asyncio.to_thread`로 실행해 FastAPI 이벤트 루프를 막지 않는다.
- Fallback·프리미엄 작업은 대기열을 거치지 않고 바로 실행한다 (동시 EXTRA_CONCURRENCY개).

경로 선택
1. 프리미엄: 유저가 고품질 모드를 골랐고 프리미엄 생성기가 설정된 경우
2. Fallback(대기): 새 작업의 예상 완료 시간 > max_wait_seconds
3. Fallback(미준비): 기본 생성기 준비 실패 (모델 이름 오류, API 키 누락 등)
4. Fallback(장애): 기본 생성기가 재시도 후에도 실패하거나 제한 시간을 넘김
Fallback·프리미엄은 하루 extra_daily_limit까지만 쓰고, 넘으면 기본 대기열로 보낸다.

타임아웃
- 생성 1건은 generation_timeout_seconds 안에 끝나야 한다. 넘으면 재시도하지 않고
  (같은 호출이 또 밀릴 가능성이 높고 비용만 늘어남) Fallback 또는 실패로 처리한다.
- 파이썬은 실행 중인 스레드를 밖에서 멈출 수 없어서, 작업마다 core에 Deadline을 걸어
  모델 호출이 스스로 멈추게 한다 (core/deadline.py). 시간이 지나거나 취소되면
  OpenAI 호출은 남은 시간에서 끊기고(재시도 없음), klein은 다음 단계에서 멈추고,
  core 안의 폴백(klein→flare, Gemma→luna)도 새로 시작하지 않는다.
- /generate가 응답을 기다리다 포기하면(generate_wait_seconds) 작업도 취소한다.
  프론트는 /generate 결과를 폴링하지 않으므로 끝까지 만들어도 아무도 못 보고 비용만 든다.

기록
- 접수할 때 `generations` 행(processing)을 만들고, 끝나면 성공·실패로 바꾼다 (service/db.py).
  행 id가 곧 작업 id이자 응답 id다.
- 작업이 끝날 때마다 `just_make_it.serving.generations` 로거에도 JSON 한 줄을 남긴다.
  필드 이름은 `generations` 테이블 컬럼과 같다. DB에 없는 `fallback_reason`을 함께 남긴다.
"""

import asyncio
import json
import logging
import math
import time
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta, timezone

from just_make_it.core.deadline import Deadline, use_deadline

from .generators import GeneratorError, ImageGenerator
from .records import GenerationRecords
from .schemas import (
    GenerationOutput,
    GenerationSpec,
    JobState,
    Route,
    Source,
)
from .settings import ServingSettings

logger = logging.getLogger(__name__)
generation_log = logging.getLogger("just_make_it.serving.generations")

KST = timezone(timedelta(hours=9))  # 한국은 서머타임이 없어 고정 오프셋으로 충분
EXTRA_CONCURRENCY = 2

ERROR_GENERIC = "잠시 후 다시 시도해 주세요."
ERROR_INPUT = "입력 내용으로 이미지를 만들 수 없어요. 내용을 확인해 주세요."
# core Deadline은 서빙 타임아웃보다 조금 늦게 끝나게 둔다. 서빙이 먼저 시간 초과를 알아채고
# (재시도 없이 Fallback·실패 처리) 취소 신호를 보내야, core가 먼저 끊겨 "일반 실패"로
# 보이면서 다시 시도되는 일이 없다
DEADLINE_GRACE_SECONDS = 2.0


def _run_within(deadline: Deadline, fn, *args):
    with use_deadline(deadline):
        return fn(*args)


async def run_with_deadline(fn, *args, timeout: float):
    """블로킹 함수를 스레드에서 돌리고, timeout이 지나면 core 작업도 멈추게 한다.

    Raises:
        TimeoutError: timeout 안에 안 끝났을 때 (core에는 취소 신호를 보냄)
    """
    deadline = Deadline(timeout + DEADLINE_GRACE_SECONDS)
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_run_within, deadline, fn, *args), timeout=timeout
        )
    except (TimeoutError, asyncio.CancelledError):
        deadline.cancel()
        raise


class QueueFullError(RuntimeError):
    """대기열이 가득 찼을 때."""


class DailyLimitError(RuntimeError):
    """하루 생성 한도에 도달했을 때."""


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _ms(seconds: float | None) -> int | None:
    return None if seconds is None else int(round(seconds * 1000))


@dataclass
class Job:
    id: str
    spec: GenerationSpec
    route: Route
    client_id: str = "anonymous"
    parent_id: str | None = None
    # 상세페이지 섹션 이미지면 페이지 id와 칸 번호
    detail_page_id: str | None = None
    section_index: int | None = None
    created_at: str = field(default_factory=_now_iso)
    state: JobState = JobState.QUEUED
    submitted_mono: float = field(default_factory=time.monotonic)
    started_mono: float | None = None
    finished_mono: float | None = None
    # 성공 시 DB가 돌려준 응답 (api_spec 조회 응답 모양)
    result: dict | None = None
    source: Source | None = None
    model: str | None = None
    message: str | None = None
    width: int | None = None
    height: int | None = None
    prompt: str | None = None
    error: str | None = None
    error_internal: str | None = None
    input_error: bool = False
    fallback_reason: str | None = None
    cost_usd: float | None = None
    # core가 잰 단계별 시간: 문구(영어 묘사·텍스트 짧게), 그림 모델
    text_ms: int | None = None
    image_ms: int | None = None
    # 지금 돌고 있는 core 호출의 Deadline. cancel()이 취소 신호를 보낸다
    deadline: Deadline | None = None
    cancelled: bool = False
    done: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def is_finished(self) -> bool:
        return self.state in (JobState.SUCCEEDED, JobState.FAILED)

    @property
    def queue_ms(self) -> int | None:
        if self.started_mono is None:
            return None
        return _ms(self.started_mono - self.submitted_mono)

    @property
    def run_ms(self) -> int | None:
        """생성기 호출 전체(문구 + 그림 + 글자 얹기) 시간."""
        if self.started_mono is None or self.finished_mono is None:
            return None
        return _ms(self.finished_mono - self.started_mono)


class _DailyCounter:
    """Asia/Seoul 자정마다 초기화되는 카운터. limit 0이면 무제한."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._day: date = self._today()
        self._count = 0

    @staticmethod
    def _today() -> date:
        return datetime.now(KST).date()

    @property
    def count(self) -> int:
        self._roll()
        return self._count

    def take(self) -> bool:
        """한도 안이면 1 차감하고 True."""
        self._roll()
        if self.limit and self._count >= self.limit:
            return False
        self._count += 1
        return True

    def _roll(self) -> None:
        today = self._today()
        if today != self._day:
            self._day, self._count = today, 0


class _DailyBudget:
    """Asia/Seoul 자정마다 초기화되는 OpenAI 금액 합계. limit 0이면 끔."""

    def __init__(self, limit_usd: float) -> None:
        self.limit = limit_usd
        self._day: date = _DailyCounter._today()
        self._spent = 0.0

    @property
    def spent(self) -> float:
        self._roll()
        return self._spent

    @property
    def exceeded(self) -> bool:
        return bool(self.limit) and self.spent >= self.limit

    def add(self, usd: float | None) -> None:
        self._roll()
        self._spent += usd or 0.0

    def set(self, usd: float) -> None:
        self._roll()
        self._spent = usd

    def _roll(self) -> None:
        today = _DailyCounter._today()
        if today != self._day:
            self._day, self._spent = today, 0.0


class QueueManager:
    """작업 접수, 경로 선택, 실행, 상태 조회를 담당한다."""

    def __init__(
        self,
        settings: ServingSettings,
        primary: ImageGenerator,
        fallback: ImageGenerator | None,
        premium: ImageGenerator | None,
        records: GenerationRecords,
    ) -> None:
        self.settings = settings
        self.primary = primary
        self.fallback = fallback
        self.premium = premium
        self.records = records

        self.concurrency = max(1, settings.primary_concurrency)
        self.seconds_per_job = settings.seconds_per_job_init
        # Fallback·프리미엄(OpenAI) 1건 시간. 진행 상황의 남은 시간 추정에만 쓴다
        self.extra_seconds_per_job = settings.seconds_per_job_init
        self.jobs_today = _DailyCounter(settings.daily_job_limit)
        self.extra_today = _DailyCounter(settings.extra_daily_limit)
        # OpenAI 금액 회로차단기 (V2). 열리면 Fallback·프리미엄·core 내부 폴백을 막는다
        self.budget = _DailyBudget(settings.openai_daily_budget_usd)
        self._core_fallback_default: bool | None = None

        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._running: set[str] = set()
        # 아직 안 끝난 작업 (진행 상황 조회용). 끝나면 지운다 (결과는 DB에)
        self._active: dict[str, Job] = {}
        self._workers: list[asyncio.Task] = []
        self._loading: asyncio.Task | None = None
        self._extra_tasks: set[asyncio.Task] = set()
        self._extra_slots = asyncio.Semaphore(EXTRA_CONCURRENCY)

    # ------------------------------------------------------------------ 수명 주기
    async def start(self) -> None:
        # 오늘 쓴 OpenAI 금액을 DB에서 이어받는다 (재시작해도 상한이 풀리지 않게)
        try:
            self.budget.set(await asyncio.to_thread(self.records.cost_today))
        except Exception:
            logger.exception("오늘 OpenAI 금액을 읽지 못함 (0으로 시작)")
        self._sync_core_fallback()
        # API 모델(Fallback·프리미엄)은 금방 준비되니 먼저 기다리고,
        # 로컬 모델(klein)은 GPU에 올리는 데 오래 걸려서 설정에 따라 뒤에서 불러온다.
        # 다 불러오기 전에 들어온 기본 요청은 primary_not_ready로 Fallback 처리된다.
        for generator in (self.fallback, self.premium):
            if generator is not None:
                await self._load(generator)
        if self.settings.load_models_in_background:
            self._loading = asyncio.create_task(self._load(self.primary))
        else:
            await self._load(self.primary)
        self._workers = [
            asyncio.create_task(self._worker_loop(), name=f"primary-worker-{i}")
            for i in range(self.concurrency)
        ]
        logger.info(
            "QueueManager 시작 (primary=%s ready=%s, workers=%d, fallback=%s, "
            "premium=%s, timeout=%.0fs)",
            self.primary.name,
            self.primary.is_ready,
            self.concurrency,
            self.fallback.name if self.fallback else None,
            self.premium.name if self.premium else None,
            self.settings.generation_timeout_seconds,
        )

    async def _load(self, generator: ImageGenerator) -> None:
        try:
            await asyncio.to_thread(generator.load)
        except Exception:  # 준비 실패해도 서버는 뜨고 다른 경로로 처리
            logger.exception("생성기 준비 실패: %s", generator.name)
        if generator is self.primary:
            logger.info(
                "기본 생성기 준비 %s: %s",
                "완료" if generator.is_ready else "실패",
                generator.name,
            )

    @property
    def models_loading(self) -> bool:
        return self._loading is not None and not self._loading.done()

    async def stop(self) -> None:
        tasks = [*self._workers, *self._extra_tasks]
        if self.models_loading:
            tasks.append(self._loading)  # type: ignore[arg-type]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------------------------------------------------------ 접수
    async def submit(
        self,
        spec: GenerationSpec,
        *,
        premium: bool = False,
        client_id: str = "anonymous",
        parent_id: str | None = None,
        detail_page_id: str | None = None,
        section_index: int | None = None,
        wait_fallback: bool = True,
    ) -> Job:
        """작업을 접수한다.

        wait_fallback=False면 대기가 길어도 OpenAI로 넘기지 않고 기다린다 (상세페이지처럼
        결과를 폴링하는 작업. 섹션 5칸이 한꺼번에 들어와 대기가 길어 보여도 비용을 아낀다).
        준비 안 됨·장애 Fallback은 그대로 적용된다.
        """
        self._sync_core_fallback()
        # 금액 상한을 넘으면 "더 정교하게"도 로컬 대기열로 (extra 한도를 넘은 경우와 같음)
        goes_premium = premium and self._usable(self.premium) and self.api_allowed
        if (
            not goes_premium
            and self._queue.qsize() >= self.settings.queue_max_size
            and self._fallback_reason(wait_fallback) is None
        ):
            raise QueueFullError("대기열이 가득 찼습니다.")
        limit = self.settings.client_daily_limit
        if (
            limit
            and await asyncio.to_thread(self.records.count_today, client_id) >= limit
        ):
            raise DailyLimitError("사용자 하루 생성 한도에 도달했습니다.")
        if not self.jobs_today.take():
            raise DailyLimitError("하루 생성 한도에 도달했습니다.")

        # 조금 수정하기(parent_id + 수정 칩)는 원본의 시드로 구도를 유지한다.
        # 다시 만들기(칩 없음)는 새 그림을 원하는 것이라 시드를 넘기지 않는다
        if parent_id and spec.adjustments and spec.seed is None:
            seed = await asyncio.to_thread(self.records.seed_of, parent_id)
            if seed is not None:
                spec = replace(spec, seed=seed)

        # 다시 만들기에서 사진을 다시 보내지 않으면 원본 결과의 참고 사진을 이어서 쓴다
        if spec.reference_image is None and parent_id:
            reference = await asyncio.to_thread(self.records.load_reference, parent_id)
            if reference is not None:
                spec = replace(spec, reference_image=reference)

        async def new_job(
            route: Route, generator: ImageGenerator, reason: str | None = None
        ) -> Job:
            gid = await asyncio.to_thread(
                self.records.start,
                client_id=client_id,
                spec=spec,
                parent_id=parent_id,
                backend=generator.source,
                model=generator.name,
                detail_page_id=detail_page_id,
                section_index=section_index,
            )
            if spec.reference_image is not None:
                await asyncio.to_thread(
                    self.records.save_reference, gid, spec.reference_image
                )
            job = Job(
                id=gid,
                spec=spec,
                route=route,
                client_id=client_id,
                parent_id=parent_id,
                detail_page_id=detail_page_id,
                section_index=section_index,
                fallback_reason=reason,
            )
            self._active[gid] = job
            return job

        if goes_premium and self.extra_today.take():
            job = await new_job("premium", self.premium)  # type: ignore[arg-type]
            self._spawn_extra(job, self.premium)  # type: ignore[arg-type]
            return job

        reason = self._fallback_reason(wait_fallback)
        if reason and self.extra_today.take():
            job = await new_job("fallback", self.fallback, reason)  # type: ignore[arg-type]
            logger.info("Fallback 라우팅 (%s): job=%s", reason, job.id)
            self._spawn_extra(job, self.fallback)  # type: ignore[arg-type]
            return job

        job = await new_job("primary", self.primary)
        await self._queue.put(job)
        return job

    def _fallback_reason(self, wait_fallback: bool = True) -> str | None:
        if not self._usable(self.fallback) or not self.api_allowed:
            return None
        if not self.primary.is_ready:
            return "primary_not_ready"
        if (
            wait_fallback
            and self._jobs_ahead() >= self.concurrency
            and self.estimated_wait_for_new_job() > self.settings.max_wait_seconds
        ):
            # 앞에 기다리는 작업이 있어 바로 시작할 수 없을 때만 넘긴다. 빈 워커가 있으면
            # 1건 평균 시간이 길어도(klein 첫 호출 등) 대기 자체는 0이므로 OpenAI로 넘기지 않음
            return "queue_wait"
        return None

    @property
    def api_allowed(self) -> bool:
        """OpenAI를 써도 되는지 (금액 회로가 닫혀 있는지)."""
        return not self.budget.exceeded

    def text_quality(self, requested: str) -> str:
        """금액 상한을 넘었으면 "더 자연스럽게"(luna)도 로컬 Gemma(basic)로 바꾼다."""
        return requested if self.api_allowed else "basic"

    def _sync_core_fallback(self) -> None:
        """금액 상한을 넘으면 core 안의 폴백(klein→flare, Gemma→luna)도 끈다. 자정에 원래대로.

        core는 호출마다 config.USE_FALLBACK을 읽는다. 프로세스 전체 값이라 회로와 같이 움직인다.
        """
        from just_make_it import config

        if self._core_fallback_default is None:
            self._core_fallback_default = config.USE_FALLBACK
        wanted = self._core_fallback_default and self.api_allowed
        if config.USE_FALLBACK != wanted:
            config.USE_FALLBACK = wanted
            logger.warning(
                "OpenAI 금액 회로 %s: 오늘 $%.4f / 상한 $%.2f",
                "닫힘(OpenAI 사용)" if wanted else "열림(OpenAI 막음)",
                self.budget.spent,
                self.budget.limit,
            )

    def _jobs_ahead(self) -> int:
        """새 작업 앞에 있는 기본 작업 수 (대기 중 + 실행 중)."""
        return self._queue.qsize() + len(self._running)

    async def check_capacity(self, client_id: str, count: int) -> None:
        """작업 count개를 한꺼번에 받을 수 있는지 미리 확인한다 (상세페이지 5칸).

        한도는 차감하지 않는다. 실제 차감은 칸마다 submit()에서 한다.

        Raises:
            DailyLimitError: 사용자·전체 하루 한도를 넘게 될 때
        """
        limit = self.settings.client_daily_limit
        if limit:
            used = await asyncio.to_thread(self.records.count_today, client_id)
            if used + count > limit:
                raise DailyLimitError("사용자 하루 생성 한도에 도달했습니다.")
        total = self.jobs_today.limit
        if total and self.jobs_today.count + count > total:
            raise DailyLimitError("하루 생성 한도에 도달했습니다.")

    @staticmethod
    def _usable(generator: ImageGenerator | None) -> bool:
        return generator is not None and generator.is_ready

    # ------------------------------------------------------------------ 조회
    def _wait_for(self, ahead: int) -> float:
        return round(
            math.ceil((ahead + 1) / self.concurrency) * self.seconds_per_job, 1
        )

    def estimated_wait_for_new_job(self) -> float:
        """지금 접수하는 기본 작업이 끝날 때까지의 예상 시간(초)."""
        return self._wait_for(self._jobs_ahead())

    def progress(self, gid: str) -> dict | None:
        """만드는 중인 작업의 진행 상황 (V3). 끝났거나 모르는 작업이면 None.

        stage: queued / running, jobs_ahead: 먼저 처리될 작업 수, estimated_seconds: 남은 예상 시간
        """
        job = self._active.get(gid)
        if job is None or job.is_finished or job.cancelled:
            return None
        now = time.monotonic()
        extra = job.route != "primary"
        per_job = self.extra_seconds_per_job if extra else self.seconds_per_job
        if job.state == JobState.RUNNING and job.started_mono is not None:
            left = max(1.0, per_job - (now - job.started_mono))
            return {
                "stage": "running",
                "jobs_ahead": 0,
                "estimated_seconds": round(left, 1),
            }
        if extra:
            # OpenAI 자리를 기다리는 중 (동시 EXTRA_CONCURRENCY개)
            return {
                "stage": "queued",
                "jobs_ahead": 0,
                "estimated_seconds": round(per_job, 1),
            }
        waiting = [
            j for j in list(self._queue._queue) if not j.cancelled
        ]  # asyncio.Queue 안의 순서
        position = next((i for i, j in enumerate(waiting) if j is job), len(waiting))
        ahead = position + len(self._running)
        return {
            "stage": "queued",
            "jobs_ahead": ahead,
            "estimated_seconds": self._wait_for(ahead),
        }

    def cancel(self, job: Job, reason: str) -> None:
        """작업을 취소한다. 대기 중이면 건너뛰고, 실행 중이면 core가 멈추게 한다.

        이미 끝난 작업은 그대로 둔다.
        """
        if job.is_finished or job.cancelled:
            return
        job.cancelled = True
        logger.info("작업 취소 job=%s (%s)", job.id, reason)
        if job.deadline is not None:
            job.deadline.cancel()
        if job.state == JobState.QUEUED:
            # 기본 대기열에서 꺼낼 때 건너뛴다. 실패 기록은 지금 남겨 응답과 DB를 맞춘다
            self._fail(job, f"cancelled: {reason}", ERROR_GENERIC)

    async def wait(self, job: Job, timeout: float) -> bool:
        """작업 완료를 최대 timeout초 기다린다. 끝났으면 True."""
        if job.is_finished:
            return True
        if timeout <= 0:
            return False
        try:
            await asyncio.wait_for(job.done.wait(), timeout=timeout)
        except TimeoutError:
            return False
        return True

    @property
    def queue_length(self) -> int:
        return self._queue.qsize()

    @property
    def running_count(self) -> int:
        return len(self._running)

    # ------------------------------------------------------------------ 실행
    async def _call(self, generator: ImageGenerator, job: Job):
        """제한 시간을 걸고 생성기를 호출한다. 시간이 지나면 core 작업도 멈춘다."""
        timeout = self.settings.generation_timeout_seconds
        job.deadline = Deadline(timeout + DEADLINE_GRACE_SECONDS)
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    _run_within, job.deadline, generator.generate, job.spec
                ),
                timeout=timeout,
            )
        except (TimeoutError, asyncio.CancelledError):
            job.deadline.cancel()
            raise
        finally:
            job.deadline = None

    async def _worker_loop(self) -> None:
        while True:
            job = await self._queue.get()
            if job.cancelled:  # 기다리는 동안 취소됨 (cancel()이 이미 실패로 기록)
                self._queue.task_done()
                continue
            self._running.add(job.id)
            job.state = JobState.RUNNING
            job.started_mono = time.monotonic()
            try:
                await self._run_primary(job)
            except Exception:  # 워커가 죽지 않도록 마지막 방어선
                logger.exception("워커 처리 중 예외: job=%s", job.id)
                self._fail(job, "worker_exception", ERROR_GENERIC)
            finally:
                self._running.discard(job.id)
                self._queue.task_done()

    async def _run_primary(self, job: Job) -> None:
        attempts = 1 + max(0, self.settings.retry_count)
        last_error = ""
        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            try:
                output = await self._call(self.primary, job)
            except TimeoutError:
                last_error = (
                    f"timeout after {self.settings.generation_timeout_seconds:.0f}s"
                )
                logger.warning("기본 생성 시간 초과 job=%s", job.id)
                break  # 시간 초과는 재시도하지 않음
            except GeneratorError as exc:
                if job.cancelled:  # 취소 신호로 core가 멈춘 것 → 다시 시도하지 않음
                    self._fail(job, f"cancelled: {exc}", ERROR_GENERIC)
                    return
                if not exc.retryable:
                    self._fail(job, str(exc), ERROR_INPUT, input_error=True)
                    return
                last_error = str(exc)
                logger.warning(
                    "기본 생성 실패 (%d/%d) job=%s: %s", attempt, attempts, job.id, exc
                )
                continue
            self._update_speed(time.monotonic() - started)
            await self._finish(job, output, self.primary)
            return

        # 재시도까지 실패 또는 시간 초과 → 장애 Fallback (취소된 작업은 넘기지 않음)
        if job.cancelled:
            self._fail(job, f"cancelled: {last_error}", ERROR_GENERIC)
            return
        if self._usable(self.fallback) and self.api_allowed and self.extra_today.take():
            job.route, job.fallback_reason = "fallback", "primary_error"
            logger.info("장애 Fallback (%s): job=%s", last_error, job.id)
            self._spawn_extra(job, self.fallback)  # type: ignore[arg-type]
            return
        self._fail(job, last_error, ERROR_GENERIC)

    def _spawn_extra(self, job: Job, generator: ImageGenerator) -> None:
        task = asyncio.create_task(self._run_extra(job, generator))
        self._extra_tasks.add(task)
        task.add_done_callback(self._extra_tasks.discard)

    async def _run_extra(self, job: Job, generator: ImageGenerator) -> None:
        async with self._extra_slots:
            if job.cancelled:  # 자리를 기다리는 동안 취소됨
                self._fail(job, "cancelled before start", ERROR_GENERIC)
                return
            job.state = JobState.RUNNING
            if job.started_mono is None:
                job.started_mono = time.monotonic()
            call_started = time.monotonic()
            try:
                output = await self._call(generator, job)
            except TimeoutError:
                self._fail(
                    job,
                    f"timeout after {self.settings.generation_timeout_seconds:.0f}s",
                    ERROR_GENERIC,
                )
                return
            except GeneratorError as exc:
                if job.cancelled:
                    self._fail(job, f"cancelled: {exc}", ERROR_GENERIC)
                elif exc.retryable:
                    self._fail(job, str(exc), ERROR_GENERIC)
                else:
                    self._fail(job, str(exc), ERROR_INPUT, input_error=True)
                return
            except Exception as exc:
                self._fail(job, repr(exc), ERROR_GENERIC)
                return
            elapsed = time.monotonic() - call_started
            self.extra_seconds_per_job = (
                0.7 * self.extra_seconds_per_job + 0.3 * elapsed
            )
            await self._finish(job, output, generator)

    async def _finish(
        self, job: Job, output: GenerationOutput, generator: ImageGenerator
    ) -> None:
        job.finished_mono = time.monotonic()
        job.source = output.source or generator.source
        job.model = output.model
        job.prompt = output.prompt
        job.cost_usd = output.cost_usd
        self.budget.add(output.cost_usd)
        self._sync_core_fallback()
        # 문구·그림 시간은 core가 단계별로 잰 값. 없으면(mock 등) 호출 전체 시간을 그림으로 본다
        job.text_ms = output.text_ms
        job.image_ms = output.image_ms if output.image_ms is not None else job.run_ms
        output.params = {**output.params, "run_ms": job.run_ms}
        if output.fallback_reason and job.route == "primary":
            # core가 안에서 로컬 모델 대신 API 모델로 만든 경우 (예: klein 실패 → flare)
            job.route, job.fallback_reason = "fallback", "core_fallback"
            logger.info(
                "core 내부 Fallback: job=%s (%s)", job.id, output.fallback_reason
            )
        try:
            job.result = await asyncio.to_thread(
                self.records.finish,
                job.id,
                output,
                source=job.source,
                route=job.route,
                queue_ms=job.queue_ms,
                image_ms=job.image_ms,
            )
        except Exception as exc:
            self._fail(job, f"결과 저장 실패: {exc!r}", ERROR_GENERIC)
            return
        job.state = JobState.SUCCEEDED
        self._active.pop(job.id, None)
        job.done.set()
        self._log(job, generator)

    def _fail(
        self,
        job: Job,
        internal_error: str,
        user_error: str,
        *,
        input_error: bool = False,
    ) -> None:
        if job.is_finished:  # 취소와 실패가 겹치면 처음 기록만 남긴다
            return
        logger.error("작업 실패 job=%s route=%s: %s", job.id, job.route, internal_error)
        job.error = user_error
        job.error_internal = internal_error
        job.input_error = input_error
        job.state = JobState.FAILED
        self._active.pop(job.id, None)
        job.finished_mono = job.finished_mono or time.monotonic()
        try:
            self.records.fail(job.id, internal_error)
        except Exception:  # 기록 실패가 응답까지 막지 않게
            logger.exception("실패 기록 저장 실패 job=%s", job.id)
        job.done.set()
        self._log(job, None)

    def _log(self, job: Job, generator: ImageGenerator | None) -> None:
        """generations 테이블 컬럼 이름으로 JSON 한 줄을 남긴다."""
        backend = job.source
        if backend is None:
            chosen = {"primary": self.primary, "fallback": self.fallback}.get(
                job.route, self.premium
            )
            backend = chosen.source if chosen else None
        record = {
            "event": "generation",
            "id": job.id,
            "client_id": job.client_id,
            "parent_id": job.parent_id,
            "detail_page_id": job.detail_page_id,
            "section_index": job.section_index,
            "created_at": job.created_at,
            "purpose": job.spec.purpose,
            "input_json": {
                "product_name": job.spec.product_name,
                "message": job.spec.message,
                "style": job.spec.style,
                "adjustments": job.spec.adjustments,
                "has_reference_image": job.spec.reference_image is not None,
            },
            "image_prompt": job.prompt,
            "image_path": f"{job.id}.png" if job.result else None,
            "backend": backend,
            "route": job.route,
            "fallback_reason": job.fallback_reason,
            "model": job.model or (generator.name if generator else None),
            "status": job.state.value,
            "error": job.error_internal,
            "queue_ms": job.queue_ms,
            "text_ms": job.text_ms,
            "image_ms": job.image_ms,
            "run_ms": job.run_ms,
            "cost_usd": job.cost_usd,
        }
        generation_log.info(json.dumps(record, ensure_ascii=False))

    # ------------------------------------------------------------------ 보조
    def _update_speed(self, seconds: float) -> None:
        # 지수이동평균으로 1건 생성 시간을 보정 (Fallback 기준이 실측을 따라감)
        self.seconds_per_job = 0.7 * self.seconds_per_job + 0.3 * seconds
