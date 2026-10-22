"""광고 이미지 생성 파이프라인 V1.

사용자가 고르는 품질에 따라 모델이 정해집니다.
- 그림 fast (빠르게): FLUX.2 [klein] 4B / detailed (더 정교하게): gpt-image-2.5-flare
- 문구 basic (기본): Gemma 4 12B / natural (더 자연스럽게): gpt-5.6-luna
VM의 로컬 모델(klein, Gemma)이 실패하면 API 모델(flare, luna)로 폴백합니다.

흐름
1. 입력 검사
2. 텍스트 짧게 칩이 있으면 문구 줄이기
3. 텍스트 모델이 상품과 메시지를 영어 묘사로 바꾸기 (품목 사전에 있으면 사전 묘사 사용)
4. 글자 없는 영어 이미지 프롬프트 만들기
5. 고른 품질의 이미지 모델로 생성
6. 분위기에 맞는 디자인으로 문구 레이어를 만들어 이미지에 얹기

받는 형태 (output)
- combined: 문구를 얹은 이미지. 글자 없는 이미지와 문구 레이어도 같이 줘서 웹에서 문구를 옮길 수 있음
- image: 글자 없는 이미지만. 문구는 얹지 않고 추천 글꼴과 위치만 줌
- text: 디자인된 문구 레이어(투명 PNG)만. 이미지 모델을 부르지 않아 GPU와 비용이 들지 않음
세 형태 모두 문구 위치, 글꼴, 크기(text_layout)와 문구 레이어 위치(text_box)를 같이 줌.
글자만 고칠 때는 이미지를 다시 만들지 않고 text_overlay.render_text로 background_bytes에 다시 얹음
"""

import io
import time
from dataclasses import dataclass

from PIL import Image

from just_make_it import config
from just_make_it.core import ai_models
from just_make_it.core.base import ImageGenerationError
from just_make_it.core.copywriter import (
    check_text_quality,
    describe_for_image,
    shorten_message,
)
from just_make_it.core.product_dictionary import lookup
from just_make_it.core.prompt_builder import build_image_prompt, get_image_size
from just_make_it.core.text_overlay import (
    overlay_text,
    place_text,
    render_text_layer,
)

OUTPUTS = ("combined", "image", "text")
SHORTEN_ADJUSTMENT = "텍스트 짧게"
BIGGER_TEXT_ADJUSTMENT = "글자 더 크게"
IMAGE_QUALITIES = ("fast", "detailed")


@dataclass
class AdImageResult:
    """광고 이미지 생성 결과 (서빙에 전달하는 형태).

    Args:
        output: 받은 형태 (combined, image, text)
        image_bytes: 최종 PNG. combined면 문구를 얹은 이미지, image면 글자 없는 이미지, text면 None
        background_bytes: 글자 없는 원본 PNG. text면 None
        text_layer_bytes: 디자인된 문구만 그린 투명 PNG. image면 None
        text_layout: 문구 위치, 글꼴, 크기 {"position", "font", "size_scale"}.
            combined면 실제로 얹은 값, 나머지는 추천 값. 글자 고치기의 처음 값으로 씀
        text_box: 문구 레이어 위치와 크기 (x, y, 가로, 세로). 테두리, 그림자, 장식 포함
        message: 이미지에 쓴 문구 (텍스트 짧게를 누르면 줄어든 문구)
        prompt: 실제로 사용한 영어 이미지 프롬프트. text면 빈 문자열
        image_model: 실제로 이미지를 만든 모델. text면 빈 문자열
        image_fallback_reason: klein 대신 flare를 쓴 이유. 폴백하지 않았으면 빈 문자열
        text_model: 실제로 쓴 텍스트 모델. 텍스트 모델을 안 불렀으면 빈 문자열
        text_fallback_reason: Gemma 대신 luna를 쓴 이유. 폴백하지 않았으면 빈 문자열
        product_source: 상품 묘사 출처 (품목 사전 또는 텍스트 모델). text면 빈 문자열
        used_reference: 참고 사진을 썼는지
        width: 이미지 가로 크기 (text면 문구 크기를 맞춘 기준 크기)
        height: 이미지 세로 크기 (text면 문구 크기를 맞춘 기준 크기)
        text_sec: 텍스트 모델 단계에 걸린 시간(초)
        image_sec: 이미지 생성에 걸린 시간(초). 폴백했으면 klein을 시도한 시간까지 포함
        overlay_sec: 문구 레이어를 만들고 얹는 데 걸린 시간(초)
        elapsed_sec: 전체 걸린 시간(초)
        cost_usd: 예상 비용(달러). flare와 luna 비용 합계, 로컬 모델만 썼으면 0
        seed: 실제로 쓴 시드. 조금 수정하기 때 다시 넘김 (flare나 text면 None)
    """

    output: str
    image_bytes: bytes | None
    background_bytes: bytes | None
    text_layer_bytes: bytes | None
    text_layout: dict
    text_box: tuple[int, int, int, int]
    message: str
    prompt: str
    image_model: str
    image_fallback_reason: str
    text_model: str
    text_fallback_reason: str
    product_source: str
    used_reference: bool
    width: int
    height: int
    text_sec: float
    image_sec: float
    overlay_sec: float
    elapsed_sec: float
    cost_usd: float
    seed: int | None


