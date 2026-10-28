"""서빙 API 엔드포인트. PM API 스펙(`docs/api_spec.md`)을 따른다."""

import asyncio
import io
import json

from fastapi import APIRouter, Header, HTTPException, Path, Query, Request, Response
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from .copywriter import CopyInputError, CopyWriter
from .detail_pages import (
    DetailPageBusyError,
    DetailPageNotFoundError,
    DetailPageService,
    SectionNotReadyError,
)
from .generators import GeneratorError
from .queue_manager import (
    ERROR_GENERIC,
    DailyLimitError,
    QueueFullError,
    QueueManager,
    run_with_deadline,
)
from .records import GenerationRecords
from .schemas import (
    EVENT_DETAIL_MAX_BYTES,
    IMAGE_QUALITY,
    TEXT_QUALITY,
    CopiesRequest,
    CopiesResponse,
    DetailPageRequest,
    DetailPageResponse,
    DetailPageStarted,
    EventRequest,
    FamilyResponse,
    GenerateRequest,
    GenerateSuccessResponse,
    GenerationResponse,
    GenerationSpec,
    GenerationStarted,
    HealthResponse,
    JobState,
    SectionRegenerateRequest,
    SectionRegenerateStarted,
    StatsResponse,
    TextEditRequest,
)
from .settings import ServingSettings

router = APIRouter()

MAX_REFERENCE_SIDE = 2048  # 업로드 사진은 이 크기 이하로 줄여 메모리를 아낀다
ALLOWED_REFERENCE_FORMATS = {"PNG", "JPEG", "WEBP"}
REQUIRED_TEXT_FIELDS = {"product_name", "message"}
# multipart 폼에서 같은 이름으로 여러 번(또는 JSON 배열 문자열로) 오는 목록 필드
LIST_FIELDS = {"adjustments", "features"}

MSG_REQUIRED = "상품 이름과 핵심 메시지는 꼭 입력해야 합니다."
MSG_NOT_FOUND = "결과를 찾을 수 없어요."
MSG_TOO_LARGE = "사진은 10MB 이하로 올려 주세요."
MSG_BAD_FORMAT = "참고 사진은 PNG, JPG, WEBP 파일만 사용할 수 있습니다."
MSG_DAILY_LIMIT = "오늘 만들 수 있는 횟수를 다 썼어요."
MSG_BUSY = "지금 요청이 많아요. 잠시 후 다시 시도해 주세요."
MSG_DETAIL_BUSY = "만들고 있는 상세페이지가 있어요. 끝나면 다시 시도해 주세요."
MSG_SECTION_BUSY = "아직 만들고 있어요. 다 만든 뒤에 다시 시도해 주세요."
MSG_EDIT_SIZE = "그림 크기가 원래 결과({width}×{height})와 달라요. 결과 화면에서 다시 저장해 주세요."
MSG_EDIT_FORMAT = "고친 그림은 PNG 파일만 저장할 수 있어요."
MSG_TEXT_NOT_READY = "아직 만들고 있는 결과예요. 다 만든 뒤에 고쳐 주세요."
MSG_TEXT_NO_BACKGROUND = "이 결과는 글자를 고칠 수 없어요. 다시 만들어 주세요."
MSG_SECTION_NO_TEXT = "문구를 만들지 못한 상세페이지예요. 처음부터 다시 만들어 주세요."
MSG_EVENT_BAD = "기록할 수 없는 요청이에요."


def _json_body_doc(model, example: dict) -> dict:
    """본문을 직접 읽는 엔드포인트도 Swagger(/docs)에 입력 칸이 보이게 한다.

    필수 문구가 비었을 때 422가 아니라 400을 돌려주려고 본문을 직접 검증하기 때문에,
    FastAPI가 자동으로 만들지 못하는 requestBody 문서를 여기서 채운다.
    """
    return {
        "required": True,
        "content": {
            "application/json": {
                "schema": model.model_json_schema(),
                "example": example,
            }
        },
    }


