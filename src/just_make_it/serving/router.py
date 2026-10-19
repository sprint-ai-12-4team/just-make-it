"""서빙 API 엔드포인트."""

import io
import json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from .queue_manager import DailyLimitError, Job, QueueFullError, QueueManager
from .schemas import (
    GenerateProcessingResponse,
    GenerateRequest,
    GenerateSuccessResponse,
    GenerationSpec,
    HealthResponse,
    JobFailedResponse,
    JobState,
)
from .settings import ServingSettings

router = APIRouter()

MAX_REFERENCE_SIDE = 2048  # 업로드 사진은 이 크기 이하로 줄여 메모리를 아낀다


def _manager(request: Request) -> QueueManager:
    return request.app.state.manager


def _settings(request: Request) -> ServingSettings:
    return request.app.state.settings


# ---------------------------------------------------------------------- /generate
@router.post(
    "/generate",
    responses={
        200: {"model": GenerateSuccessResponse, "description": "대기 시간 안에 완료"},
        202: {"model": GenerateProcessingResponse, "description": "아직 생성 중"},
        422: {"description": "입력 오류"},
        429: {"description": "하루 생성 한도 도달"},
        502: {"model": JobFailedResponse, "description": "생성 실패"},
        503: {"description": "대기열 가득 참"},
    },
)
async def generate(
    request: Request,
    wait: float | None = Query(
        default=None,
        ge=0,
        description="결과를 기다려 줄 최대 시간(초). 0이면 바로 job_id를 반환",
    ),
):
    """광고 이미지 생성을 요청한다.

    - `application/json` 또는 `multipart/form-data`(참고 사진 `reference_image` 포함)
    - `wait`초 안에 끝나면 `success`, 아니면 202 `processing` + `job_id`를 반환한다.
      이후 `GET /jobs/{job_id}`로 상태를 조회한다.
    """
    settings = _settings(request)
    body, reference = await _parse_body(request, settings)

    try:
        payload = GenerateRequest.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_validation_message(exc)) from exc
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
        job = await manager.submit(spec, premium=payload.premium)
    except QueueFullError as exc:
        raise HTTPException(
            status_code=503, detail="지금 요청이 많아요. 잠시 후 다시 시도해 주세요."
        ) from exc
    except DailyLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail="오늘 만들 수 있는 횟수를 다 썼어요. 내일 다시 이용해 주세요.",
        ) from exc

    timeout = settings.generate_wait_seconds if wait is None else wait
    await manager.wait(job, min(timeout, settings.generate_wait_seconds))
    return _job_response(manager, job, for_generate=True)


# ---------------------------------------------------------------------- /jobs/{id}
@router.get(
    "/jobs/{job_id}",
    response_model=GenerateSuccessResponse
    | GenerateProcessingResponse
    | JobFailedResponse,
)
async def get_job(request: Request, job_id: str):
    """작업 상태를 조회한다. 프론트는 1~2초 간격으로 폴링한다."""
    manager = _manager(request)
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없어요.")
    return _job_response(manager, job, for_generate=False)


# ---------------------------------------------------------------------- /health
@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
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


# ---------------------------------------------------------------------- 보조 함수
def _job_response(manager: QueueManager, job: Job, *, for_generate: bool):
    if job.state == JobState.SUCCEEDED:
        return GenerateSuccessResponse(
            job_id=job.id,
            image_url=job.image_url or "",
            generation_source=job.source or "local",
            route=job.route,
            message=job.message or job.spec.message,
            model=job.model or "",
        )
    if job.state == JobState.FAILED:
        body = JobFailedResponse(job_id=job.id, error=job.error or "")
        if for_generate:
            return JSONResponse(status_code=502, content=body.model_dump())
        return body

    body = GenerateProcessingResponse(
        job_id=job.id,
        stage="running" if job.state == JobState.RUNNING else "queued",
        queue_position=manager.queue_position(job),
        estimated_wait_seconds=manager.estimated_wait(job),
    )
    if for_generate:
        return JSONResponse(status_code=202, content=body.model_dump())
    return body


async def _parse_body(
    request: Request, settings: ServingSettings
) -> tuple[dict, bytes | None]:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith(
        ("multipart/form-data", "application/x-www-form-urlencoded")
    ):
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

    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=422, detail="JSON 형식이 올바르지 않아요."
        ) from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="요청 본문은 객체여야 해요.")
    return body, None


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
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=422, detail=f"사진은 {limit_mb}MB 이하만 올릴 수 있어요."
        )
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(
            status_code=422, detail="사진 파일을 읽을 수 없어요."
        ) from exc

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


def _validation_message(exc: ValidationError) -> str:
    fields = sorted({".".join(str(p) for p in err["loc"]) for err in exc.errors()})
    return f"입력값을 확인해 주세요: {', '.join(fields)}"
