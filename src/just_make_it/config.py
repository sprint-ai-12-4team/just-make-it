"""프로젝트 전체 설정. 환경 변수는 프로젝트 루트의 .env에서 불러옵니다.

API 키 같은 비밀값은 코드에 직접 쓰지 않고 .env에만 둡니다!!
"""

import os

from dotenv import load_dotenv

load_dotenv()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_IMAGE_QUALITY = os.getenv("OPENAI_IMAGE_QUALITY", "medium")

DEFAULT_IMAGE_BACKEND = os.getenv("DEFAULT_IMAGE_BACKEND", "gpt-image-2.5-flare")

# 광고 문구 추천용 텍스트 모델
DEFAULT_TEXT_BACKEND = os.getenv("DEFAULT_TEXT_BACKEND", "gpt-5.4-mini")
