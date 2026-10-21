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


def _strip_text(value: object) -> object:
    # 검증 전에 공백을 지워서 "   " 같은 입력이 필수값 검사를 통과하지 못하게 한다
    if isinstance(value, str):
        return value.strip() or None
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
    # 고품질 모드 (스펙 미결 사항. 서버에 프리미엄 모델이 설정됐을 때만 적용)
    premium: bool = False

    _strip = field_validator("product_name", "message", "style", mode="before")(
        _strip_text
    )

    @field_validator("adjustments", mode="before")
    @classmethod
    def _clean_adjustments(cls, value: object) -> object:
        if isinstance(value, list):
            return [v.strip() for v in value if isinstance(v, str) and v.strip()]
        return value


class CopiesRequest(BaseModel):
    """POST /copies 요청 본문."""

    product_name: str
    message: str
    style: str | None = None

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
    adjustments: list[str] = field(default_factory=list)
    reference_image: bytes | None = None


@dataclass
class GenerationOutput:
    """생성기 결과."""

    image_bytes: bytes  # PNG
    message: str
    model: str
    width: int
    height: int
    prompt: str | None = None