COPIES_EXAMPLE = {
    "product_name": "동네꽃집",
    "message": "주말 20% 할인",
    "style": "밝고 경쾌한",
    "text_model": "gemma-4-12b-it",
}
GENERATE_EXAMPLE = {
    "purpose": "instagram",
    "product_name": "소금빵",
    "message": "신메뉴 출시",
    "style": "따뜻한",
    "adjustments": [],
    "parent_id": None,
    "image_model": "flux2-klein-4b",
}
DETAIL_EXAMPLE = {
    "product_name": "수제 딸기잼",
    "message": "국산 딸기 100% 신상품",
    "features": ["무첨가", "소량 생산", "선물 포장"],
    "style": "따뜻한",
    "image_model": "flux2-klein-4b",
}


def _form_body_doc(model, example: dict) -> dict:
    """JSON 또는 multipart(참고 사진) 본문 문서."""
    doc = _json_body_doc(model, example)
    schema = model.model_json_schema()
    form_properties = dict(schema["properties"])
    form_properties["reference_image"] = {
        "type": "string",
        "format": "binary",
        "description": "상품 사진 (PNG·JPG·WEBP, 10MB 이하)",
    }
    doc["content"]["multipart/form-data"] = {
        "schema": {
            "type": "object",
            "properties": form_properties,
            "required": schema.get("required", []),
        }
    }
    return doc


def _manager(request: Request) -> QueueManager:
    return request.app.state.manager


def _settings(request: Request) -> ServingSettings:
    return request.app.state.settings


def _records(request: Request) -> GenerationRecords:
    return request.app.state.records


def _copywriter(request: Request) -> CopyWriter:
    return request.app.state.copywriter


def _detail_pages(request: Request) -> DetailPageService:
    return request.app.state.detail_pages


def _client_id(value: str | None) -> str:
    value = (value or "").strip()
    return value[:64] if value else "anonymous"


# ---------------------------------------------------------------------- /health
@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """서버 상태. docker healthcheck는 HTTP 200 여부만 본다."""
    manager = _manager(request)
    settings = _settings(request)
    return HealthResponse(
        status="ok" if manager.primary.is_ready else "degraded",
        image_backend=settings.image_backend,
        primary_model=manager.primary.name,
        primary_ready=manager.primary.is_ready,
        fallback_model=manager.fallback.name if manager.fallback else None,
        premium_model=manager.premium.name if manager.premium else None,
        models_loading=manager.models_loading,
        queue_length=manager.queue_length,
        running=manager.running_count,
        estimated_wait_seconds=round(manager.estimated_wait_for_new_job(), 1),
        seconds_per_job=round(manager.seconds_per_job, 2),
        jobs_today=manager.jobs_today.count,
        daily_job_limit=settings.daily_job_limit,
        extra_calls_today=manager.extra_today.count,
        extra_daily_limit=settings.extra_daily_limit,
        openai_cost_today_usd=round(manager.budget.spent, 4),
        openai_daily_budget_usd=settings.openai_daily_budget_usd,
        openai_blocked=not manager.api_allowed,
    )


# ---------------------------------------------------------------------- /copies
@router.post(
    "/copies",
    response_model=CopiesResponse,
    responses={400: {"description": "필수값 누락"}, 503: {"description": "생성 실패"}},
    openapi_extra={"requestBody": _json_body_doc(CopiesRequest, COPIES_EXAMPLE)},
)
async def copies(request: Request) -> CopiesResponse:
    """홍보 문구 후보를 최대 3개 추천한다."""
    body = await _read_json(request)
    payload = _validate(CopiesRequest, body)
    settings = _settings(request)
    try:
        # 시간이 지나면 core의 Gemma·luna 호출도 멈춘다 (core/deadline.py)
        result = await run_with_deadline(
            _copywriter(request).suggest,
            payload.product_name,
            payload.message,
            payload.style,
            _manager(request).text_quality(TEXT_QUALITY[payload.text_model]),
            timeout=settings.copy_timeout_seconds,
        )
    except CopyInputError as exc:
        raise HTTPException(status_code=400, detail=MSG_REQUIRED) from exc
    except (GeneratorError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail=ERROR_GENERIC) from exc
    return CopiesResponse(copies=result[:3])