def generate_ad_image(
    product_name,
    message,
    purpose="free",
    style=None,
    output="combined",
    reference_image=None,
    adjustments=None,
    seed=None,
    image_quality="fast",
    text_quality="basic",
):
    """프론트 입력값으로 광고 이미지를 생성합니다.

    Args:
        product_name: 가게 또는 상품 이름
        message: 이미지에 넣을 문구 (핵심 메시지 또는 추천받은 문구)
        purpose: 광고 목적 (instagram, commerce, youtube, kakao, free)
        style: 분위기 칩 값 (밝고 경쾌한, 고급스러운, 따뜻한, 심플한, 강렬한)
        output: 받는 형태. combined(이미지와 문구), image(이미지만), text(문구 레이어만)
        reference_image: 사용자가 올린 상품 사진 바이트 (선택). PNG, JPG, WEBP 등
        adjustments: 조금 수정하기 칩 목록 (예: ["더 밝게", "텍스트 짧게"])
        seed: 비우면 랜덤. 조금 수정하기 때 이전 결과의 seed를 넘기면 구도가 유지됨 (klein만 적용)
        image_quality: 그림 품질. fast(빠르게, klein) 또는 detailed(더 정교하게, flare)
        text_quality: 문구 품질. basic(기본, Gemma) 또는 natural(더 자연스럽게, luna)

    Returns:
        AdImageResult: 이미지와 생성 정보

    Raises:
        ValueError: 필수 입력이 비었거나, output이나 품질 값이 잘못됐거나, 참고 사진을 읽을 수 없을 때
        TextGenerationError: 텍스트 모델이 실패했을 때 (폴백까지 실패 포함)
        ImageGenerationError: 이미지 모델이 실패했을 때 (폴백까지 실패 포함)
    """
    total_start = time.perf_counter()
    if not product_name.strip() or not message.strip():
        raise ValueError("상품 이름과 핵심 메시지는 꼭 입력해야 합니다.")
    if output not in OUTPUTS:
        raise ValueError(f"output은 {OUTPUTS} 중 하나여야 합니다.")
    if image_quality not in IMAGE_QUALITIES:
        raise ValueError(f"image_quality는 {IMAGE_QUALITIES} 중 하나여야 합니다.")
    check_text_quality(text_quality)
    adjustments = adjustments or []
    reference_png = _to_png(reference_image) if reference_image is not None else None
    size_scale = 1.25 if BIGGER_TEXT_ADJUSTMENT in adjustments else 1.0
    width, height = get_image_size(purpose)

    start = time.perf_counter()
    text_cost = 0.0
    text_model = ""
    text_reason = ""
    if SHORTEN_ADJUSTMENT in adjustments:
        message, shorten_result, text_reason = shorten_message(message, text_quality)
        text_cost += shorten_result.cost_usd
        text_model = shorten_result.model

    if output == "text":
        text_sec = time.perf_counter() - start
        start = time.perf_counter()
        layer_bytes, placement = render_text_layer(
            message, style, (width, height), size_scale
        )
        return AdImageResult(
            output=output,
            image_bytes=None,
            background_bytes=None,
            text_layer_bytes=layer_bytes,
            **_placement_fields(placement),
            message=message,
            prompt="",
            image_model="",
            image_fallback_reason="",
            text_model=text_model,
            text_fallback_reason=text_reason,
            product_source="",
            used_reference=False,
            width=width,
            height=height,
            text_sec=round(text_sec, 2),
            image_sec=0.0,
            overlay_sec=round(time.perf_counter() - start, 2),
            elapsed_sec=round(time.perf_counter() - total_start, 2),
            cost_usd=round(text_cost, 6),
            seed=None,
        )

    product_en, scene_en, product_source, describe_result, describe_reason = (
        describe_for_image(product_name, message, style, text_quality)
    )
    text_cost += describe_result.cost_usd
    text_model = describe_result.model
    text_reason = describe_reason or text_reason
    text_sec = time.perf_counter() - start

    prompt = build_image_prompt(
        product_en,
        scene_en,
        purpose=purpose,
        style=style,
        has_reference=reference_png is not None,
        adjustments=adjustments,
    )
    start = time.perf_counter()
    result, image_reason = _generate_image(
        product_name, prompt, width, height, reference_png, seed, image_quality
    )
    image_sec = time.perf_counter() - start

    start = time.perf_counter()
    if output == "combined":
        final_bytes, layer_bytes, placement = overlay_text(
            result.image_bytes, message, style, size_scale=size_scale
        )
    else:
        final_bytes, layer_bytes = result.image_bytes, None
        placement = place_text(result.image_bytes, message, style, size_scale)
    overlay_sec = time.perf_counter() - start
    width, height = Image.open(io.BytesIO(final_bytes)).size

    return AdImageResult(
        output=output,
        image_bytes=final_bytes,
        background_bytes=result.image_bytes,
        text_layer_bytes=layer_bytes,
        **_placement_fields(placement),
        message=message,
        prompt=prompt,
        image_model=result.model,
        image_fallback_reason=image_reason,
        text_model=text_model,
        text_fallback_reason=text_reason,
        product_source=product_source,
        used_reference=reference_png is not None,
        width=width,
        height=height,
        text_sec=round(text_sec, 2),
        image_sec=round(image_sec, 2),
        overlay_sec=round(overlay_sec, 2),
        elapsed_sec=round(time.perf_counter() - total_start, 2),
        cost_usd=round(result.cost_usd + text_cost, 6),
        seed=result.seed,
    )


