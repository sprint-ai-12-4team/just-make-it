"""프로젝트 전체 설정. 환경 변수는 프로젝트 루트의 .env에서 불러옵니다.

API 키 같은 비밀값은 코드에 직접 쓰지 않고 .env에만 둡니다!!
"""

import os

from dotenv import load_dotenv

load_dotenv()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1-mini")
OPENAI_IMAGE_QUALITY = os.getenv("OPENAI_IMAGE_QUALITY", "low")

DEFAULT_IMAGE_BACKEND = os.getenv("DEFAULT_IMAGE_BACKEND", "openai")