# ---------------------------------------------------------------------- /generate
@router.post(
    "/generate",
    response_model=GenerateSuccessResponse,
    responses={
        400: {"description": "필수값 누락"},
        413: {"description": "사진 10MB 초과"},
        415: {"description": "PNG·JPG·WEBP가 아닌 사진"},
        429: {"description": "하루 생성 한도 초과"},
        503: {"description": "생성 실패 또는 요청 과다"},
    },
    openapi_extra={"requestBody": _form_body_doc(GenerateRequest, GENERATE_EXAMPLE)},
)
async def generate(
    request: Request,
    x_client_id: str | None = Header(default=None),
) -> GenerateSuccessResponse:
    """광고 이미지를 생성한다 (다시 만들기·수정 포함). **동기 응답**.

    - `application/json`, 참고 사진이 있으면 `multipart/form-data`(`reference_image`)
    - 서버가 문구를 얹은 최종 이미지(`image_url`)와 글자 없는 원본(`background_url`),
      얹은 위치·글꼴·크기(`text_layout`)를 함께 준다. 글자만 고칠 때는 `POST /generations/{id}/text`
    - `image_model`: `flux2-klein-4b`(빠르게, 로컬 GPU 대기열) /
      `openai-image-2.5-flare`(더 정교하게, OpenAI로 바로)
    - 로컬이 밀리거나 실패하면 서버가 OpenAI로 넘긴다 (`source`로 기록)
    - `parent_id`만 보내고 사진을 안 보내면 원본 결과의 참고 사진을 다시 쓴다
    - 기다리는 동안 진행 상황을 보여주려면 같은 본문으로 `POST /generations`(202 + 조회)를 쓴다
    """
    settings = _settings(request)
    manager = _manager(request)
    job = await _submit_generation(request, x_client_id)
    if not await manager.wait(job, settings.generate_wait_seconds):
        # 동기 응답은 프론트가 이 결과를 폴링하지 않아 끝까지 만들어도 아무도 못 본다 → 작업도 멈춘다
        # (대기 중이면 건너뛰고, 실행 중이면 core의 OpenAI·klein 호출을 끊음)
        manager.cancel(job, "generate_wait_timeout")
        raise HTTPException(status_code=503, detail=ERROR_GENERIC)
    if job.state == JobState.FAILED:
        status_code = 400 if job.input_error else 503
        return JSONResponse(status_code=status_code, content={"detail": job.error})
    return GenerateSuccessResponse.model_validate(job.result)


@router.post(
    "/generations",
    status_code=202,
    response_model=GenerationStarted,
    responses={
        400: {"description": "필수값 누락"},
        413: {"description": "사진 10MB 초과"},
        415: {"description": "PNG·JPG·WEBP가 아닌 사진"},
        429: {"description": "하루 생성 한도 초과"},
        503: {"description": "요청 과다 (대기열 가득 참)"},
    },
    openapi_extra={"requestBody": _form_body_doc(GenerateRequest, GENERATE_EXAMPLE)},
)
async def start_generation(
    request: Request,
    x_client_id: str | None = Header(default=None),
) -> GenerationStarted:
    """광고 이미지 생성을 시작한다. **비동기 (202)**, V3.

    - 본문·검사·라우팅은 `POST /generate`와 같다. 기다리지 않고 바로 `id`와 문구를 돌려준다
    - 프론트는 문구를 먼저 보여주고 `GET /generations/{id}`를 2초마다 조회한다
      (`progress`: 대기 순서·남은 예상 시간). `status`가 `success`·`error`가 되면 멈춘다
    - 동기 `/generate`와 달리 응답을 기다리다 작업을 취소하지 않는다 (나중에 조회해도 결과가 있음)
    """
    job = await _submit_generation(request, x_client_id)
    progress = _manager(request).progress(job.id)
    width, height = _image_size(job.spec.purpose)
    return GenerationStarted(
        id=job.id,
        message=job.spec.message,
        width=width,
        height=height,
        estimated_seconds=progress["estimated_seconds"] if progress else 0.0,
    )


