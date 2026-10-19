"""OpenAI 텍스트 모델. 광고 문구 추천에 사용합니다.

API 키와 모델 이름은 config.py에서 가져옵니다.
"""

import time

from openai import OpenAI

from just_make_it import config
from just_make_it.core.base import BaseTextModel, TextGenerationError, TextResult


class OpenAITextModel(BaseTextModel):
    """OpenAI 텍스트 생성 모델."""

    name = "openai-text"

    def __init__(self, model="gpt-5.6-luna"):
        """모델 이름을 정하고 클라이언트를 만듭니다.

        Args:
            model: OpenAI 텍스트 모델 이름

        Raises:
            TextGenerationError: OPENAI_API_KEY가 없을 때
        """
        if not config.OPENAI_API_KEY:
            raise TextGenerationError(
                "OPENAI_API_KEY가 없습니다. .env 파일을 확인해주세요."
            )
        self.model = model
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)

    def generate(self, instructions, user_input, **options):
        """지시문과 입력으로 글을 생성합니다.

        Args:
            instructions: 모델이 지켜야 할 규칙
            user_input: 사용자 입력
            **options: 지금은 사용하지 않음 (나중에 모델별 옵션용)

        Returns:
            TextResult: 생성 결과

        Raises:
            TextGenerationError: API 호출 실패 또는 응답이 비어 있을 때
        """
        start = time.perf_counter()
        try:
            response = self.client.responses.create(
                model=self.model,
                instructions=instructions,
                input=user_input,
            )
        except Exception as e:
            raise TextGenerationError(f"OpenAI 문구 생성 실패: {e}") from e

        if not response.output_text:
            raise TextGenerationError("OpenAI 응답에 글이 없습니다.")

        return TextResult(
            text=response.output_text.strip(),
            model=self.model,
            elapsed_sec=round(time.perf_counter() - start, 2),
        )
