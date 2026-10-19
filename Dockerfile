# ============================================================
# just-make-it — Multi-stage Dockerfile
# Target: GCP g2-standard-4 (L4 GPU, 16GB system RAM)
# ============================================================

# ----- Stage 1: Builder (의존성 설치) -----
FROM astral/uv:python3.11-bookworm-slim AS builder

WORKDIR /app

# 시스템 의존성 (빌드용)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 의존성 파일만 먼저 복사 (레이어 캐시 활용)
COPY pyproject.toml uv.lock ./

# 가상환경 생성 + 의존성 설치 (프로덕션용, dev 의존성 제외)
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
RUN uv sync --frozen --no-dev --no-install-project

# 소스 코드 복사 후 프로젝트 설치
COPY src/ ./src/
RUN uv sync --frozen --no-dev


# ----- Stage 2: Runtime (실행 환경) -----
# CUDA runtime 베이스를 쓰면 이미지가 커지므로,
# 호스트에 NVIDIA Container Toolkit이 있을 때 동작하는 방식을 기본으로 함.
# (GCP L4 인스턴스 + nvidia-docker 환경 가정)
FROM python:3.11-slim AS runtime

WORKDIR /app

# 런타임에 필요한 최소 시스템 패키지
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

# builder에서 만든 가상환경 복사
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# 환경 변수
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# 모델 캐시 경로 (볼륨 마운트 권장)
ENV HF_HOME=/app/model-cache
ENV TRANSFORMERS_CACHE=/app/model-cache

# non-root 유저로 실행
RUN mkdir -p /app/model-cache && chown -R appuser:appuser /app
USER appuser

# 포트
EXPOSE 8000

# 헬스체크 (모델 로딩이 길 수 있으므로 start-period를 넉넉히)
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 반드시 --workers 1 (RAM 16GB 보호)
CMD ["uvicorn", "just_make_it.serving.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1"]
