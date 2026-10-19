"""서빙 API 요청·응답 스키마.

필드명은 프론트엔드 `frontend/lib/types.ts`와 core `generate_ad_image()` 인자에 맞춘다.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Purpose = Literal["instagram", "commerce", "youtube", "kakao", "free"]
GenerationMode = Literal["quick", "template", "canvas"]
# 실제로 이미지를 만든 곳: openai(OpenAI API), local(VM 모델), mock(개발용)
GenerationSource = Literal["local", "openai", "mock"]
# 서버가 고른 경로: primary(기본), fallback(대기·장애 우회), premium(유저 선택)
Route = Literal["primary", "fallback", "premium"]


class GenerateRequest(BaseModel):
    """POST /generate 요청 본문 (JSON 또는 multipart 폼 필드)."""

    purpose: Purpose
    product_name: str = Field(min_length=1)
    message: str = Field(min_length=1)
    style: str | None = None
    generation_mode: GenerationMode = "quick"
    # 결과 화면의 "조금 수정하기" 칩 (예: ["더 밝게", "텍스트 짧게"])
    adjustments: list[str] = Field(default_factory=list, max_length=10)
    # 유저가 "고품질로 만들기"를 고른 경우
    premium: bool = False

    @field_validator("product_name", "message", "style", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        # 검증 전에 공백을 지워서 "   " 같은 입력이 필수값 검사를 통과하지 못하게 한다
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("adjustments", mode="before")
    @classmethod
    def _clean_adjustments(cls, value: object) -> object:
        if isinstance(value, list):
            return [v.strip() for v in value if isinstance(v, str) and v.strip()]
        return value


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class GenerateSuccessResponse(BaseModel):
    status: Literal["success"] = "success"
    job_id: str
    image_url: str
    generation_source: GenerationSource
    route: Route
    # 이미지에 실제로 쓴 문구 ("텍스트 짧게"를 누르면 줄어든 문구)
    message: str
    model: str


class GenerateProcessingResponse(BaseModel):
    status: Literal["processing"] = "processing"
    job_id: str
    stage: Literal["queued", "running"]
    queue_position: int | None = None
    estimated_wait_seconds: float | None = None


class JobFailedResponse(BaseModel):
    status: Literal["failed"] = "failed"
    job_id: str
    error: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    image_backend: str
    primary_model: str
    primary_ready: bool
    fallback_model: str | None
    premium_model: str | None
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
    generation_mode: str = "quick"
    adjustments: list[str] = field(default_factory=list)
    reference_image: bytes | None = None


@dataclass
class GenerationOutput:
    """생성기 결과."""

    image_bytes: bytes  # PNG
    message: str
    model: str
