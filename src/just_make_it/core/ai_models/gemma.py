"""텍스트 모델: Gemma 4 12B. VM의 Ollama 서버로 호출합니다."""

import time

import requests

from just_make_it import config
from just_make_it.core.base import TextGenerationError, TextResult


class GemmaTextModel:
    """Ollama로 띄운 Gemma 4 12B."""

    def __init__(
        self,
        model=config.GEMMA_MODEL,
        host=config.OLLAMA_HOST,
        timeout=config.GEMMA_TIMEOUT,
    ):
        """
        Args:
            model: Ollama 모델 태그
            host: Ollama 서버 주소
            timeout: 한 번 호출을 기다리는 최대 시간(초)
        """
        self.model = model
        self.host = host
        self.timeout = timeout
        self.no_think = True

    def generate(self, instructions, user_input, max_tokens=300):
        """지시문과 입력으로 글을 생성합니다.

        Args:
            instructions: 모델이 지켜야 할 규칙
            user_input: 사용자 입력
            max_tokens: 최대로 쓸 토큰 수

        Returns:
            TextResult: 생성 결과

        Raises:
            TextGenerationError: Ollama 호출 실패 또는 응답이 비어 있을 때
        """
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_input},
            ],
            "stream": False,
            "keep_alive": _keep_alive(config.GEMMA_KEEP_ALIVE),
            "options": {"num_predict": max_tokens, "temperature": 0.7},
        }
        if self.no_think:
            body["think"] = False

        start = time.perf_counter()
        try:
            response = requests.post(
                f"{self.host}/api/chat", json=body, timeout=self.timeout
            )
        except requests.RequestException as e:
            raise TextGenerationError(f"Gemma 서버에 연결하지 못했습니다: {e}") from e

        if response.status_code == 400 and "think" in response.text and self.no_think:
            self.no_think = False
            return self.generate(instructions, user_input, max_tokens)
        try:
            response.raise_for_status()
            text = response.json()["message"]["content"] or ""
        except (requests.HTTPError, ValueError, KeyError, TypeError) as e:
            raise TextGenerationError(f"Gemma 문구 생성 실패: {e}") from e

        if "</think>" in text:
            text = text.split("</think>")[-1]
        if not text.strip():
            raise TextGenerationError("Gemma 응답에 글이 없습니다.")

        return TextResult(
            text=text.strip(),
            model=self.model,
            elapsed_sec=round(time.perf_counter() - start, 2),
        )


def _keep_alive(value):
    """Ollama keep_alive 값으로 바꿉니다. "0"처럼 숫자만 있으면 초 단위 숫자로 넘깁니다."""
    return int(value) if value.lstrip("-").isdigit() else value