def _placement_fields(placement):
    """TextPlacement를 결과 칸 이름에 맞게 바꿉니다."""
    return {"text_layout": placement.layout, "text_box": placement.box}


def _generate_image(
    product_name, prompt, width, height, reference_png, seed, image_quality
):
    """품질에 맞는 이미지 모델로 만듭니다.

    detailed면 처음부터 flare를 쓰고, fast면 klein으로 만들되 아래 경우에는 flare로 폴백합니다.
    - 품목 사전에서 klein이 못 그리는 품목(local_ok=False)인데 참고 사진이 없을 때: 처음부터 flare
    - klein을 불러오지 못했거나 생성에 실패했을 때 (GPU 없음, 메모리 부족 등)

    Returns:
        tuple: (ImageResult, 폴백 이유. 폴백 안 했으면 빈 문자열)

    Raises:
        ImageGenerationError: 폴백을 끈 상태에서 klein이 실패했거나, flare까지 실패했을 때
    """
    if image_quality == "detailed":
        return _generate_with_flare(prompt, width, height, reference_png), ""

    entry = lookup(product_name)
    if (
        config.USE_FALLBACK
        and entry
        and not entry["local_ok"]
        and reference_png is None
    ):
        reason = "klein이 잘 못 그리는 품목이라 처음부터 flare 사용"
        return _generate_with_flare(prompt, width, height, reference_png), reason

    try:
        result = ai_models.get_klein().generate(
            prompt, width, height, reference_image=reference_png, seed=seed
        )
        return result, ""
    except ImageGenerationError as e:
        if not config.USE_FALLBACK:
            raise
        reason = f"klein 실패로 flare 사용 ({e})"
        return _generate_with_flare(prompt, width, height, reference_png), reason


def _generate_with_flare(prompt, width, height, reference_png):
    """flare로 이미지를 만듭니다."""
    return ai_models.get_flare().generate(
        prompt, width, height, reference_image=reference_png
    )


def _to_png(image_bytes):
    """사용자가 올린 사진을 PNG 바이트로 바꿉니다. 어떤 형식이든 모델에 같은 형태로 넘기기 위해서입니다.

    Raises:
        ValueError: 이미지로 읽을 수 없는 파일일 때
    """
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        raise ValueError(f"참고 사진을 읽을 수 없습니다: {e}") from e
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
