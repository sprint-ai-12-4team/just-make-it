"""서빙 API 요청·응답 스키마.

필드명과 값은 PM API 스펙(`docs/api_spec.md`)과 core `generate_ad_image()` 인자에 맞춘다.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Purpose = Literal["instagram", "commerce", "youtube", "kakao", "free"]
# 실제로 이미지를 만든 곳: openai(OpenAI API), local(VM 모델), mock(개발용). 통계용
Source = Literal["local", "openai", "mock"]
# 서버가 고른 경로: primary(기본), fallback(대기·장애 우회), premium(유저 선택). 통계용
Route = Literal["primary", "fallback", "premium"]
# 프론트가 고르는 모델 (api_spec 1·3장). 화면에는 "빠르게 / 더 정교하게"로만 보인다
ImageModel = Literal["flux2-klein-4b", "openai-image-2.5-flare"]
TextModel = Literal["gemma-4-12b-it", "openai-gpt-5.6-luna"]
# 프론트 모델 이름 → core 파이프라인 V1의 품질 값
IMAGE_QUALITY: dict[str, str] = {
    "flux2-klein-4b": "fast",
    "openai-image-2.5-flare": "detailed",
}
TEXT_QUALITY: dict[str, str] = {
    "gemma-4-12b-it": "basic",
    "openai-gpt-5.6-luna": "natural",
}


def _strip_text(value: object) -> object:
    # 검증 전에 공백을 지워서 "   " 같은 입력이 필수값 검사를 통과하지 못하게 한다
    if isinstance(value, str):
        return value.strip() or None
    return value


def _clean_list(value: object) -> object:
    # 칩·특징 목록의 빈 값을 버린다
    if isinstance(value, list):
        return [v.strip() for v in value if isinstance(v, str) and v.strip()]
    return value


class GenerateRequest(BaseModel):
    """POST /generate 요청 본문 (JSON 또는 multipart 폼 필드).

    `generation_mode`는 스펙에서 삭제됐다 (글자는 항상 프론트가 얹음).
    예전 프론트가 보내더라도 모르는 필드는 무시한다.
    """

    purpose: Purpose
    product_name: str
    message: str
    style: str | None = None
    # 결과 화면의 "조금 수정하기" 칩 (예: ["더 밝게", "텍스트 짧게"])
    adjustments: list[str] = Field(default_factory=list, max_length=10)
    # 다시 만들기·수정할 때 원본 결과의 id
    parent_id: str | None = Field(default=None, max_length=64)
    # 그림 품질. klein = 빠르게(로컬, 기본), flare = 더 정교하게(OpenAI)
    image_model: ImageModel = "flux2-klein-4b"
    # 영어 묘사·"텍스트 짧게"에 쓸 문구 모델. 비우면 서버 설정(GENERATE_TEXT_QUALITY)
    text_model: TextModel | None = None

    _strip = field_validator("product_name", "message", "style", mode="before")(
        _strip_text
    )

    _clean = field_validator("adjustments", mode="before")(_clean_list)


class CopiesRequest(BaseModel):
    """POST /copies 요청 본문."""

    product_name: str
    message: str
    style: str | None = None
    # 문구 품질. gemma = 기본(로컬), luna = 더 자연스럽게(OpenAI)
    text_model: TextModel = "gemma-4-12b-it"

    _strip = field_validator("product_name", "message", "style", mode="before")(
        _strip_text
    )


class CopiesResponse(BaseModel):
    copies: list[str]


class JobState(StrEnum):
    """작업 내부 상태. API에는 processing / success / error 세 가지로 보인다."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "success"
    FAILED = "error"


class GenerateSuccessResponse(BaseModel):
    """생성 완료 (POST /generate 200)."""

    id: str
    status: Literal["success"] = "success"
    image_url: str
    # 실제로 쓴 문구 ("텍스트 짧게"를 누르면 줄어든 문구). 프론트가 이미지 위에 얹는다
    message: str
    source: Source
    width: int
    height: int


class GenerationInput(BaseModel):
    purpose: str
    product_name: str
    message: str
    style: str | None = None
    adjustments: list[str] = Field(default_factory=list)