async def _submit_generation(request: Request, x_client_id: str | None):
    """/generate와 /generations 공통: 본문 검사 → 대기열 접수. 접수한 작업을 돌려준다."""
    settings = _settings(request)
    body, reference = await _parse_form_body(request, settings)
    payload = _validate(GenerateRequest, body)
    _check_lengths(payload, settings)

    manager = _manager(request)
    spec = GenerationSpec(
        product_name=payload.product_name,
        message=payload.message,
        purpose=payload.purpose,
        style=payload.style,
        adjustments=payload.adjustments,
        reference_image=reference,
        text_quality=manager.text_quality(
            TEXT_QUALITY[payload.text_model]
            if payload.text_model
            else settings.generate_text_quality
        ),
    )
    # "더 정교하게"(OpenAI)는 로컬 GPU 대기열을 거치지 않는 프리미엄 경로로 보낸다
    use_api_model = IMAGE_QUALITY[payload.image_model] == "detailed"
    try:
        return await manager.submit(
            spec,
            premium=use_api_model,
            client_id=_client_id(x_client_id),
            parent_id=payload.parent_id,
        )
    except QueueFullError as exc:
        raise HTTPException(status_code=503, detail=MSG_BUSY) from exc
    except DailyLimitError as exc:
        raise HTTPException(status_code=429, detail=MSG_DAILY_LIMIT) from exc


def _image_size(purpose: str) -> tuple[int, int]:
    from just_make_it.core.prompt_builder import get_image_size

    return get_image_size(purpose)


# ---------------------------------------------------------------------- /generations
@router.get(
    "/generations/{generation_id}",
    response_model=GenerationResponse,
    responses={404: {"description": "없는 결과 id"}},
)
async def get_generation(request: Request, generation_id: str) -> GenerationResponse:
    """생성 결과를 다시 조회한다 (결과 화면 새로고침, 링크 공유, 비동기 생성 폴링). DB에 영구 보관.

    `processing`이면 `progress`(대기 순서·남은 예상 시간)를 함께 준다.
    """
    record = await asyncio.to_thread(_records(request).get, generation_id)
    if record is None:
        raise HTTPException(status_code=404, detail=MSG_NOT_FOUND)
    if record["status"] == "processing":
        record = {**record, "progress": _manager(request).progress(generation_id)}
    return GenerationResponse.model_validate(record)


@router.get(
    "/generations/{generation_id}/family",
    response_model=FamilyResponse,
    responses={404: {"description": "없는 결과 id (상세페이지 섹션 id 포함)"}},
)
async def get_family(request: Request, generation_id: str) -> FamilyResponse:
    """같은 원본에서 다시 만든 결과 목록 (api_spec_next 3, S2). 만든 순서.

    - `parent_id`를 거슬러 맨 처음 결과를 찾고 그 아래 모든 결과를 준다
    - 성공한 결과만, 최대 50개. 상세페이지 섹션은 제외. 혼자인 결과도 자기 1개가 온다
    """
    items = await asyncio.to_thread(_records(request).family, generation_id, 50)
    if items is None:
        raise HTTPException(status_code=404, detail=MSG_NOT_FOUND)
    return FamilyResponse(items=items)


@router.post(
    "/events",
    status_code=204,
    responses={
        400: {"description": "모르는 type, 없는 generation_id, detail 4KB 초과"}
    },
    openapi_extra={
        "requestBody": _json_body_doc(
            EventRequest,
            {
                "generation_id": "6f1c2b0e-...",
                "type": "download",
                "detail": {"edited": False},
            },
        )
    },
)
async def add_event(
    request: Request, x_client_id: str | None = Header(default=None)
) -> Response:
    """사용 기록 (api_spec_next 1, S4). 채택률 지표·다음 학습용 선호 데이터.

    - `type`: `download` 다운로드 · `copy_link` 링크 복사 · `remake` 다시 만들기 ·
      `edit_text` 글자 직접 고치기 시작 · `cutout` 배경 지우고 색 채우기 완료 · `pick_copy` 추천 문구 고름
    - `detail`: 추가 정보 (자유 형식, 4KB 이하). 누를 때마다 1건씩 쌓인다
    - `download`·`copy_link`이면 결과의 첫 다운로드 시각도 남긴다. 일일 생성 한도에 세지 않음
    - 화면 동작과 무관하므로 프론트는 실패해도 무시하면 된다
    """
    body = await _read_json(request)
    try:
        payload = EventRequest.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=MSG_EVENT_BAD) from exc
    if payload.detail is not None:
        size = len(json.dumps(payload.detail, ensure_ascii=False).encode())
        if size > EVENT_DETAIL_MAX_BYTES:
            raise HTTPException(status_code=400, detail=MSG_EVENT_BAD)
    added = await asyncio.to_thread(
        _records(request).add_event,
        payload.generation_id,
        _client_id(x_client_id),
        payload.type,
        payload.detail,
    )
    if not added:
        raise HTTPException(status_code=400, detail=MSG_EVENT_BAD)
    return Response(status_code=204)


