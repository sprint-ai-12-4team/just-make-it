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
- 파이썬은 실행 중인 스레드를 강제로 멈출 수 없어서, 타임아웃 뒤에도 호출 자체는
  뒤에서 끝날 때까지 돈다. 호출을 실제로 끊으려면 core의 OpenAI 클라이언트에도
  timeout이 있어야 한다.

로그
- 작업이 끝날 때마다 `just_make_it.serving.generations` 로거에 JSON 한 줄을 남긴다.
  필드 이름은 `generations` 테이블 컬럼과 같다.
"""

import asyncio
import json
import logging
import math
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone

from .generators import GeneratorError, ImageGenerator
from .schemas import (
    GenerationOutput,
    GenerationSpec,
    JobState,
    Route,
    Source,
)
from .settings import ServingSettings
from .storage import ResultStore

logger = logging.getLogger(__name__)
generation_log = logging.getLogger("just_make_it.serving.generations")

KST = timezone(timedelta(hours=9))  # 한국은 서머타임이 없어 고정 오프셋으로 충분
EXTRA_CONCURRENCY = 2

ERROR_GENERIC = "잠시 후 다시 시도해 주세요."
ERROR_INPUT = "입력 내용으로 이미지를 만들 수 없어요. 내용을 확인해 주세요."


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
    created_at: str = field(default_factory=_now_iso)
    state: JobState = JobState.QUEUED
    submitted_mono: float = field(default_factory=time.monotonic)
    started_mono: float | None = None
    finished_mono: float | None = None
    image_url: str | None = None
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
    def image_ms(self) -> int | None:
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


class QueueManager:
    """작업 접수, 경로 선택, 실행, 상태 조회를 담당한다."""

    def __init__(
        self,
        settings: ServingSettings,
        primary: ImageGenerator,
        fallback: ImageGenerator | None,
        premium: ImageGenerator | None,
        store: ResultStore,
    ) -> None:
        self.settings = settings
        self.primary = primary
        self.fallback = fallback
        self.premium = premium
        self.store = store

        self.concurrency = max(1, settings.primary_concurrency)
        self.seconds_per_job = settings.seconds_per_job_init
        self.jobs_today = _DailyCounter(settings.daily_job_limit)
        self.extra_today = _DailyCounter(settings.extra_daily_limit)

        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._order: deque[str] = deque()  # 대기 순번 계산용
        self._running: set[str] = set()
        self._jobs: dict[str, Job] = {}
        self._workers: list[asyncio.Task] = []
        self._extra_tasks: set[asyncio.Task] = set()
        self._extra_slots = asyncio.Semaphore(EXTRA_CONCURRENCY)

    # ------------------------------------------------------------------ 수명 주기
    async def start(self) -> None:
        for generator in (self.primary, self.fallback, self.premium):
            if generator is None:
                continue
            try:
                await asyncio.to_thread(generator.load)
            except Exception:  # 준비 실패해도 서버는 뜨고 다른 경로로 처리
                logger.exception("생성기 준비 실패: %s", generator.name)
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

    async def stop(self) -> None:
        tasks = [*self._workers, *self._extra_tasks]
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
    ) -> Job:
        self._cleanup_expired()
        if (
            self._queue.qsize() >= self.settings.queue_max_size
            and self._fallback_reason() is None
        ):
            raise QueueFullError("대기열이 가득 찼습니다.")
        if not self.jobs_today.take():
            raise DailyLimitError("하루 생성 한도에 도달했습니다.")

        def new_job(route: Route, reason: str | None = None) -> Job:
            job = Job(
                id=str(uuid.uuid4()),
                spec=spec,
                route=route,
                client_id=client_id,
                parent_id=parent_id,
                fallback_reason=reason,
            )
            self._jobs[job.id] = job
            return job

        if premium and self._usable(self.premium) and self.extra_today.take():
            job = new_job("premium")
            self._spawn_extra(job, self.premium)  # type: ignore[arg-type]
            return job

        reason = self._fallback_reason()
        if reason and self.extra_today.take():
            job = new_job("fallback", reason)
            logger.info("Fallback 라우팅 (%s): job=%s", reason, job.id)
            self._spawn_extra(job, self.fallback)  # type: ignore[arg-type]
            return job

        job = new_job("primary")
        self._order.append(job.id)
        await self._queue.put(job)
        return job

    def _fallback_reason(self) -> str | None:
        if not self._usable(self.fallback):
            return None
        if not self.primary.is_ready:
            return "primary_not_ready"
        if self.estimated_wait_for_new_job() > self.settings.max_wait_seconds:
            return "queue_wait"
        return None

    @staticmethod
    def _usable(generator: ImageGenerator | None) -> bool:
        return generator is not None and generator.is_ready

    # ------------------------------------------------------------------ 조회
    def get(self, job_id: str) -> Job | None:
        self._cleanup_expired()
        return self._jobs.get(job_id)

    def queue_position(self, job: Job) -> int | None:
        """기본 대기열에서 기다리는 중이면 1부터 시작하는 순번, 아니면 None."""
        if job.state != JobState.QUEUED or job.route != "primary":
            return None
        try:
            return self._order.index(job.id) + 1
        except ValueError:
            return None

    def _wait_for(self, ahead: int) -> float:
        return round(
            math.ceil((ahead + 1) / self.concurrency) * self.seconds_per_job, 1
        )

    def estimated_wait_for_new_job(self) -> float:
        """지금 접수하는 기본 작업이 끝날 때까지의 예상 시간(초)."""
        return self._wait_for(self._queue.qsize() + len(self._running))

    def estimated_wait(self, job: Job) -> float | None:
        position = self.queue_position(job)
        if position is None:
            return None
        return self._wait_for(position - 1 + len(self._running))

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
    async def _call(self, generator: ImageGenerator, spec: GenerationSpec):
        """제한 시간을 걸고 생성기를 호출한다."""
        return await asyncio.wait_for(
            asyncio.to_thread(generator.generate, spec),
            timeout=self.settings.generation_timeout_seconds,
        )

    async def _worker_loop(self) -> None:
        while True:
            job = await self._queue.get()
            if job.id in self._order:
                self._order.remove(job.id)
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
                output = await self._call(self.primary, job.spec)
            except TimeoutError:
                last_error = (
                    f"timeout after {self.settings.generation_timeout_seconds:.0f}s"
                )
                logger.warning("기본 생성 시간 초과 job=%s", job.id)
                break  # 시간 초과는 재시도하지 않음
            except GeneratorError as exc:
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

        # 재시도까지 실패 또는 시간 초과 → 장애 Fallback
        if self._usable(self.fallback) and self.extra_today.take():
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
            job.state = JobState.RUNNING
            if job.started_mono is None:
                job.started_mono = time.monotonic()
            try:
                output = await self._call(generator, job.spec)
            except TimeoutError:
                self._fail(
                    job,
                    f"timeout after {self.settings.generation_timeout_seconds:.0f}s",
                    ERROR_GENERIC,
                )
                return
            except GeneratorError as exc:
                if exc.retryable:
                    self._fail(job, str(exc), ERROR_GENERIC)
                else:
                    self._fail(job, str(exc), ERROR_INPUT, input_error=True)
                return
            except Exception as exc:
                self._fail(job, repr(exc), ERROR_GENERIC)
                return
            await self._finish(job, output, generator)

    async def _finish(
        self, job: Job, output: GenerationOutput, generator: ImageGenerator
    ) -> None:
        try:
            job.image_url = await asyncio.to_thread(
                self.store.save, job.id, output.image_bytes
            )
        except Exception as exc:
            self._fail(job, f"결과 저장 실패: {exc!r}", ERROR_GENERIC)
            return
        job.source = generator.source
        job.model = output.model
        job.message = output.message
        job.width, job.height = output.width, output.height
        job.prompt = output.prompt
        job.state = JobState.SUCCEEDED
        job.finished_mono = time.monotonic()
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
        logger.error("작업 실패 job=%s route=%s: %s", job.id, job.route, internal_error)
        job.error = user_error
        job.error_internal = internal_error
        job.input_error = input_error
        job.state = JobState.FAILED
        job.finished_mono = time.monotonic()
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
            "created_at": job.created_at,
            "purpose": job.spec.purpose,
            "input_json": {
                "product_name": job.spec.product_name,
                "message": job.spec.message,
                "generation_mode": job.spec.generation_mode,
                "style": job.spec.style,
                "adjustments": job.spec.adjustments,
                "has_reference_image": job.spec.reference_image is not None,
            },
            "image_prompt": job.prompt,
            "image_path": job.image_url,
            "backend": backend,
            "route": job.route,
            "fallback_reason": job.fallback_reason,
            "model": job.model or (generator.name if generator else None),
            "status": job.state.value,
            "error": job.error_internal,
            "queue_ms": job.queue_ms,
            "image_ms": job.image_ms,
            # TODO: 응답의 토큰 사용량 또는 품질·크기별 단가표로 계산
            "cost_usd": None,
        }
        generation_log.info(json.dumps(record, ensure_ascii=False))

    # ------------------------------------------------------------------ 보조
    def _update_speed(self, seconds: float) -> None:
        # 지수이동평균으로 1건 생성 시간을 보정 (Fallback 기준이 실측을 따라감)
        self.seconds_per_job = 0.7 * self.seconds_per_job + 0.3 * seconds

    def _cleanup_expired(self) -> None:
        now = time.monotonic()
        ttl = self.settings.job_ttl_seconds
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.finished_mono is not None and now - job.finished_mono > ttl
        ]
        for job_id in expired:
            del self._jobs[job_id]
