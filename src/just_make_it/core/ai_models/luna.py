"""API 텍스트 모델: OpenAI gpt-5.6-luna.

문구 추천에서 더 자연스럽게를 골랐을 때 쓰고, Gemma가 실패했을 때 폴백으로도 씁니다.
"""

import time

from openai import OpenAI

from just_make_it import config
from just_make_it.core import deadline
from just_make_it.core.base import TextGenerationError, TextResult


class LunaTextModel:
    """OpenAI gpt-5.6-luna."""

    def __init__(self, model=config.LUNA_MODEL):
        """
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
        self.client = OpenAI(
            api_key=config.OPENAI_API_KEY,
            timeout=config.OPENAI_TEXT_TIMEOUT,
            max_retries=config.OPENAI_MAX_RETRIES,
        )

    def generate(self, instructions, user_input, max_tokens=300):
        """지시문과 입력으로 글을 생성합니다.

        Args:
            instructions: 모델이 지켜야 할 규칙
            user_input: 사용자 입력
            max_tokens: Gemma와 같은 모양으로 맞추려고 둔 인자. luna는 생각하는 데도 토큰을 써서
                길이를 제한하면 답이 잘릴 수 있어 쓰지 않음

        Returns:
            TextResult: 생성 결과

        Raises:
            TextGenerationError: API 호출 실패 또는 응답이 비어 있을 때
        """
        start = time.perf_counter()
        try:
            # 서빙이 제한 시간을 걸었으면 남은 시간만 기다리고 재시도하지 않음
            client = deadline.openai_client(self.client, "luna")
            response = client.responses.create(
                model=self.model,
                instructions=instructions,
                input=user_input,
            )
        except Exception as e:
            raise TextGenerationError(f"luna 문구 생성 실패: {e}") from e

        if not response.output_text:
            raise TextGenerationError("luna 응답에 글이 없습니다.")

        usage = getattr(response, "usage", None)
        cost = (getattr(usage, "input_tokens", 0) or 0) * config.LUNA_PRICE_INPUT + (
            getattr(usage, "output_tokens", 0) or 0
        ) * config.LUNA_PRICE_OUTPUT
        return TextResult(
            text=response.output_text.strip(),
            model=self.model,
            elapsed_sec=round(time.perf_counter() - start, 2),
            cost_usd=round(cost / 1_000_000, 6),
        )
