"""상세페이지 비동기 생성 (POST /detail-pages, GET /detail-pages/{id}, 섹션 다시 만들기).

흐름 (api_spec 3장)
1. 접수: 진행 중인 페이지가 있으면 409, 하루 한도가 5칸을 못 받으면 429. 바로 202
2. 문구: 텍스트 모델이 5칸(대표 · 좋은 점 ×3 · 마무리)의 제목·설명·사진 장면을 한 번에 만든다
3. 이미지: 칸마다 생성 작업을 큐에 넣는다. /generate와 같은 대기열·타임아웃·Fallback을 쓰고,
   이미지는 글자 없이 만든다 (문구는 프론트가 얹음)
4. 칸이 모두 끝나면 service/db.py가 페이지를 success로 닫는다. 프론트는 2초마다 폴링

섹션 문구는 core의 `suggest_detail_sections()`가 만든다 (`CoreDetailWriter`).
테스트·mock 모드에서는 `MockDetailWriter`로 바꿔 끼운다.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .generators import GeneratorError
from .queue_manager import (
    DailyLimitError,
    QueueFullError,
    QueueManager,
    run_with_deadline,
)
from .records import GenerationRecords
from .schemas import IMAGE_QUALITY, TEXT_QUALITY, DetailPageRequest, GenerationSpec
from .settings import ServingSettings

logger = logging.getLogger(__name__)

SECTION_COUNT = 5  # service/db.py와 같은 값
ROLES = ["hero", "feature", "feature", "feature", "closing"]
# 섹션 이미지 크기·구도는 커머스 목적을 따른다 (core prompt_builder)
SECTION_PURPOSE = "commerce"
# 섹션 다시 만들기는 문구를 그대로 두므로 문구를 줄이는 칩은 이미지 쪽에 넘기지 않는다
TEXT_ONLY_ADJUSTMENTS = {"텍스트 짧게", "글자 더 크게"}


class DetailPageBusyError(RuntimeError):
    """같은 사용자의 상세페이지가 이미 진행 중일 때 (409)."""


class DetailPageNotFoundError(LookupError):
    """없는 페이지 id 또는 칸 번호 (404)."""


class SectionNotReadyError(RuntimeError):
    """페이지나 그 칸이 아직 만드는 중이거나, 문구가 없어 다시 만들 수 없을 때 (409)."""


# ---------------------------------------------------------------------- 문구 5칸
class DetailWriter(ABC):
    @abstractmethod
    def write(
        self,
        product_name: str,
        message: str,
        features: list[str],
        style: str | None,
        text_quality: str = "basic",
    ) -> list[dict]:
        """5칸의 [{role, title, body, image_prompt}]를 돌려준다. 실패하면 GeneratorError.

        image_prompt: 그 칸 사진에 담을 장면 (한국어 한 문장). core가 영어 묘사로 바꾼다.
        """


class CoreDetailWriter(DetailWriter):
    """core의 상세페이지 5칸 문구 함수(`suggest_detail_sections`)를 부른다."""

    def write(self, product_name, message, features, style, text_quality="basic"):
        from just_make_it.core import TextGenerationError, suggest_detail_sections

        try:
            return suggest_detail_sections(
                product_name,
                message,
                features=features,
                style=style,
                text_quality=text_quality,
            )
        except ValueError as exc:  # 입력 오류 (라우터가 먼저 막지만 방어)
            raise GeneratorError(str(exc), retryable=False) from exc
        except TextGenerationError as exc:
            raise GeneratorError(str(exc)) from exc
        except Exception as exc:  # API 키 누락 등
            raise GeneratorError(f"{type(exc).__name__}: {exc}") from exc


class MockDetailWriter(DetailWriter):
    """API 호출 없이 가짜 문구 5칸 (IMAGE_BACKEND=mock)."""

    def write(self, product_name, message, features, style, text_quality="basic"):
        names = [*features, "정성 가득", "믿을 수 있는 재료", "빠른 배송"][:3]
        texts = [
            (message, f"{product_name}을 소개합니다"),
            *((name, f"{product_name}의 {name}") for name in names),
            (f"지금 {product_name}을 만나 보세요", "오늘 주문하면 내일 도착해요"),
        ]
        return [
            {"role": ROLES[i], "title": t, "body": b, "image_prompt": f"{t} 장면"}
            for i, (t, b) in enumerate(texts)
        ]


# ---------------------------------------------------------------------- 서비스
@dataclass
class _PageInput:
    client_id: str
    product_name: str
    style: str | None
    image_model: str
    text_quality: str


class DetailPageService:
    """상세페이지 접수·문구 생성·섹션 이미지 작업 제출을 맡는다."""

    def __init__(
        self,
        settings: ServingSettings,
        manager: QueueManager,
        writer: DetailWriter,
        records: GenerationRecords,
    ) -> None:
        self.settings = settings
        self.manager = manager
        self.writer = writer
        self.records = records
        # 진행 중 확인과 접수 사이에 같은 사용자의 요청이 끼어들지 않게 한다
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    # ------------------------------------------------------------------ 접수
    async def start(
        self,
        payload: DetailPageRequest,
        reference: bytes | None,
        client_id: str,
    ) -> str:
        """페이지를 만들고 id를 돌려준다. 문구·이미지는 뒤에서 만든다.

        Raises:
            DetailPageBusyError: 이 사용자의 페이지가 이미 진행 중
            DailyLimitError: 오늘 5칸을 더 만들 수 없음
        """
        text_quality = (
            TEXT_QUALITY[payload.text_model]
            if payload.text_model
            else self.settings.generate_text_quality
        )
        stored = {
            "product_name": payload.product_name,
            "message": payload.message,
            "features": payload.features,
            "style": payload.style,
            "image_model": payload.image_model,
            "text_quality": text_quality,
            "has_reference_image": reference is not None,
        }
        async with self._lock:
            if await asyncio.to_thread(self.records.has_running_detail_page, client_id):
                raise DetailPageBusyError(client_id)
            await self.manager.check_capacity(client_id, SECTION_COUNT)
            pid = await asyncio.to_thread(
                self.records.start_detail_page, client_id, stored
            )
        if reference is not None:
            # 섹션 다시 만들기에서 다시 쓴다 (칸 결과가 접수 실패로 사진이 없어도)
            await asyncio.to_thread(self.records.save_reference, pid, reference)
        page = _PageInput(
            client_id=client_id,
            product_name=payload.product_name,
            style=payload.style,
            image_model=payload.image_model,
            text_quality=text_quality,
        )
        self._spawn(self._run(pid, payload, page, reference))
        return pid

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(
        self,
        pid: str,
        payload: DetailPageRequest,
        page: _PageInput,
        reference: bytes | None,
    ) -> None:
        started = time.monotonic()
        try:
            # 시간이 지나면 core의 Gemma·luna 호출도 멈춘다 (core/deadline.py)
            sections = await run_with_deadline(
                self.writer.write,
                payload.product_name,
                payload.message,
                payload.features,
                payload.style,
                page.text_quality,
                timeout=self.settings.detail_text_timeout_seconds,
            )
        except TimeoutError:
            await self._fail_page(pid, "문구 생성 시간 초과")
            return
        except Exception as exc:  # GeneratorError 포함. 페이지 전체 실패
            await self._fail_page(pid, f"문구 생성 실패: {exc}")
            return

        text_ms = int(round((time.monotonic() - started) * 1000))
        await asyncio.to_thread(
            self.records.set_detail_sections, pid, sections, text_ms
        )
        logger.info("상세페이지 문구 완료: page=%s (%dms)", pid, text_ms)
        for index, section in enumerate(sections):
            await self._submit_section(pid, index, section, page, reference)

    async def _fail_page(self, pid: str, error: str) -> None:
        logger.error("상세페이지 실패 page=%s: %s", pid, error)
        try:
            await asyncio.to_thread(self.records.fail_detail_page, pid, error)
        except Exception:
            logger.exception("상세페이지 실패 기록 저장 실패 page=%s", pid)

    async def _submit_section(
        self,
        pid: str,
        index: int,
        section: dict,
        page: _PageInput,
        reference: bytes | None,
        *,
        adjustments: list[str] | None = None,
        parent_id: str | None = None,
    ) -> None:
        spec = GenerationSpec(
            product_name=page.product_name,
            # core는 message로 사진 장면을 정한다. 칸마다 다른 장면이 들어간다
            message=section.get("image_prompt") or section.get("title") or "",
            purpose=SECTION_PURPOSE,
            style=page.style,
            adjustments=[
                a for a in adjustments or [] if a not in TEXT_ONLY_ADJUSTMENTS
            ],
            reference_image=reference,
            text_quality=page.text_quality,
            # 상세페이지 칸 문구는 아직 프론트 canvas가 얹는다 (api_spec 5장)
            output="image",
        )
        premium = IMAGE_QUALITY.get(page.image_model) == "detailed"
        try:
            await self.manager.submit(
                spec,
                premium=premium,
                client_id=page.client_id,
                parent_id=parent_id,
                detail_page_id=pid,
                section_index=index,
                wait_fallback=False,
            )
        except (DailyLimitError, QueueFullError) as exc:
            logger.warning("섹션 접수 실패 page=%s index=%d: %s", pid, index, exc)
            generator = self.manager.premium if premium else self.manager.primary
            await asyncio.to_thread(
                self.records.fail_section,
                client_id=page.client_id,
                spec=spec,
                detail_page_id=pid,
                section_index=index,
                backend=generator.source if generator else "local",
                model=generator.name if generator else page.image_model,
                error=f"접수 실패: {exc}",
            )

    # ------------------------------------------------------------------ 섹션 다시 만들기
    async def regenerate(self, pid: str, index: int, adjustments: list[str]) -> None:
        """문구는 그대로 두고 그 칸 이미지만 다시 만든다.

        처음 올린 참고 사진을 다시 쓰고, 직전 결과를 parent_id로 넘겨 수정 칩이 있으면
        시드(구도)도 이어 쓴다.

        Raises:
            DetailPageNotFoundError: 없는 페이지 또는 칸 번호
            SectionNotReadyError: 페이지·칸이 아직 만드는 중이거나 문구가 없음
            DailyLimitError: 오늘 더 만들 수 없음
        """
        if not 0 <= index < SECTION_COUNT:
            raise DetailPageNotFoundError(f"{pid}/{index}")
        async with self._lock:
            page = await asyncio.to_thread(self.records.get_detail_page, pid)
            if page is None:
                raise DetailPageNotFoundError(pid)
            if page["status"] == "processing":
                raise SectionNotReadyError("page_processing")
            if page["sections"][index]["status"] == "processing":
                raise SectionNotReadyError("section_processing")
            info = await asyncio.to_thread(self.records.section_input, pid, index)
            if info is None:
                raise SectionNotReadyError("no_text")  # 문구 생성부터 실패한 페이지
            stored = info["input"]
            page_input = _PageInput(
                client_id=info["client_id"],
                product_name=stored["product_name"],
                style=stored.get("style"),
                image_model=stored.get("image_model", "flux2-klein-4b"),
                text_quality=stored.get(
                    "text_quality", self.settings.generate_text_quality
                ),
            )
            await self.manager.check_capacity(page_input.client_id, 1)
            reference = await asyncio.to_thread(self.records.load_reference, pid)
            await self._submit_section(
                pid,
                index,
                info["section"],
                page_input,
                reference,
                adjustments=adjustments,
                parent_id=info["parent_id"],
            )
