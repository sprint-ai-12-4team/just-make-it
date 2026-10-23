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
COPY pyproject.toml uv.lock README.md ./

# 가상환경 생성 + 의존성 설치 (프로덕션용, dev 의존성 제외)
# 기본으로 GPU 의존성(torch·diffusers 등, pyproject의 gpu extra)까지 설치한다.
# GPU 없이 OpenAI만 쓰는 가벼운 이미지가 필요하면: --build-arg UV_EXTRAS=
ARG UV_EXTRAS="--extra gpu"
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
RUN uv sync --frozen --no-dev ${UV_EXTRAS} --no-install-project

# 소스 코드 복사 후 프로젝트 설치
COPY src/ ./src/
RUN uv sync --frozen --no-dev ${UV_EXTRAS}


# ----- Stage 2: Runtime (실행 환경) -----
# CUDA 런타임은 torch 휠(PyPI, CUDA 13.0)에 들어 있어서 CUDA 베이스 이미지가 필요 없다.
# GPU 드라이버만 호스트에서 NVIDIA Container Toolkit으로 넘겨받는다 (드라이버 580 이상).
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
# 모델 캐시 경로 (compose의 model-cache 볼륨). klein 가중치를 처음 한 번만 받는다
ENV HF_HOME=/app/model-cache

# non-root 유저로 실행
# data: 서비스 DB·생성 이미지 (compose의 service-data 볼륨이 이 소유권을 이어받음)
RUN mkdir -p /app/model-cache /app/data && chown -R appuser:appuser /app
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
