"""이미지 프롬프트를 만드는 모듈.

이미지 모델은 글자 없는 이미지만 만들고, 문구는 나중에 text_overlay.py가 얹습니다.
그래서 프롬프트는 영어로만 쓰고, 글자를 떠올리게 하는 단어(headline, shop, sign 등)는 넣지 않습니다.
"""

PURPOSE_SIZES = {
    "instagram": (1024, 1024),
    "commerce": (1024, 1024),
    "youtube": (1536, 864),
    "kakao": (1024, 1536),
    "free": (1024, 1024),
}
DEFAULT_PURPOSE = "free"

FRAMING = {
    "instagram": "square composition",
    "commerce": "the product centered on a clean simple background",
    "youtube": "wide landscape composition with one clear focal point",
    "kakao": "tall vertical composition",
    "free": "balanced composition",
}

STYLE_PRESETS = {
    "밝고 경쾌한": "bright, cheerful, vivid colors, lively mood",
    "고급스러운": "luxurious, premium, elegant, dramatic soft lighting",
    "따뜻한": "warm, cozy, soft warm lighting, inviting atmosphere",
    "심플한": "minimal, clean, simple composition, lots of negative space",
    "강렬한": "bold, strong contrast, dynamic, energetic",
}

IMAGE_ADJUSTMENTS = {
    "더 밝게": "Make the whole image brighter with light, airy lighting.",
    "배경 단순하게": "Use a simpler, cleaner background with fewer objects.",
}
TEXT_ADJUSTMENTS = {"글자 더 크게", "텍스트 짧게"}


def get_image_size(purpose):
    """목적에 맞는 이미지 크기를 반환합니다.

    Args:
        purpose: 광고 목적 (instagram, commerce, youtube, kakao, free)

    Returns:
        tuple: (가로, 세로)
    """
    return PURPOSE_SIZES.get(purpose, PURPOSE_SIZES[DEFAULT_PURPOSE])


def build_image_prompt(
    product,
    scene,
    purpose=DEFAULT_PURPOSE,
    style=None,
    has_reference=False,
    adjustments=None,
):
    """글자 없는 광고 이미지용 영어 프롬프트를 만듭니다.

    Args:
        product: 상품 생김새 영어 묘사 (copywriter.describe_for_image 결과)
        scene: 장면 영어 묘사
        purpose: 광고 목적
        style: 분위기 칩 값
        has_reference: 참고 사진이 있는지
        adjustments: 조금 수정하기 칩 목록

    Returns:
        str: 이미지 프롬프트
    """
    framing = FRAMING.get(purpose, FRAMING[DEFAULT_PURPOSE])
    parts = []
    if has_reference:
        parts += [
            "Use the product in the reference image as the main subject.",
            (
                "Keep the product's shape, colors and packaging exactly as they are. "
                "Only change the background, lighting and composition."
            ),
        ]
    parts += [
        f"A professional commercial photograph of {product}.",
        f"{scene.rstrip('.')}.",
        f"{framing[0].upper() + framing[1:]}.",
    ]
    if style in STYLE_PRESETS:
        parts.append(f"Mood: {STYLE_PRESETS[style]}.")
    for adjustment in adjustments or []:
        if adjustment in IMAGE_ADJUSTMENTS:
            parts.append(IMAGE_ADJUSTMENTS[adjustment])
    parts += [
        # 문구 얹을 자리
        "Keep the upper third of the frame as calm, softly blurred background with no objects in it.",
        "No text, no letters, no words, no numbers, no signage, no labels, no logos, no watermark.",
        "Photorealistic, high quality.",
    ]
    return " ".join(parts)


def build_scene_prompt(scene, purpose=DEFAULT_PURPOSE, style=None, adjustments=None):
    """상품 없는 장면 프롬프트 (keep_product, api_spec_next 4장).

    상품은 사용자 사진을 그대로 프론트가 가운데 아래(가로 60%, 세로 55%)에 놓으므로,
    그 자리를 비우고 상품 이름·생김새는 넣지 않습니다 (넣으면 모델이 상품을 그림).
    문구는 위쪽에 얹으므로 위쪽도 조용하게 둡니다.

    Args:
        scene: 장면 영어 묘사 (copywriter.describe_for_image 결과)
        purpose: 광고 목적
        style: 분위기 칩 값
        adjustments: 조금 수정하기 칩 목록

    Returns:
        str: 이미지 프롬프트
    """
    framing = FRAMING.get(purpose, FRAMING[DEFAULT_PURPOSE]).replace(
        "the product centered on a clean simple background", "clean simple background"
    )
    parts = [
        "A professional commercial product photography backdrop with no product in it.",
        f"Setting: {scene.rstrip('.')}.",
        f"{framing[0].upper() + framing[1:]}, eye-level camera.",
        (
            "The lower center of the frame (about 60 percent of the width and 55 percent of the height) "
            "is an empty, flat, uncluttered surface such as a table top or pedestal, "
            "with nothing standing on it, ready for a product to be placed later."
        ),
        "Props and decorations only at the far edges and in the soft background.",
    ]
    if style in STYLE_PRESETS:
        parts.append(f"Mood: {STYLE_PRESETS[style]}.")
    for adjustment in adjustments or []:
        if adjustment in IMAGE_ADJUSTMENTS:
            parts.append(IMAGE_ADJUSTMENTS[adjustment])
    parts += [
        "Keep the upper third of the frame as calm, softly blurred background with no objects in it.",
        "No people, no hands.",
        "No text, no letters, no words, no numbers, no signage, no labels, no logos, no watermark.",
        "Photorealistic, high quality.",
    ]
    return " ".join(parts)
