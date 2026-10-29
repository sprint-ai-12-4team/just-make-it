# syntax=docker/dockerfile:1
# ============================================================
# just-make-it — Multi-stage Dockerfile
# Target: GCP g2-standard-4 (L4 GPU, 16GB system RAM)
#
# 이미지 크기·빌드 시간 (docs/serving/docker_build.md)
# - GPU 의존성(.venv)은 압축 풀면 수 GB라 레이어를 어떻게 나누는지가 배포 시간을 좌우한다
# - .venv 레이어는 pyproject·uv.lock이 바뀔 때만 새로 만든다. 코드(src)만 바뀐 배포는
#   src 레이어만 새로 만들어 몇 분 안에 끝난다
# ============================================================

# ----- Stage 1: deps (의존성만 설치) -----
FROM astral/uv:python3.11-bookworm-slim AS deps

WORKDIR /app

# 시스템 의존성 (빌드용)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 의존성 파일만 먼저 복사 (레이어 캐시 활용)
COPY pyproject.toml uv.lock README.md ./

# 가상환경 생성 + 의존성 설치 (프로덕션용, dev 의존성 제외, 프로젝트 코드는 넣지 않음)
# 기본으로 GPU 의존성(torch·diffusers 등, pyproject의 gpu extra)까지 설치한다.
# GPU 없이 OpenAI만 쓰는 가벼운 이미지가 필요하면: --build-arg UV_EXTRAS=
# uv 캐시를 빌드 캐시로 남겨, uv.lock이 바뀌어도 받아 둔 휠(torch 등 약 3GB)은 다시 받지 않는다
ARG UV_EXTRAS="--extra gpu"
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev ${UV_EXTRAS} --no-install-project


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
    && useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/model-cache /app/data \
    && chown appuser:appuser /app /app/model-cache /app/data

# 의존성(.venv)과 코드(src)를 다른 레이어로 복사한다. 소유자는 복사하면서 바꾼다
# (예전처럼 마지막에 chown -R /app을 하면 수 GB짜리 .venv가 레이어에 한 벌 더 생기고,
#  코드만 바뀌어도 그 레이어를 매번 다시 써서 이미지가 약 2배, 배포가 수 분 더 걸렸다)
COPY --from=deps --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser src/ /app/src/

# 환경 변수
# 프로젝트는 설치하지 않고 PYTHONPATH로 불러온다 (코드가 바뀌어도 .venv 레이어가 그대로)
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# 모델 캐시 경로 (compose의 model-cache 볼륨). klein 가중치를 처음 한 번만 받는다
ENV HF_HOME=/app/model-cache

# non-root 유저로 실행
# data: 서비스 DB·생성 이미지 (compose의 service-data 볼륨이 이 소유권을 이어받음)
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
