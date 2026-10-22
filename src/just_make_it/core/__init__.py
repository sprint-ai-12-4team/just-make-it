"""모델 개발 파트: 광고 이미지 생성 파이프라인 V1.

서빙에서는 이 세 함수만 쓰면 됩니다.
- generate_ad_image: 광고 이미지 생성 (참고 사진 선택)
- suggest_ad_copies: 광고 문구 3개 추천
- render_text: 글자 고치기. 글자 없는 원본에 문구, 위치, 글꼴, 크기만 바꿔 다시 얹음 (이미지 재생성 없음)

받는 형태 output
- combined (기본값): 문구를 얹은 이미지 + 글자 없는 이미지 + 문구 레이어
- image: 글자 없는 이미지만 (추천 text_layout 포함)
- text: 디자인된 문구 레이어(투명 PNG)만 (추천 text_layout 포함)

text_layout 값
- position: top / middle / bottom
- font: jua / yeonsung / batang / dodum / blackhan
- size_scale: 0.6 ~ 1.6 (글자 더 크게 칩은 1.25)

품질 고르기 값
- 그림 image_quality: fast (빠르게, 기본값) / detailed (더 정교하게)
- 문구 text_quality: basic (기본, 기본값) / natural (더 자연스럽게)
"""

from just_make_it.core.base import ImageGenerationError, TextGenerationError
from just_make_it.core.copywriter import suggest_ad_copies
from just_make_it.core.pipeline import AdImageResult, generate_ad_image
from just_make_it.core.text_overlay import render_text

__all__ = [
    "AdImageResult",
    "ImageGenerationError",
    "TextGenerationError",
    "generate_ad_image",
    "render_text",
    "suggest_ad_copies",
]
