"""OpenAI 이미지 API 모델.

API 키와 모델 이름은 config.py에서 가져옵니다.
"""

import base64
import time

from openai import OpenAI

from just_make_it import config
from just_make_it.core.base import BaseImageModel, ImageGenerationError, ImageResult


class OpenAIImageModel(BaseImageModel):
    """OpenAI 이미지 생성 모델."""

    name = "openai"

    def __init__(self, model="gpt-image-2.5-flare", quality=None):
        """모델 이름과 품질을 정하고 클라이언트를 만듭니다.

        Args:
            model: OpenAI 이미지 모델 이름
            quality: low, medium, high. 비우면 config의 OPENAI_IMAGE_QUALITY

        Raises:
            ImageGenerationError: OPENAI_API_KEY가 없을 때
        """
        if not config.OPENAI_API_KEY:
            raise ImageGenerationError(
                "OPENAI_API_KEY가 없습니다. .env 파일을 확인해주세요."
            )
        self.model = model
        self.quality = quality or config.OPENAI_IMAGE_QUALITY
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)

    def generate(self, prompt, width, height, reference_image=None, **options):
        """OpenAI로 이미지를 생성합니다.

        참고 사진이 있으면 편집 API로 사진 속 상품을 살려서 만들고,
        없으면 생성 API로 처음부터 새로 그립니다.

        Args:
            prompt: 이미지 프롬프트
            width: 원하는 가로 크기 (모델이 받는 크기로 자동 변환)
            height: 원하는 세로 크기
            reference_image: 사용자가 올린 상품 사진 바이트 (PNG, JPG, WEBP)
            **options: quality를 넘기면 이번 호출에만 적용 (비어 있으면 기본값)

        Returns:
            ImageResult: 생성 결과

        Raises:
            ImageGenerationError: API 호출 실패 또는 응답에 이미지가 없을 때
        """
        request = {
            "model": self.model,
            "prompt": prompt,
            "size": self._size_for(width, height),
            "quality": options.get("quality") or self.quality,
            "n": 1,
        }
        if reference_image is not None:
            mime = _guess_mime(reference_image)
            extension = mime.split("/")[1]
            request["image"] = (f"reference.{extension}", reference_image, mime)

        start = time.perf_counter()
        try:
            if reference_image is not None:
                response = self.client.images.edit(**request)
            else:
                response = self.client.images.generate(**request)
        except Exception as e:
            raise ImageGenerationError(f"OpenAI 이미지 생성 실패: {e}") from e

        # gpt-image 계열은 URL이 아니라 base64 문자열로 이미지를 돌려줌
        if not response.data or not response.data[0].b64_json:
            raise ImageGenerationError("OpenAI 응답에 이미지가 없습니다.")

        return ImageResult(
            image_bytes=base64.b64decode(response.data[0].b64_json),
            model=self.model,
            elapsed_sec=round(time.perf_counter() - start, 2),
        )

    @staticmethod
    def _size_for(width, height):
        """gpt-image-2.5-flare가 받는 크기 문자열을 만듭니다.

        gpt-image-2.5-flare는 원하는 크기를 그대로 받지만, 가로와 세로가 16의 배수여야 합니다.

        Args:
            width: 원하는 가로 크기
            height: 원하는 세로 크기

        Returns:
            str: 가로x세로 형식의 크기
        """
        return f"{width // 16 * 16}x{height // 16 * 16}"


def _guess_mime(image_bytes):
    """사진 파일의 앞부분을 보고 형식을 알아냅니다.

    Args:
        image_bytes: 사진 바이트

    Returns:
        str: image/png, image/jpeg, image/webp 중 하나

    Raises:
        ImageGenerationError: 지원하지 않는 형식일 때
    """
    if image_bytes.startswith(b"\x89PNG"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    raise ImageGenerationError("참고 사진은 PNG, JPG, WEBP 파일만 사용할 수 있습니다.")
