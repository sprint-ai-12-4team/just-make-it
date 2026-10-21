"""프로젝트 전체 설정. 환경 변수는 프로젝트 루트의 .env에서 불러옵니다.

API 키 같은 비밀값은 코드에 직접 쓰지 않고 .env에만 둡니다!!
"""

import os

from dotenv import load_dotenv

load_dotenv()

# 빠르게/기본은 VM의 로컬 모델, 더 정교하게/더 자연스럽게는 OpenAI API 모델
GEMMA_MODEL = "gemma4:12b-it-qat"
LUNA_MODEL = "gpt-5.6-luna"
KLEIN_MODEL = "black-forest-labs/FLUX.2-klein-4B"
FLARE_MODEL = "gpt-image-2.5-flare"

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_IMAGE_QUALITY = os.getenv("OPENAI_IMAGE_QUALITY", "medium")

# false면 로컬 모델이 실패했을 때 API 모델로 넘기지 않고 에러를 냄
USE_FALLBACK = os.getenv("USE_FALLBACK", "true").lower() == "true"

# "0"이면 문구 작업이 끝나자마자 Gemma를 GPU에서 내림. L4(24GB)에서는 Gemma와 klein이 같이 못 올라감
GEMMA_KEEP_ALIVE = os.getenv("GEMMA_KEEP_ALIVE", "0")

KLEIN_CPU_OFFLOAD = os.getenv("KLEIN_CPU_OFFLOAD", "false").lower() == "true"

# 100만 토큰당 달러. OpenAI 모델 페이지 가격표 기준 (2026-10 확인)
FLARE_PRICE_TEXT_INPUT = 5.0
FLARE_PRICE_IMAGE_INPUT = 8.0
FLARE_PRICE_OUTPUT = 30.0
LUNA_PRICE_INPUT = 0.20
LUNA_PRICE_OUTPUT = 1.20
