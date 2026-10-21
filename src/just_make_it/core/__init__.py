"""모델 개발 파트: 광고 이미지 생성 파이프라인 V1.

서빙에서는 이 두 함수만 쓰면 됩니다.
- generate_ad_image: 광고 이미지 생성 (참고 사진 선택)
- suggest_ad_copies: 광고 문구 3개 추천

품질 고르기 값
- 그림 image_quality: fast (빠르게, 기본값) / detailed (더 정교하게)
- 문구 text_quality: basic (기본, 기본값) / natural (더 자연스럽게)
"""

from just_make_it.core.base import ImageGenerationError, TextGenerationError
from just_make_it.core.copywriter import suggest_ad_copies
from just_make_it.core.pipeline import AdImageResult, generate_ad_image

__all__ = [
    "AdImageResult",
    "ImageGenerationError",
    "TextGenerationError",
    "generate_ad_image",
    "suggest_ad_copies",
]
