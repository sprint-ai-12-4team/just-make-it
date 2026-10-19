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
    # core: core.generate_ad_image 사용 (실제 생성, OPENAI_API_KEY 필요)
    # mock: API 키·GPU 없이 더미 이미지 반환 (프론트·서빙 개발용)
    image_backend: Literal["core", "mock"] = "core"
    # core registry에 등록된 모델 이름. 비우면 core의 DEFAULT_IMAGE_BACKEND
    primary_image_model: str | None = None
    # 대기·장애 시 우회할 모델. 비우면 Fallback 끔
    fallback_image_model: str | None = None
    # 유저가 고품질 모드를 고르면 쓸 모델. 비우면 premium 요청도 기본 모델로 처리
    premium_image_model: str | None = None
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

    # ----- 응답 -----
    # /generate가 결과를 기다려 주는 최대 시간(초). 넘으면 202 + job_id
    generate_wait_seconds: float = 60.0
    job_ttl_seconds: int = 60 * 60  # 완료된 작업 기록 보관 시간

    # ----- 입력 제한 -----
    max_upload_bytes: int = 10 * 1024 * 1024
    max_product_name_chars: int = 50
    max_message_chars: int = 200

    # ----- 결과 저장 -----
    # 서비스 파트의 GCS 업로더가 붙기 전까지 로컬 디스크에 저장하고 /results 로 서빙
    result_dir: Path = Path("outputs")
    public_base_url: str = "http://localhost:8000"

    # ----- CORS -----
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_serving_settings() -> ServingSettings:
    return ServingSettings()