class GenerationResponse(BaseModel):
    """결과 조회 (GET /generations/{id}). DB(service/db.py)가 돌려주는 모양 그대로."""

    id: str
    status: Literal["processing", "success", "error"]
    image_url: str | None = None
    message: str | None = None
    source: Source | None = None
    width: int | None = None
    height: int | None = None
    parent_id: str | None = None
    created_at: str
    input: GenerationInput


class DetailPageRequest(BaseModel):
    """POST /detail-pages 요청 본문 (JSON 또는 multipart 폼 필드)."""

    product_name: str
    message: str
    # 상품 특징 (최대 3개). 비우면 텍스트 모델이 상품·메시지에 맞게 만든다
    features: list[str] = Field(default_factory=list, max_length=3)
    style: str | None = None
    # 섹션 이미지 품질. 섹션 다시 만들기도 이 값을 그대로 쓴다
    image_model: ImageModel = "flux2-klein-4b"
    # 섹션 문구 품질. 비우면 서버 설정(GENERATE_TEXT_QUALITY)
    text_model: TextModel | None = None

    _strip = field_validator("product_name", "message", "style", mode="before")(
        _strip_text
    )

    _clean = field_validator("features", mode="before")(_clean_list)


class DetailPageStarted(BaseModel):
    """상세페이지 접수 (POST /detail-pages 202)."""

    id: str
    status: Literal["processing"] = "processing"


class SectionRegenerateRequest(BaseModel):
    """POST /detail-pages/{id}/sections/{index} 요청 본문."""

    adjustments: list[str] = Field(default_factory=list, max_length=10)

    _clean = field_validator("adjustments", mode="before")(_clean_list)


class SectionRegenerateStarted(BaseModel):
    """섹션 다시 만들기 접수 (202). 결과는 GET /detail-pages/{id}로 확인."""

    id: str
    index: int
    status: Literal["processing"] = "processing"


class DetailSection(BaseModel):
    index: int
    role: Literal["hero", "feature", "closing"]
    status: Literal["pending", "processing", "success", "error"]
    title: str | None = None
    body: str | None = None
    image_url: str | None = None
    source: Source | None = None


class DetailProgress(BaseModel):
    done: int
    total: int


class DetailPageResponse(BaseModel):
    """상세페이지 조회 (GET /detail-pages/{id}). DB(service/db.py)가 돌려주는 모양 그대로."""

    id: str
    status: Literal["processing", "success", "error"]
    progress: DetailProgress
    sections: list[DetailSection]
    created_at: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    image_backend: str
    primary_model: str
    primary_ready: bool
    fallback_model: str | None
    premium_model: str | None
    models_loading: bool
    queue_length: int
    running: int
    estimated_wait_seconds: float
    seconds_per_job: float
    jobs_today: int
    daily_job_limit: int
    extra_calls_today: int
    extra_daily_limit: int


@dataclass
class GenerationSpec:
    """생성기에 넘기는 작업 명세 (core.generate_ad_image 인자와 같다)."""

    product_name: str
    message: str
    purpose: str = "free"
    style: str | None = None
    adjustments: list[str] = field(default_factory=list)
    reference_image: bytes | None = None
    # core V1 문구 품질 (basic / natural)
    text_quality: str = "basic"
    # 조금 수정하기 때 원본의 시드를 넘기면 구도가 유지된다 (klein만 적용, flare는 무시)
    seed: int | None = None


@dataclass
class GenerationOutput:
    """생성기 결과."""

    image_bytes: bytes  # 글자 없는 PNG (문구는 프론트가 얹음)
    message: str
    model: str
    width: int
    height: int
    prompt: str | None = None
    # 실제로 이미지를 만든 곳. 비우면 생성기 기본값 (core가 내부에서 폴백하면 바뀜)
    source: Source | None = None
    # core가 로컬 모델 대신 API 모델을 쓴 이유 (예: klein 실패로 flare 사용)
    fallback_reason: str = ""
    cost_usd: float | None = None
    seed: int | None = None
    text_ms: int | None = None
    # DB params_json에 남길 재현·분석용 값 (text_model, product_source 등)
    params: dict = field(default_factory=dict)
