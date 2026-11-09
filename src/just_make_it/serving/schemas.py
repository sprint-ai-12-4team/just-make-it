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
# 참고 사진 출처: upload 직접 올림 · stock 프론트가 보여 준 Pixabay 후보에서 고름 (정량평가용)
ReferenceSource = Literal["upload", "stock"]
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
    # AI 상담에서 넘어왔으면 그 상담 id (상담한 경우 vs 안 한 경우 비교용, 결과 input에 남음)
    consult_id: str | None = Field(default=None, max_length=64)
    # 상품 사진 그대로, 배경 장면만 AI (api_spec_next 4장). 배경을 지운 PNG·WEBP가 필요
    keep_product: bool = False
    # 참고 사진 출처 (정량평가용): upload 직접 올림 · stock Pixabay에서 고름. 사진이 없으면 저장하지 않음
    reference_source: ReferenceSource | None = None

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
    # keep_product일 때 배경이 투명한 상품 사진. 프론트가 장면(background_url) 위에 합침
    product_url: str | None = None
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
    consult_id: str | None = None
    keep_product: bool = False
    # 참고 사진 출처: upload · stock · None(사진 없음, 예전 결과)
    reference_source: ReferenceSource | None = None
    # 사용자가 고른 이미지 품질 (결과 화면 "다시 만들기"의 기본값). 예전 결과는 None.
    # 실제로 쓴 모델은 응답의 source (빠르게를 골라도 대기가 길면 OpenAI로 갈 수 있음)
    image_model: ImageModel | None = None


class GenerationProgress(BaseModel):
    """만드는 중인 결과의 진행 상황 (V3). 서버가 메모리에 들고 있는 작업만 알 수 있다."""

    # queued: 차례를 기다리는 중, running: 만드는 중
    stage: Literal["queued", "running"]
    # 이 작업보다 먼저 처리될 작업 수 (대기 + 실행 중). 만드는 중이면 0
    jobs_ahead: int
    # 끝날 때까지 남은 예상 시간(초). 대략적인 값이라 화면에는 "약 N초"로.
    # 예상보다 늦어지면 0 + overdue=True
    estimated_seconds: float
    # 접수 후 지난 시간(초). 프론트 막대는 이 값으로 그림 (새로고침·PC 시계 차이 무관)
    elapsed_seconds: float | None = None
    overdue: bool = False
    # 지금 하는 일 (core가 알려 줌): text 문구·영어 묘사 / image 그림 / saving 저장. 모르면 None
    phase: Literal["text", "image", "saving"] | None = None
    # 그림 모델 단계 (klein: steps=4). OpenAI는 None
    step: int | None = None
    steps: int | None = None


class GenerationResponse(BaseModel):
    """결과 조회 (GET /generations/{id}). DB(service/db.py)가 돌려주는 모양 그대로."""

    id: str
    status: Literal["processing", "success", "error"]
    image_url: str | None = None
    background_url: str | None = None
    # keep_product일 때 배경이 투명한 상품 사진 (아니면 None)
    product_url: str | None = None
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
# + add_qr 그림에 QR, tip_click 대기 카드, copy_kit 게시 문구 복사 (api_spec_consult 5장).
# flag(악용 감지)는 서버만 남기므로 여기 없음
EventType = Literal[
    "download",
    "copy_link",
    "remake",
    "edit_text",
    "cutout",
    "pick_copy",
    "add_qr",
    "tip_click",
    "copy_kit",
]


class EventRequest(BaseModel):
    """POST /events 요청."""

    generation_id: str = Field(max_length=64)
    type: EventType
    # 추가 정보 (자유 형식, JSON으로 4KB 이하). 예: {"edited": true}, {"index": 1, "copy": "…"}
    detail: dict | None = None


class ReferenceStats(BaseModel):
    """참고 사진 출처별 (upload · stock · none). generated가 0이면 비율은 None."""

    generated: int
    download_rate: float | None
    remake_rate: float | None


class DailyStats(BaseModel):
    date: str
    generated: int
    downloaded: int
    edited: int
    remade: int
    download_rate: float
    edit_rate: float
    remake_rate: float
    # 정량평가 칸 (11-04 요청). mock 결과 제외, 계산할 결과가 없으면 None
    seconds_p50: float | None = None  # 생성 시간(대기 포함) 중앙값
    seconds_p95: float | None = None
    local_rate: float | None = None  # 로컬 GPU로 만든 비율 (성공 중)
    cost_usd: float | None = None  # OpenAI 비용 합 (성공·실패 모두)
    cost_per_image_usd: float | None = None  # cost_usd / 성공 수
    error_rate: float | None = None  # 실패 / (성공 + 실패)
    by_reference: dict[str, ReferenceStats] | None = None


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
    # processing인 칸만 (단일 이미지 progress와 같은 모양)
    progress: GenerationProgress | None = None


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
    # 시작 웜업: off(설정으로 끔) · pending · running · done · skipped(mock, core 함수 없음) · failed
    warmup: Literal["off", "pending", "running", "done", "skipped", "failed"] = "off"
    warmup_seconds: float | None = None
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
    # AI 상담에서 넘어왔으면 그 상담 id (기록용)
    consult_id: str | None = None
    # 상품 없는 장면만 그림. reference_image는 상품(투명 PNG)으로 저장만 하고 모델에는 넣지 않음
    keep_product: bool = False
    # 참고 사진 출처 (기록용, upload · stock). 사진이 없으면 None
    reference_source: str | None = None
    # 사용자가 고른 이미지 품질 (기록용, input.image_model). 실제 경로는 submit의 premium이 정함
    image_model: str | None = None
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


