"""상세페이지 비동기 생성 (POST /detail-pages, GET /detail-pages/{id}, 섹션 다시 만들기).

흐름 (api_spec 3장)
1. 접수: 진행 중인 페이지가 있으면 409, 하루 한도가 5칸을 못 받으면 429. 바로 202
2. 문구: 텍스트 모델이 5칸(대표 · 좋은 점 ×3 · 마무리)의 제목·설명·사진 장면을 한 번에 만든다
3. 이미지: 칸마다 생성 작업을 큐에 넣는다. /generate와 같은 대기열·타임아웃·Fallback을 쓰고,
   이미지는 글자 없이 만든다 (문구는 프론트가 얹음)
4. 칸이 모두 끝나면 service/db.py가 페이지를 success로 닫는다. 프론트는 2초마다 폴링

섹션 문구 생성기(`DetailWriter`)는 core에 상세페이지용 함수가 생기면 그걸 부르도록
`CoreDetailWriter`만 바꾸면 된다. 지금은 core의 `generate_text()`에 규칙을 넘겨 만든다.
"""

import asyncio
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .generators import GeneratorError
from .queue_manager import DailyLimitError, QueueFullError, QueueManager
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


DETAIL_RULES = """\
너는 스마트스토어 상세페이지를 쓰는 카피라이터야.
상세페이지는 위에서 아래로 5칸이고, 칸마다 사진 위에 제목과 설명을 얹어.
칸 구성
1. 대표: 핵심 메시지를 살려 상품을 한눈에 소개
2~4. 좋은 점: 상품 특징을 한 칸에 하나씩
5. 마무리: 구매를 권하는 따뜻한 한마디
규칙
- 제목은 15자 안팎, 설명은 30자 안팎으로 짧고 읽기 쉽게
- 최고, 1위 같은 근거 없는 과장 표현과 의학적 효능 표현은 쓰지 않기
- 입력된 할인율, 가격, 날짜, 수치는 바꾸지 말고 그대로 쓰기
- 특징이 주어지면 2~4칸 제목에 그 특징을 순서대로 그대로 쓰기
- 특징이 모자라면 상품과 메시지에서 자연스럽게 떠올릴 수 있는 장점으로 채우되,
  확인할 수 없는 수치나 인증은 지어내지 않기
- 장면은 그 칸 사진에 담을 모습을 한 문장으로. 칸마다 다른 장면으로 쓰고,
  글자·간판·로고·포장 문구는 넣지 않기
- 한 칸에 한 줄씩 `번호 | 제목 | 설명 | 장면` 형식으로 5줄만 출력하고 다른 말은 붙이지 않기

예시
- 상품: 수제 딸기잼 / 메시지: 국산 딸기 100% 신상품 / 특징: 무첨가, 소량 생산, 선물 포장
1 | 국산 딸기 100%, 그대로 담았어요 | 설탕 말고 딸기 맛만 남겼습니다 | 유리병에 담긴 붉은 딸기잼과 생딸기
2 | 무첨가 | 보존료·색소 없이 만들어요 | 나무 숟가락으로 떠낸 윤기 나는 잼
3 | 소량 생산 | 매일 필요한 만큼만 끓여요 | 작은 냄비에서 보글보글 끓는 딸기
4 | 선물 포장 | 리본 하나로 마음까지 전해요 | 리본으로 묶은 잼 병 두 개
5 | 아침 식탁에 딸기 한 스푼 | 오늘 주문하면 내일 만나요 | 잼을 바른 토스트와 커피가 놓인 아침 식탁"""

_LINE = re.compile(r"^\s*[-*]?\s*(\d)\s*[.)]?\s*\|(.+)$")


def build_detail_input(
    product_name: str, message: str, features: list[str], style: str | None
) -> str:
    text = f"상품: {product_name} / 메시지: {message}"
    if features:
        text += f" / 특징: {', '.join(features)}"
    if style:
        text += f" / 분위기: {style}"
    return text + "\n상세페이지 5칸을 써줘."


def parse_sections(text: str, features: list[str]) -> list[dict]:
    """모델 출력을 5칸으로 나눈다. 칸이 모자라거나 형식이 깨지면 ValueError.

    특징을 직접 적었으면 2~4칸 제목은 그 특징으로 고정한다 (모델이 바꿔 써도).
    """
    found: dict[int, dict] = {}
    for line in text.splitlines():
        match = _LINE.match(line.strip("`"))
        if not match:
            continue
        number = int(match.group(1))
        parts = [p.strip().strip("\"'") for p in match.group(2).split("|")]
        if not 1 <= number <= SECTION_COUNT or len(parts) < 2 or not parts[0]:
            continue
        found.setdefault(
            number - 1,
            {
                "title": parts[0],
                "body": parts[1] if len(parts) > 1 else "",
                "image_prompt": parts[2] if len(parts) > 2 and parts[2] else parts[0],
            },
        )
    if len(found) < SECTION_COUNT:
        raise ValueError(f"상세페이지 문구가 {len(found)}칸뿐입니다: {text[:200]!r}")

    sections = []
    for i in range(SECTION_COUNT):
        section = {"role": ROLES[i], **found[i]}
        if 1 <= i <= len(features):
            section["title"] = features[i - 1]
        sections.append(section)
    return sections


class CoreDetailWriter(DetailWriter):
    """core의 텍스트 모델(Gemma·luna)로 5칸 문구를 만든다. 형식이 깨지면 한 번 더 시도."""

    attempts = 2
    max_tokens = 900

    def write(self, product_name, message, features, style, text_quality="basic"):
        from just_make_it.core import TextGenerationError
        from just_make_it.core.copywriter import generate_text

        user_input = build_detail_input(product_name, message, features, style)
        last_error = ""
        for _ in range(self.attempts):
            try:
                result, _reason = generate_text(
                    DETAIL_RULES, user_input, text_quality, max_tokens=self.max_tokens
                )
                return parse_sections(result.text, features)
            except ValueError as exc:  # 형식 오류 → 다시 시도
                last_error = str(exc)
                logger.warning("상세페이지 문구 형식 오류: %s", exc)
            except TextGenerationError as exc:
                raise GeneratorError(str(exc)) from exc
            except Exception as exc:  # API 키 누락 등
                raise GeneratorError(f"{type(exc).__name__}: {exc}") from exc
        raise GeneratorError(last_error)


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
            sections = await asyncio.wait_for(
                asyncio.to_thread(
                    self.writer.write,
                    payload.product_name,
                    payload.message,
                    payload.features,
                    payload.style,
                    page.text_quality,
                ),
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
