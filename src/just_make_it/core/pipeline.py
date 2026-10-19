"""
어떤 모델을 쓸지는 backend 값으로 고르고, 모델이 바뀌어도 이 파일은 고치지 않습니다.
"""

from dataclasses import dataclass

from just_make_it.core.copywriter import shorten_message
from just_make_it.core.prompt_builder import build_image_prompt, get_image_size
from just_make_it.core.registry import DEFAULT_IMAGE_BACKEND, get_image_model

TEXT_IN_IMAGE_MODES = {"quick"}

# 이 칩을 누르면 텍스트 모델로 문구를 먼저 줄임
# 빠른 생성은 줄인 문구로 이미지를 다시 만들고, 나머지 모드는 줄인 문구를 웹에서 얹음
SHORTEN_ADJUSTMENT = "텍스트 짧게"


@dataclass
class AdImageResult:
    """광고 이미지 생성 결과 (서빙에 전달하는 형태).

    Args:
        image_bytes: PNG 이미지 바이트
        message: 이미지에 실제로 쓴 문구 (텍스트 짧게를 누르면 줄어든 문구)
        prompt: 실제로 사용한 프롬프트 (실험 기록용)
        backend: 사용한 모델 이름 (gpt-image-2.5-flare 등)
        model: 실제 모델 이름
        width: 요청한 가로 크기
        height: 요청한 세로 크기
        elapsed_sec: 생성에 걸린 시간(초)
    """

    image_bytes: bytes
    message: str
    prompt: str
    backend: str
    model: str
    width: int
    height: int
    elapsed_sec: float


def generate_ad_image(
    product_name,
    message,
    purpose="free",
    style=None,
    generation_mode="quick",
    backend=DEFAULT_IMAGE_BACKEND,
    reference_image=None,
    adjustments=None,
    **options,
):
    """프론트 입력값으로 광고 이미지를 생성합니다.

    Args:
        product_name: 가게 또는 상품 이름
        message: 핵심 메시지
        purpose: 광고 목적 (instagram, commerce, youtube, kakao, free)
        style: 분위기 칩 값
        generation_mode: quick, template, canvas
        backend: 사용할 모델 이름 (registry.py에 등록된 이름)
        reference_image: 사용자가 올린 상품 사진 바이트. 없으면 None
        adjustments: 조금 수정하기 칩 목록 (예: ["더 밝게", "배경 단순하게"])
        **options: 모델별 추가 옵션 (예: quality)

    Returns:
        AdImageResult: 이미지와 실험 기록용 정보

    Raises:
        ValueError: 필수 입력이 비었거나 등록되지 않은 backend일 때
        ImageGenerationError: 모델이 생성에 실패했을 때
        TextGenerationError: 텍스트 짧게 처리 중 문구 생성에 실패했을 때
    """
    # 비용이 드는 문구 줄이기보다 입력 검사를 먼저 해서 헛된 API 호출을 막음
    if not product_name.strip() or not message.strip():
        raise ValueError("상품 이름과 핵심 메시지는 꼭 입력해야 합니다.")

    adjustments = adjustments or []
    include_text = generation_mode in TEXT_IN_IMAGE_MODES

    if SHORTEN_ADJUSTMENT in adjustments:
        message = shorten_message(message)

    prompt = build_image_prompt(
        product_name=product_name,
        message=message,
        purpose=purpose,
        style=style,
        include_text=include_text,
        has_reference=reference_image is not None,
        adjustments=adjustments,
    )
    width, height = get_image_size(purpose)

    result = get_image_model(backend).generate(
        prompt, width, height, reference_image=reference_image, **options
    )

    return AdImageResult(
        image_bytes=result.image_bytes,
        message=message,
        prompt=prompt,
        backend=backend,
        model=result.model,
        width=width,
        height=height,
        elapsed_sec=result.elapsed_sec,
    )