@router.get("/stats", response_model=StatsResponse)
async def stats(
    request: Request, days: int = Query(default=7, ge=1, le=90)
) -> StatsResponse:
    """최근 `days`일(한국 날짜) 사용 지표 (S4, 발표용 채택률). 단일 이미지 결과만 (상세페이지 칸 제외).

    - `generated` 성공한 결과 수, `downloaded` 다운로드·링크 복사된 수,
      `edited` 글자 직접 고치기·배경 지우기를 한 수, `remade` 다시 만들기·조금 수정하기의 원본이 된 수
    - `*_rate`는 generated 대비 비율
    """
    rows = await asyncio.to_thread(_records(request).adoption_stats, days)
    daily = [_with_rates(row["day"], row) for row in rows]
    keys = ("generated", "downloaded", "edited", "remade")
    total = _with_rates("total", {k: sum(row[k] for row in rows) for k in keys})
    return StatsResponse(days=daily, total=total)


def _with_rates(day: str, row: dict) -> dict:
    generated = row["generated"] or 0

    def rate(key: str) -> float:
        return round((row[key] or 0) / generated, 3) if generated else 0.0

    return {
        "date": day,
        "generated": generated,
        "downloaded": row["downloaded"] or 0,
        "edited": row["edited"] or 0,
        "remade": row["remade"] or 0,
        "download_rate": rate("downloaded"),
        "edit_rate": rate("edited"),
        "remake_rate": rate("remade"),
    }


