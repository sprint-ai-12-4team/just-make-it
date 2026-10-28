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
# 글자 고치기 값 (api_spec 5장 text_layout). core text_overlay의 POSITIONS·FONTS와 같다
TextPosition = Literal["top", "middle", "bottom"]
FontId = Literal["jua", "yeonsung", "batang", "dodum", "blackhan"]
SIZE_SCALE_MIN, SIZE_SCALE_MAX = 0.6, 1.6
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


class TextLayout(BaseModel):
    """실제로 얹은 글자 위치·글꼴·크기. 결과 화면 "글자 고치기"의 처음 값."""

    position: TextPosition
    font: FontId
    size_scale: float


class GenerateSuccessResponse(BaseModel):
    """생성 완료 (POST /generate 200)."""

    id: str
    status: Literal["success"] = "success"
    # 글자를 얹은 최종 이미지 (화면 표시·다운로드·공유)
    image_url: str
    # 글자 없는 원본. 글자 고치기는 서버가 여기에 다시 얹는다
    background_url: str | None = None
    # 실제로 얹은 문구 ("텍스트 짧게"를 누르면 줄어든 문구)
    message: str
    text_layout: TextLayout | None = None
    source: Source
    width: int
    height: int


class GenerationInput(BaseModel):
    purpose: str
    product_name: str
    message: str
    style: str | None = None
    adjustments: list[str] = Field(default_factory=list)


class GenerationProgress(BaseModel):
    """만드는 중인 결과의 진행 상황 (V3). 서버가 메모리에 들고 있는 작업만 알 수 있다."""

    # queued: 차례를 기다리는 중, running: 만드는 중
    stage: Literal["queued", "running"]
    # 이 작업보다 먼저 처리될 작업 수 (대기 + 실행 중). 만드는 중이면 0
    jobs_ahead: int
    # 끝날 때까지 남은 예상 시간(초). 대략적인 값이라 화면에는 "약 N초"로
    estimated_seconds: float


class GenerationResponse(BaseModel):
    """결과 조회 (GET /generations/{id}). DB(service/db.py)가 돌려주는 모양 그대로."""

    id: str
    status: Literal["processing", "success", "error"]
    image_url: str | None = None
    background_url: str | None = None
    message: str | None = None
    # 글자 고치기 전 예전 결과·상세페이지 칸 이미지는 None
    text_layout: TextLayout | None = None
    source: Source | None = None
    width: int | None = None
    height: int | None = None
    parent_id: str | None = None
    created_at: str
    input: GenerationInput
    # 브라우저에서 고친 그림(배경 지우기·글자 직접 고치기)을 저장했으면 True
    edited: bool = False
    # processing일 때만. 서버를 다시 켜기 전 작업 등 알 수 없으면 None
    progress: GenerationProgress | None = None


class GenerationStarted(BaseModel):
    """비동기 생성 접수 (POST /generations 202). 결과는 GET /generations/{id}로 확인."""

    id: str
    status: Literal["processing"] = "processing"
    # 입력한 문구. 이미지보다 먼저 화면에 보여줄 수 있다 ("텍스트 짧게"면 완료 후 바뀔 수 있음)
    message: str
    width: int
    height: int
    estimated_seconds: float


class FamilyItem(BaseModel):
    id: str
    parent_id: str | None = None
    image_url: str
    created_at: str


class FamilyResponse(BaseModel):
    """같은 원본에서 만든 결과 (GET /generations/{id}/family). 성공한 결과만, 만든 순서."""

    items: list[FamilyItem]


# download 다운로드, copy_link 링크 복사, remake 다시 만들기, edit_text 글자 직접 고치기 시작,
# cutout 배경 지우고 색 채우기 완료, pick_copy 추천 문구 고름 (api_spec_next 1)
EventType = Literal[
    "download", "copy_link", "remake", "edit_text", "cutout", "pick_copy"
]
EVENT_DETAIL_MAX_BYTES = 4096


class EventRequest(BaseModel):
    """POST /events 요청."""

    generation_id: str = Field(max_length=64)
    type: EventType
    # 추가 정보 (자유 형식, JSON으로 4KB 이하). 예: {"edited": true}, {"index": 1, "copy": "…"}
    detail: dict | None = None


class DailyStats(BaseModel):
    date: str
    generated: int
    downloaded: int
    edited: int
    remade: int
    download_rate: float
    edit_rate: float
    remake_rate: float


class StatsResponse(BaseModel):
    """GET /stats. 단일 이미지 결과의 사용 지표 (상세페이지 칸 제외)."""

    days: list[DailyStats]
    total: DailyStats


class TextEditRequest(BaseModel):
    """POST /generations/{id}/text 요청. 보낸 필드만 바꾸고 나머지는 지금 값 유지."""

    message: str | None = None
    position: TextPosition | None = None
    font: FontId | None = None
    size_scale: float | None = Field(default=None, ge=SIZE_SCALE_MIN, le=SIZE_SCALE_MAX)


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
    # OpenAI 금액 회로차단기 (오늘 합계, 상한, 열림 = OpenAI 막힘)
    openai_cost_today_usd: float
    openai_daily_budget_usd: float
    openai_blocked: bool


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
    # core 받는 형태. combined = 서버가 글자를 얹음 (단일 이미지),
    # image = 글자 없는 이미지만 (상세페이지 칸. 아직 프론트가 얹음)
    output: Literal["combined", "image"] = "combined"


@dataclass
class GenerationOutput:
    """생성기 결과."""

    image_bytes: (
        bytes  # 최종 PNG. combined면 글자를 얹은 이미지, image면 글자 없는 이미지
    )
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
    # 그림 모델만 걸린 시간 (core image_sec). 문구·글자 얹기 제외
    image_ms: int | None = None
    # 글자 없는 원본 (combined일 때만. 글자 고치기용)
    background_bytes: bytes | None = None
    # 실제로 얹은 {position, font, size_scale} (combined일 때만)
    text_layout: dict | None = None
    # DB params_json에 남길 재현·분석용 값 (text_model, product_source 등)
    params: dict = field(default_factory=dict)
