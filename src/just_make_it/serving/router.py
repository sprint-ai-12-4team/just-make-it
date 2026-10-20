"""서빙 API 엔드포인트. PM API 스펙(`docs/api_spec.md`)을 따른다."""

import asyncio
import io
import json

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from .copywriter import CopyInputError, CopyWriter
from .generators import GeneratorError
from .queue_manager import (
    ERROR_GENERIC,
    DailyLimitError,
    Job,
    QueueFullError,
    QueueManager,
)
from .schemas import (
    CopiesRequest,
    CopiesResponse,
    GenerateProcessingResponse,
    GenerateRequest,
    GenerateSuccessResponse,
    GenerationInput,
    GenerationResponse,
    GenerationSpec,
    HealthResponse,
    JobState,
)
from .settings import ServingSettings

router = APIRouter()

MAX_REFERENCE_SIDE = 2048  # 업로드 사진은 이 크기 이하로 줄여 메모리를 아낀다
ALLOWED_REFERENCE_FORMATS = {"PNG", "JPEG", "WEBP"}
REQUIRED_TEXT_FIELDS = {"product_name", "message"}

MSG_REQUIRED = "상품 이름과 핵심 메시지는 꼭 입력해야 합니다."
MSG_NOT_FOUND = "결과를 찾을 수 없어요."
MSG_TOO_LARGE = "사진은 10MB 이하로 올려 주세요."
MSG_BAD_FORMAT = "참고 사진은 PNG, JPG, WEBP 파일만 사용할 수 있습니다."
MSG_DAILY_LIMIT = "오늘 만들 수 있는 횟수를 다 썼어요."
MSG_BUSY = "지금 요청이 많아요. 잠시 후 다시 시도해 주세요."


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
}
GENERATE_EXAMPLE = {
    "purpose": "instagram",
    "product_name": "소금빵",
    "message": "신메뉴 출시",
    "generation_mode": "quick",
    "style": "따뜻한",
    "adjustments": [],
    "parent_id": None,
}


def _generate_body_doc() -> dict:
    doc = _json_body_doc(GenerateRequest, GENERATE_EXAMPLE)
    schema = GenerateRequest.model_json_schema()
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


def _copywriter(request: Request) -> CopyWriter:
    return request.app.state.copywriter


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
        queue_length=manager.queue_length,
        running=manager.running_count,
        estimated_wait_seconds=round(manager.estimated_wait_for_new_job(), 1),
        seconds_per_job=round(manager.seconds_per_job, 2),
        jobs_today=manager.jobs_today.count,
        daily_job_limit=settings.daily_job_limit,
        extra_calls_today=manager.extra_today.count,
        extra_daily_limit=settings.extra_daily_limit,
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
        result = await asyncio.wait_for(
            asyncio.to_thread(
                _copywriter(request).suggest,
                payload.product_name,
                payload.message,
                payload.style,
            ),
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
    responses={
        200: {"model": GenerateSuccessResponse, "description": "생성 완료"},
        202: {"model": GenerateProcessingResponse, "description": "아직 생성 중"},
        400: {"description": "필수값 누락"},
        413: {"description": "사진 10MB 초과"},
        415: {"description": "PNG·JPG·WEBP가 아닌 사진"},
        429: {"description": "하루 생성 한도 초과"},
        503: {"description": "생성 실패 또는 요청 과다"},
    },
    openapi_extra={"requestBody": _generate_body_doc()},
)
async def generate(
    request: Request,
    x_client_id: str | None = Header(default=None),
    wait: float | None = Query(
        default=None,
        ge=0,
        description="결과를 기다려 줄 최대 시간(초). 0이면 바로 202 + id",
    ),
):
    """광고 이미지를 생성한다 (다시 만들기·수정 포함).

    - `application/json`, 참고 사진이 있으면 `multipart/form-data`(`reference_image`)
    - 기본은 동기 응답. 대기열이 길어 `wait`초 안에 끝나지 않으면 202 + `id`를 주고,
      프론트는 `GET /generations/{id}`로 확인한다.
    """
    settings = _settings(request)
    body, reference = await _parse_generate_body(request, settings)
    payload = _validate(GenerateRequest, body)
    _check_lengths(payload, settings)

    spec = GenerationSpec(
        product_name=payload.product_name,
        message=payload.message,
        purpose=payload.purpose,
        style=payload.style,
        generation_mode=payload.generation_mode,
        adjustments=payload.adjustments,
        reference_image=reference,
    )

    manager = _manager(request)
    try:
        job = await manager.submit(
            spec,
            premium=payload.premium,
            client_id=_client_id(x_client_id),
            parent_id=payload.parent_id,
        )
    except QueueFullError as exc:
        raise HTTPException(status_code=503, detail=MSG_BUSY) from exc
    except DailyLimitError as exc:
        raise HTTPException(status_code=429, detail=MSG_DAILY_LIMIT) from exc

    timeout = settings.generate_wait_seconds if wait is None else wait
    await manager.wait(job, min(timeout, settings.generate_wait_seconds))

    if job.state == JobState.SUCCEEDED:
        return _success(job)
    if job.state == JobState.FAILED:
        status_code = 400 if job.input_error else 503
        return JSONResponse(status_code=status_code, content={"detail": job.error})
    processing = GenerateProcessingResponse(
        id=job.id,
        queue_position=manager.queue_position(job),
        estimated_wait_seconds=manager.estimated_wait(job),
    )
    return JSONResponse(status_code=202, content=processing.model_dump())


