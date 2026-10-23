"""서빙 전용 설정.

모델·API 키 설정은 core가 쓰는 `just_make_it/config.py`를 그대로 따르고,
여기에는 큐·Fallback·저장처럼 서빙에만 필요한 값만 둔다.
모든 값은 `.env` 또는 환경 변수로 덮어쓸 수 있다. 예: ``IMAGE_BACKEND=mock``.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServingSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ----- 생성기 선택 -----
    # core: core 파이프라인 V1 사용 (실제 생성)
    # mock: API 키·GPU 없이 더미 이미지 반환 (프론트·서빙 개발용)
    image_backend: Literal["core", "mock"] = "core"
    # 기본 경로("빠르게" = 로컬 klein) 대기가 길거나 준비 안 됐을 때
    # "더 정교하게"(OpenAI flare)로 넘길지. false면 기다리거나 503
    queue_fallback: bool = True
    # /generate 안에서 이미지 프롬프트용 영어 묘사를 만들 텍스트 품질
    # basic = 로컬 Gemma(실패하면 core가 luna로 폴백), natural = OpenAI luna
    generate_text_quality: Literal["basic", "natural"] = "basic"
    # 서버 시작 시 모델(klein)을 뒤에서 불러온다. 다 불러오기 전 요청은 Fallback으로 처리
    load_models_in_background: bool = True
    mock_delay_seconds: float = 2.0

    # ----- 기본 생성기 대기열 -----
    # 동시에 처리할 작업 수. 로컬 GPU 모델이면 1, API 모델이면 2~3
    primary_concurrency: int = 1
    # 1건 생성 시간 초기 추정값(초). 실제 생성 시간으로 계속 보정됨
    seconds_per_job_init: float = 20.0
    # 생성 실패 시 같은 모델로 재시도할 횟수
    retry_count: int = 1
    # 대기열이 이 이상이면 새 요청을 거절 (Fallback이 불가능할 때)
    queue_max_size: int = 50

    # ----- Fallback -----
    # 새 작업의 예상 완료 시간이 이 값(초)을 넘으면 Fallback 모델로 우회
    max_wait_seconds: float = 30.0

    # ----- 비용 보호 (Asia/Seoul 자정 기준 초기화, 0이면 무제한) -----
    daily_job_limit: int = 300  # 하루 전체 생성 요청 수
    extra_daily_limit: int = 100  # 그중 Fallback·프리미엄 호출 수
    client_daily_limit: int = 0  # 사용자(X-Client-Id) 1명당 하루 생성 수 (DB 기준)

    # ----- 타임아웃 -----
    # 생성 1건의 제한 시간(초). 넘으면 재시도 없이 Fallback 또는 실패 처리
    # (Flare 평균 17~20초, "텍스트 짧게"는 문구 모델 호출까지 포함)
    generation_timeout_seconds: float = 90.0
    # 문구 추천(/copies) 제한 시간(초). Gemma는 호출 때마다 GPU에 올렸다 내려서 여유 있게
    copy_timeout_seconds: float = 60.0
    # 상세페이지 문구 5칸 제한 시간(초). 문구가 길어 /copies보다 여유 있게
    detail_text_timeout_seconds: float = 90.0

    # ----- 응답 -----
    # /generate는 동기 응답. 대기 + 생성 + Fallback까지 이 시간(초) 안에 안 끝나면 503
    # (작업 자체는 계속 돌고 결과는 DB에 남아 GET /generations/{id}로 볼 수 있음)
    # Vercel 프록시가 120초에서 끊으므로 그보다 짧게
    generate_wait_seconds: float = 110.0

    # ----- 입력 제한 -----
    max_upload_bytes: int = 10 * 1024 * 1024
    max_product_name_chars: int = 50
    max_message_chars: int = 200
    max_feature_chars: int = 50  # 상세페이지 특징 1개

    # ----- 저장 (service/db.py, service/storage.py) -----
    # DB(just_make_it.db)·생성 이미지(images/)·참고 사진(references/)을 두는 폴더.
    # 이미지 URL 앞부분은 서비스 저장소가 PUBLIC_BASE_URL 환경 변수로 정한다
    data_dir: Path = Path("data")

    # ----- CORS -----
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_serving_settings() -> ServingSettings:
    return ServingSettings()