@router.post(
    "/generations/{generation_id}/text",
    response_model=GenerationResponse,
    responses={
        400: {"description": "문구가 빈 문자열"},
        404: {"description": "없는 결과 id"},
        409: {
            "description": "아직 processing·error인 결과, 또는 원본이 없는 예전 결과"
        },
        422: {"description": "위치·글꼴·크기 허용값 오류"},
    },
    openapi_extra={
        "requestBody": _json_body_doc(
            TextEditRequest,
            {
                "message": "이번 주말만 20% 할인",
                "position": "bottom",
                "font": "blackhan",
            },
        )
    },
)
async def edit_text(request: Request, generation_id: str) -> GenerationResponse:
    """글자(문구·위치·글꼴·크기)만 바꿔 원본 이미지에 다시 얹는다. **이미지 재생성 없음**.

    - 보낸 필드만 바꾸고 나머지는 지금 값 유지. 일일 생성 한도에 세지 않음
    - 분위기(`style`)별 색·테두리·장식은 그대로, 글꼴에 없는 글자가 있으면 `dodum`으로 대신 씀
      → 응답 `text_layout.font`가 실제로 쓴 값
    - 응답 `image_url`은 새 주소 (브라우저 캐시 회피)
    """
    body = await _read_json(request)
    if isinstance(body.get("message"), str) and not body["message"].strip():
        raise HTTPException(status_code=400, detail="문구를 입력해 주세요.")
    payload = _validate(TextEditRequest, body)
    settings = _settings(request)
    if payload.message and len(payload.message) > settings.max_message_chars:
        raise HTTPException(
            status_code=422,
            detail=f"문구는 {settings.max_message_chars}자 이하로 입력해 주세요.",
        )

    records = _records(request)
    record = await asyncio.to_thread(records.get, generation_id)
    if record is None:
        raise HTTPException(status_code=404, detail=MSG_NOT_FOUND)
    if record["status"] != "success":
        raise HTTPException(status_code=409, detail=MSG_TEXT_NOT_READY)
    background = await asyncio.to_thread(records.background, generation_id)
    if background is None:
        raise HTTPException(status_code=409, detail=MSG_TEXT_NO_BACKGROUND)

    current = record.get("text_layout") or {}
    changes = payload.model_dump(exclude_none=True, exclude={"message"})
    layout = {"size_scale": 1.0, **current, **changes}
    message = payload.message.strip() if payload.message else record["message"]
    try:
        image, actual = await asyncio.to_thread(
            _render_text,
            background,
            message,
            record["input"].get("style"),
            layout["size_scale"],
            layout.get("position"),
            layout.get("font"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="입력값을 확인해 주세요.") from exc
    updated = await asyncio.to_thread(
        records.update_text, generation_id, image, message=message, text_layout=actual
    )
    return GenerationResponse.model_validate(updated)


def _render_text(background, message, style, size_scale, position, font):
    """core 글자 얹기 (PIL, 1초 이내). GPU·OpenAI 호출 없음."""
    from just_make_it.core import render_text

    return render_text(
        background,
        message,
        style,
        size_scale=size_scale,
        position=position,
        font=font,
    )


@router.post(
    "/generations/{generation_id}/image",
    response_model=GenerationResponse,
    responses={
        400: {"description": "그림 크기가 원래 결과와 다름"},
        404: {"description": "없는 결과 id"},
        409: {"description": "아직 processing·error인 결과"},
        413: {"description": "그림 10MB 초과"},
        415: {"description": "PNG가 아닌 그림"},
        422: {"description": "image 없음, 문구가 너무 김"},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "image": {
                                "type": "string",
                                "format": "binary",
                                "description": "글자까지 얹은 최종 그림. PNG, 원래 결과와 같은 크기",
                            },
                            "background": {
                                "type": "string",
                                "format": "binary",
                                "description": "글자 없는 그림 (배경을 지웠을 때). 보내면 background_url도 바뀜",
                            },
                            "message": {
                                "type": "string",
                                "description": "그림에 얹은 문구 (보내면 응답 message가 바뀜)",
                            },
                        },
                        "required": ["image"],
                    }
                }
            },
        }
    },
)
async def save_edited_image(request: Request, generation_id: str) -> GenerationResponse:
    """브라우저에서 고친 그림을 서버에 저장한다 (api_spec_next 2, S7). 재생성 없음.

    - 배경 지우기·글자 직접 고치기 결과를 올리면 `image_url`이 그 그림으로 바뀐다
      → 링크 공유·다시 조회해도 고친 그림이 보인다. 응답·조회에 `edited: true`
    - `background`(글자 없는 그림)를 보내면 `background_url`도 바뀌어,
      이후 `POST /generations/{id}/text`가 지운 배경 위에 글자를 얹는다
    - 응답 `image_url`은 새 주소 (캐시 회피). 처음 결과 파일은 예전 링크용으로 남김
    - 일일 생성 한도에 세지 않음
    """
    settings = _settings(request)
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("multipart/form-data"):
        raise HTTPException(
            status_code=422, detail="그림은 multipart/form-data로 보내 주세요."
        )
    form = await request.form()
    upload = form.get("image")
    if not isinstance(upload, UploadFile) or not upload.filename:
        raise HTTPException(status_code=422, detail="저장할 그림이 없어요.")
    background_upload = form.get("background")
    if not isinstance(background_upload, UploadFile) or not background_upload.filename:
        background_upload = None
    message = form.get("message")
    message = message.strip() if isinstance(message, str) else ""
    if len(message) > settings.max_message_chars:
        raise HTTPException(
            status_code=422,
            detail=f"문구는 {settings.max_message_chars}자 이하로 입력해 주세요.",
        )

    records = _records(request)
    record = await asyncio.to_thread(records.get, generation_id)
    if record is None:
        raise HTTPException(status_code=404, detail=MSG_NOT_FOUND)
    if record["status"] != "success":
        raise HTTPException(status_code=409, detail=MSG_TEXT_NOT_READY)

    image = await _read_edited_png(upload, settings, record)
    background = (
        await _read_edited_png(background_upload, settings, record)
        if background_upload is not None
        else None
    )
    updated = await asyncio.to_thread(
        records.replace_image,
        generation_id,
        image,
        background=background,
        message=message or None,
    )
    return GenerationResponse.model_validate(updated)