# ---------------------------------------------------------------------- /generations
@router.get("/generations/{generation_id}", response_model=GenerationResponse)
async def get_generation(request: Request, generation_id: str) -> GenerationResponse:
    """생성 결과를 다시 조회한다. 폴링 간격은 1~2초를 권장한다.

    DB가 붙기 전까지는 완료 후 1시간 동안만 메모리에 보관한다.
    """
    manager = _manager(request)
    job = manager.get(generation_id)
    if job is None:
        raise HTTPException(status_code=404, detail=MSG_NOT_FOUND)

    spec = job.spec
    response = GenerationResponse(
        id=job.id,
        status="processing",
        route=job.route,
        parent_id=job.parent_id,
        created_at=job.created_at,
        input=GenerationInput(
            purpose=spec.purpose,
            product_name=spec.product_name,
            message=spec.message,
            generation_mode=spec.generation_mode,
            style=spec.style,
            adjustments=spec.adjustments,
        ),
    )
    if job.state == JobState.SUCCEEDED:
        response.status = "success"
        response.image_url = job.image_url
        response.message = job.message
        response.source = job.source
        response.width, response.height = job.width, job.height
    elif job.state == JobState.FAILED:
        response.status = "error"
        response.error = job.error
    else:
        response.queue_position = manager.queue_position(job)
        response.estimated_wait_seconds = manager.estimated_wait(job)
    return response


# ---------------------------------------------------------------------- 보조 함수
def _success(job: Job) -> GenerateSuccessResponse:
    return GenerateSuccessResponse(
        id=job.id,
        image_url=job.image_url or "",
        message=job.message or job.spec.message,
        source=job.source or "local",
        width=job.width or 0,
        height=job.height or 0,
        route=job.route,
    )


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


async def _parse_generate_body(
    request: Request, settings: ServingSettings
) -> tuple[dict, bytes | None]:
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith(
        ("multipart/form-data", "application/x-www-form-urlencoded")
    ):
        return await _read_json(request), None

    form = await request.form()
    body: dict = {}
    adjustments: list[str] = []
    reference: bytes | None = None
    for key, value in form.multi_items():
        if key == "reference_image":
            if isinstance(value, UploadFile) and value.filename:
                reference = await _read_reference(value, settings)
        elif key == "adjustments" and isinstance(value, str):
            adjustments.extend(_split_adjustments(value))
        elif isinstance(value, str):
            body[key] = value
    if adjustments:
        body["adjustments"] = adjustments
    return body, reference


def _split_adjustments(value: str) -> list[str]:
    """폼의 adjustments는 같은 이름을 여러 번 보내거나 JSON 배열 문자열로 보낸다."""
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


def _check_lengths(payload: GenerateRequest, settings: ServingSettings) -> None:
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
