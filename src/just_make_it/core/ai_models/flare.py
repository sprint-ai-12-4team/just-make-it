"""API 이미지 모델: OpenAI gpt-image-2.5-flare.

그림 품질에서 더 정교하게를 골랐을 때 쓰고, klein이 실패하거나 klein이 모르는 품목일 때 폴백으로도 씁니다.
"""

import base64
import time

from openai import OpenAI

from just_make_it import config
from just_make_it.core.base import ImageGenerationError, ImageResult


class FlareImageModel:
    """OpenAI gpt-image-2.5-flare."""

    def __init__(self, model=config.FLARE_MODEL, quality=config.OPENAI_IMAGE_QUALITY):
        """
        Args:
            model: OpenAI 이미지 모델 이름
            quality: low, medium, high

        Raises:
            ImageGenerationError: OPENAI_API_KEY가 없을 때
        """
        if not config.OPENAI_API_KEY:
            raise ImageGenerationError(
                "OPENAI_API_KEY가 없습니다. .env 파일을 확인해주세요."
            )
        self.model = model
        self.quality = quality
        self.client = OpenAI(
            api_key=config.OPENAI_API_KEY,
            timeout=config.OPENAI_IMAGE_TIMEOUT,
            max_retries=config.OPENAI_MAX_RETRIES,
        )

    def generate(self, prompt, width, height, reference_image=None, seed=None):
        """프롬프트로 이미지를 만듭니다. 참고 사진이 있으면 편집 API를 씁니다.

        Args:
            prompt: 영어 이미지 프롬프트
            width: 가로 크기 (16의 배수로 맞춤)
            height: 세로 크기 (16의 배수로 맞춤)
            reference_image: 참고 사진 PNG 바이트. 없으면 None
            seed: OpenAI는 시드를 받지 않아서 쓰지 않음

        Returns:
            ImageResult: 생성 결과 (사용 토큰 포함)

        Raises:
            ImageGenerationError: API 호출 실패 또는 응답에 이미지가 없을 때
        """
        request = {
            "model": self.model,
            "prompt": prompt,
            "size": f"{width // 16 * 16}x{height // 16 * 16}",
            "quality": self.quality,
            "n": 1,
        }
        start = time.perf_counter()
        try:
            if reference_image is not None:
                request["image"] = ("reference.png", reference_image, "image/png")
                response = self.client.images.edit(**request)
            else:
                response = self.client.images.generate(**request)
        except Exception as e:
            raise ImageGenerationError(f"OpenAI 이미지 생성 실패: {e}") from e

        if not response.data or not response.data[0].b64_json:
            raise ImageGenerationError("OpenAI 응답에 이미지가 없습니다.")

        return ImageResult(
            image_bytes=base64.b64decode(response.data[0].b64_json),
            model=self.model,
            elapsed_sec=round(time.perf_counter() - start, 2),
            cost_usd=_cost_usd(getattr(response, "usage", None)),
        )


def _cost_usd(usage):
    """사용 토큰으로 예상 비용을 계산합니다. 텍스트 입력과 이미지 입력(참고 사진)은 가격이 달라서 나눠 계산합니다."""
    if usage is None:
        return 0.0
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    details = getattr(usage, "input_tokens_details", None)
    image_tokens = getattr(details, "image_tokens", 0) or 0
    text_tokens = getattr(details, "text_tokens", None)
    if text_tokens is None:
        text_tokens = input_tokens - image_tokens
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    cost = (
        text_tokens * config.FLARE_PRICE_TEXT_INPUT
        + image_tokens * config.FLARE_PRICE_IMAGE_INPUT
        + output_tokens * config.FLARE_PRICE_OUTPUT
    )
    return round(cost / 1_000_000, 6)