async def _read_edited_png(
    upload: UploadFile, settings: ServingSettings, record: dict
) -> bytes:
    """올린 그림 검사: PNG만(415), 10MB 이하(413), 원래 결과와 같은 크기(400). 바이트 그대로 저장."""
    data = await upload.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=MSG_TOO_LARGE)
    try:
        image = Image.open(io.BytesIO(data))
        image_format = image.format
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=415, detail=MSG_EDIT_FORMAT) from exc
    if image_format != "PNG":
        raise HTTPException(status_code=415, detail=MSG_EDIT_FORMAT)
    width, height = record.get("width"), record.get("height")
    if width and height and image.size != (width, height):
        raise HTTPException(
            status_code=400, detail=MSG_EDIT_SIZE.format(width=width, height=height)
        )
    return data


# ---------------------------------------------------------------------- /detail-pages
@router.post(
    "/detail-pages",
    status_code=202,
    response_model=DetailPageStarted,
    responses={
        400: {"description": "필수값 누락"},
        409: {"description": "이 사용자의 상세페이지가 이미 진행 중"},
        413: {"description": "사진 10MB 초과"},
        415: {"description": "PNG·JPG·WEBP가 아닌 사진"},
        429: {"description": "하루 생성 한도 초과"},
    },
    openapi_extra={"requestBody": _form_body_doc(DetailPageRequest, DETAIL_EXAMPLE)},
)
async def start_detail_page(
    request: Request,
    x_client_id: str | None = Header(default=None),
) -> DetailPageStarted:
    """상세페이지(5칸: 대표 · 좋은 점 ×3 · 마무리) 생성을 시작한다. **비동기 (202)**.

    - 바로 `id`를 돌려주고, 문구·이미지는 뒤에서 만든다. `GET /detail-pages/{id}`를 2초마다 조회
    - `features`를 비우면 텍스트 모델이 특징을 만든다 (최대 3개)
    - 섹션 이미지는 글자 없이 만들고, 각 칸의 `title`·`body`를 프론트가 얹는다
    - 사용자(`X-Client-Id`)당 진행 중인 상세페이지는 1개 (`409`)
    """
    settings = _settings(request)
    body, reference = await _parse_form_body(request, settings)
    payload = _validate(DetailPageRequest, body)
    _check_lengths(payload, settings)
    for feature in payload.features:
        if len(feature) > settings.max_feature_chars:
            raise HTTPException(
                status_code=422,
                detail=f"상품 특징은 {settings.max_feature_chars}자 이하로 입력해 주세요.",
            )
    try:
        pid = await _detail_pages(request).start(
            payload, reference, _client_id(x_client_id)
        )
    except DetailPageBusyError as exc:
        raise HTTPException(status_code=409, detail=MSG_DETAIL_BUSY) from exc
    except DailyLimitError as exc:
        raise HTTPException(status_code=429, detail=MSG_DAILY_LIMIT) from exc
    return DetailPageStarted(id=pid)


@router.get(
    "/detail-pages/{page_id}",
    response_model=DetailPageResponse,
    responses={404: {"description": "없는 상세페이지 id"}},
)
async def get_detail_page(request: Request, page_id: str) -> DetailPageResponse:
    """상세페이지 진행 상황·결과. 칸이 끝나는 대로 `sections`가 채워진다."""
    page = await asyncio.to_thread(_records(request).get_detail_page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail=MSG_NOT_FOUND)
    return DetailPageResponse.model_validate(page)


@router.post(
    "/detail-pages/{page_id}/sections/{index}",
    status_code=202,
    response_model=SectionRegenerateStarted,
    responses={
        404: {"description": "없는 상세페이지 id 또는 칸 번호"},
        409: {"description": "페이지 또는 그 칸을 아직 만드는 중"},
        429: {"description": "하루 생성 한도 초과"},
    },
    openapi_extra={
        "requestBody": {
            **_json_body_doc(SectionRegenerateRequest, {"adjustments": ["더 밝게"]}),
            "required": False,
        }
    },
)
async def regenerate_section(
    request: Request,
    page_id: str,
    index: int = Path(ge=0, le=4),
) -> SectionRegenerateStarted:
    """섹션 1칸의 이미지만 다시 만든다 (문구는 그대로). **비동기 (202)**.

    - `adjustments`: "조금 수정하기" 칩. 칩이 있으면 직전 이미지의 구도를 유지한다
    - 페이지가 아직 `processing`이거나 그 칸이 만드는 중이면 `409`
    """
    body = await _read_json(request) if await request.body() else {}
    payload = _validate(SectionRegenerateRequest, body)
    try:
        await _detail_pages(request).regenerate(page_id, index, payload.adjustments)
    except DetailPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=MSG_NOT_FOUND) from exc
    except SectionNotReadyError as exc:
        detail = MSG_SECTION_NO_TEXT if str(exc) == "no_text" else MSG_SECTION_BUSY
        raise HTTPException(status_code=409, detail=detail) from exc
    except DailyLimitError as exc:
        raise HTTPException(status_code=429, detail=MSG_DAILY_LIMIT) from exc
    return SectionRegenerateStarted(id=page_id, index=index)


