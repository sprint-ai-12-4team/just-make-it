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
KLEIN_FP8_REPO = "black-forest-labs/FLUX.2-klein-4b-fp8"
KLEIN_FP8_FILE = "flux-2-klein-4b-fp8.safetensors"
FLARE_MODEL = "gpt-image-2.5-flare"

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_IMAGE_QUALITY = os.getenv("OPENAI_IMAGE_QUALITY", "medium")

# false면 로컬 모델이 실패했을 때 API 모델로 넘기지 않고 에러를 냄
USE_FALLBACK = os.getenv("USE_FALLBACK", "true").lower() == "true"

# "0"이면 문구 작업이 끝나자마자 Gemma를 GPU에서 내림. L4(24GB)에서는 Gemma와 klein이 같이 못 올라감
GEMMA_KEEP_ALIVE = os.getenv("GEMMA_KEEP_ALIVE", "0")

KLEIN_CPU_OFFLOAD = os.getenv("KLEIN_CPU_OFFLOAD", "false").lower() == "true"

# true면 이미지 한 장을 만들 때마다 klein을 메모리에서 내림 (메모리는 비지만 다음 생성 때 다시 불러와 느려짐)
KLEIN_UNLOAD_AFTER_USE = os.getenv("KLEIN_UNLOAD_AFTER_USE", "false").lower() == "true"

# 모델 호출 제한 시간(초). 서빙 제한(90초)보다 짧게 두어, 서빙이 포기한 뒤 호출이 뒤에서 계속 돌지 않게 함
OPENAI_IMAGE_TIMEOUT = float(os.getenv("OPENAI_IMAGE_TIMEOUT", "75"))
OPENAI_TEXT_TIMEOUT = float(os.getenv("OPENAI_TEXT_TIMEOUT", "30"))
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "1"))
GEMMA_TIMEOUT = float(os.getenv("GEMMA_TIMEOUT", "60"))

FLARE_PRICE_TEXT_INPUT = 5.0
FLARE_PRICE_IMAGE_INPUT = 8.0
FLARE_PRICE_OUTPUT = 30.0
LUNA_PRICE_INPUT = 0.20
LUNA_PRICE_OUTPUT = 1.20