# ---------------------------------------------------------------------- 대기 카드 (api_spec_consult 2장)
class TipAction(BaseModel):
    label: str
    href: str


class TipSource(BaseModel):
    name: str
    url: str


class Tip(BaseModel):
    id: str
    kind: Literal["season", "howto", "platform", "law", "support", "news"]
    title: str
    body: str | None = None
    action: TipAction | None = None
    source: TipSource | None = None
    checked_at: str | None = None


class TipsResponse(BaseModel):
    tips: list[Tip]


# ---------------------------------------------------------------------- AI 상담 (api_spec_consult 3장)
class ConsultStartRequest(BaseModel):
    """POST /consults. 만들기 화면에서 넘어오면 채워서 보냄 (모두 선택)."""

    purpose: Purpose | None = None
    product_name: str | None = Field(default=None, max_length=50)

    _strip = field_validator("product_name", mode="before")(_strip_text)


CONSULT_TEXT_MAX = 500


class AdviceRequest(BaseModel):
    """POST /advice. advice_id가 없으면 새 대화. consult_id가 있으면 그 상담 기획서를 참고."""

    advice_id: str | None = Field(default=None, max_length=64)
    text: str
    consult_id: str | None = Field(default=None, max_length=64)


class AdviceResponse(BaseModel):
    advice_id: str
    reply: str
    chips: list[str] = Field(default_factory=list)
    # true면 프론트가 "이미지 만들러 가기" 버튼을 보여 줌
    go_create: bool = False
    ended: bool = False
    turn: int
    max_turns: int
    # 이번 턴에 부른 모델: openai / local
    source: Literal["openai", "local"] | None = None


class ConsultMessageRequest(BaseModel):
    """POST /consults/{id}/messages. 칩을 눌렀으면 칩 글자 그대로 + chip=true."""

    text: str
    chip: bool = False


class Brief(BaseModel):
    """광고 기획서 (프론트 lib/types.ts Brief와 같은 모양)."""

    category: str
    goal: str
    product_name: str
    period: str | None = None
    strengths: list[str] = Field(default_factory=list)
    audience: str
    purpose: Purpose
    channel: str
    message: str
    copies: list[str]
    style: str | None = None
    reason: str
    next_tips: list[str] = Field(default_factory=list)


class ConsultTurnResponse(BaseModel):
    id: str
    reply: str
    chips: list[str]
    allow_free_text: bool
    turn: int
    max_turns: int
    brief: Brief | None = None
    ended: bool = False
    # 기획서를 더 고칠 수 있는 횟수 (기획서가 나오기 전에는 None)
    edits_left: int | None = None
    # 이번 턴에 부른 모델: openai / local. 모델을 안 불렀으면(칩·고정 질문) None
    source: Literal["openai", "local"] | None = None


class ConsultMessage(BaseModel):
    role: Literal["assistant", "user"]
    text: str
    chips: list[str] | None = None


class ConsultResponse(BaseModel):
    """GET /consults/{id}. 새로고침했을 때 대화를 다시 보여 줌."""

    id: str
    messages: list[ConsultMessage]
    brief: Brief | None = None
    ended: bool = False
    edits_left: int | None = None


# ---------------------------------------------------------------------- 문구 변환 (api_spec_consult 4장)
ConvertFormat = Literal[
    "instagram_post",
    "instagram_hashtags",
    "instagram_location",
    "instagram_story",
    "naver_coupon",
    "naver_blog_title",
    "store_description",
]
CONVERT_TEXT_MAX = 300


class ConvertRequest(BaseModel):
    text: str
    format: ConvertFormat
    product_name: str | None = Field(default=None, max_length=50)
    area: str | None = Field(default=None, max_length=30)
    # 쿠폰 조건 등 사장님이 입력한 값. 모델은 여기 없는 숫자를 쓰지 않음
    facts: dict[str, str] | None = None

    _strip = field_validator("product_name", "area", mode="before")(_strip_text)


class Coupon(BaseModel):
    title: str
    condition: str
    period: str


class ConvertResponse(BaseModel):
    format: ConvertFormat
    result: str | list[str] | Coupon
    fixed_typos: bool
    source: Literal["openai", "local"]