# ---------------------------------------------------------------------- 보조 함수
def _validate(model, body: dict):
    """필수 문구가 비었으면 400, 그 밖의 타입·허용값 오류는 422 (스펙 4장)."""
    try:
        return model.model_validate(body)
    except ValidationError as exc:
        missing = {
            str(err["loc"][0])
            for err in exc.errors()
            if err["loc"] and str(err["loc"][0]) in REQUIRED_TEXT_FIELDS
        }
        if missing:
            raise HTTPException(status_code=400, detail=MSG_REQUIRED) from exc
        fields = sorted({".".join(str(p) for p in err["loc"]) for err in exc.errors()})
        raise HTTPException(
            status_code=422, detail=f"입력값을 확인해 주세요: {', '.join(fields)}"
        ) from exc


async def _read_json(request: Request) -> dict:
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=422, detail="JSON 형식이 올바르지 않아요."
        ) from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="요청 본문은 객체여야 해요.")
    return body


async def _parse_form_body(
    request: Request, settings: ServingSettings
) -> tuple[dict, bytes | None]:
    """JSON이면 그대로, multipart면 폼 필드 + 참고 사진(`reference_image`)."""
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith(
        ("multipart/form-data", "application/x-www-form-urlencoded")
    ):
        return await _read_json(request), None

    form = await request.form()
    body: dict = {}
    lists: dict[str, list[str]] = {}
    reference: bytes | None = None
    for key, value in form.multi_items():
        if key == "reference_image":
            if isinstance(value, UploadFile) and value.filename:
                reference = await _read_reference(value, settings)
        elif key in LIST_FIELDS and isinstance(value, str):
            lists.setdefault(key, []).extend(_split_list(value))
        elif isinstance(value, str):
            body[key] = value
    body.update({key: values for key, values in lists.items() if values})
    return body, reference


def _split_list(value: str) -> list[str]:
    """폼의 목록 필드는 같은 이름을 여러 번 보내거나 JSON 배열 문자열로 보낸다."""
    value = value.strip()
    if value.startswith("["):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return [v for v in parsed if isinstance(v, str)]
    return [value] if value else []


async def _read_reference(upload: UploadFile, settings: ServingSettings) -> bytes:
    data = await upload.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=MSG_TOO_LARGE)
    try:
        image = Image.open(io.BytesIO(data))
        image_format = image.format
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=415, detail=MSG_BAD_FORMAT) from exc
    if image_format not in ALLOWED_REFERENCE_FORMATS:
        raise HTTPException(status_code=415, detail=MSG_BAD_FORMAT)

    # core가 받는 PNG로 통일하고 너무 큰 사진은 줄인다
    image = image.convert("RGBA" if image.mode in ("RGBA", "LA", "P") else "RGB")
    image.thumbnail((MAX_REFERENCE_SIDE, MAX_REFERENCE_SIDE))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _check_lengths(
    payload: GenerateRequest | DetailPageRequest, settings: ServingSettings
) -> None:
    if len(payload.product_name) > settings.max_product_name_chars:
        raise HTTPException(
            status_code=422,
            detail=f"가게/상품 이름은 {settings.max_product_name_chars}자 이하로 입력해 주세요.",
        )
    if len(payload.message) > settings.max_message_chars:
        raise HTTPException(
            status_code=422,
            detail=f"핵심 메시지는 {settings.max_message_chars}자 이하로 입력해 주세요.",
        )
