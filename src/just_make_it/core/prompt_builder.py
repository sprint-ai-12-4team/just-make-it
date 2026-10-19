"""사용자 입력을 이미지 프롬프트로 바꾸는 모듈 (모든 모델 공통).

사장님은 프롬프트를 직접 쓰기 어렵기 때문에, 프론트에서 받은 선택값을
모델이 잘 알아듣는 문장으로 조립합니다.
"""

# 목적(매체)별 크기와 구도 힌트. 크기는 모델과 상관없이 원하는 비율로 적어둠
PURPOSE_PRESETS = {
    "instagram": {
        "size": (1024, 1024),
        "composition": "square social media post, eye-catching and well balanced",
    },
    "commerce": {
        "size": (1024, 1024),
        "composition": "e-commerce product thumbnail, product centered on a clean simple background",
    },
    "youtube": {
        "size": (1536, 864),
        "composition": "wide thumbnail, bold and high contrast, clear focal point",
    },
    "kakao": {
        "size": (1024, 1536),
        "composition": "vertical promotional image for a mobile messenger",
    },
    "free": {
        "size": (1024, 1024),
        "composition": "advertising image",
    },
}

# 프론트 STYLE_CHIPS를 영어 묘사로 변환
STYLE_PRESETS = {
    "밝고 경쾌한": "bright, cheerful, vivid colors, lively mood",
    "고급스러운": "luxurious, premium, elegant, dramatic soft lighting",
    "따뜻한": "warm, cozy, soft warm lighting, inviting atmosphere",
    "심플한": "minimal, clean, simple composition, lots of negative space",
    "강렬한": "bold, strong contrast, dynamic, energetic",
}

# 결과 화면의 조금 수정하기 칩을 영어 지시문으로 변환
# 글자 관련 칩은 이미지 안에 글자를 넣는 빠른 생성에서만 적용
ADJUSTMENT_PRESETS = {
    "글자 더 크게": "Make the headline text much larger and bolder.",
    "더 밝게": "Make the whole image brighter with light, airy lighting.",
    "배경 단순하게": "Use a simpler, cleaner background with fewer objects.",
    "텍스트 짧게": "Keep the headline on one short line.",
}
TEXT_ADJUSTMENTS = {"글자 더 크게", "텍스트 짧게"}

DEFAULT_PURPOSE = "free"


def get_image_size(purpose):
    """목적에 맞는 이미지 크기를 반환합니다.

    Args:
        purpose: 광고 목적 (instagram, commerce, youtube, kakao, free)

    Returns:
        tuple[int, int]: (가로, 세로). 모르는 목적이면 기본 크기
    """
    return PURPOSE_PRESETS.get(purpose, PURPOSE_PRESETS[DEFAULT_PURPOSE])["size"]


def build_image_prompt(
    product_name,
    message,
    purpose=DEFAULT_PURPOSE,
    style=None,
    include_text=True,
    has_reference=False,
    adjustments=None,
):
    """광고 이미지 프롬프트를 만듭니다.

    Args:
        product_name: 가게 또는 상품 이름
        message: 핵심 메시지 (예: 신메뉴 출시, 주말 20% 할인)
        purpose: 광고 목적
        style: 분위기 칩 값. 목록에 없으면 입력값 그대로 사용
        include_text: True면 이미지 안에 한글 문구 포함, False면 글자 없이 빈 공간만 남김
        has_reference: 사용자가 상품 사진을 올렸는지 여부
        adjustments: 조금 수정하기 칩 목록. 목록에 없는 값은 입력값 그대로 사용

    Returns:
        str: 이미지 프롬프트

    Raises:
        ValueError: 상품 이름이나 핵심 메시지가 비어 있을 때
    """
    product_name = product_name.strip()
    message = message.strip()
    if not product_name or not message:
        raise ValueError("상품 이름과 핵심 메시지는 꼭 입력해야 합니다.")

    preset = PURPOSE_PRESETS.get(purpose, PURPOSE_PRESETS[DEFAULT_PURPOSE])
    if has_reference:
        subject = (
            f"Create an advertising photo for a local shop selling '{product_name}', "
            "using the product in the reference image as the main subject."
        )
        keep = (
            "Keep the product's shape, colors, packaging and logo exactly as they are. "
            "Only change the background, lighting and composition."
        )
        lines = [subject, keep]
    else:
        lines = [
            f"A professional advertising photo for a local shop selling '{product_name}'."
        ]
    lines.append(f"Composition: {preset['composition']}.")

    if style:
        lines.append(f"Mood and style: {STYLE_PRESETS.get(style, style)}.")

    if include_text:
        # 번역하지 말고 그대로 쓰라고 강조해야 엉뚱한 글자가 덜 나옴
        lines.append(
            "Include this Korean headline text exactly as written, "
            f'large, clear and easy to read: "{message}". '
            "Do not translate it and do not add any other text."
        )
    else:
        lines.append(
            "Do not include any text, letters, numbers, logos or watermarks. "
            "Leave clean empty space for a headline to be added later. "
            f"The image should express this message: {message}."
        )

    for adjustment in adjustments or []:
        if adjustment in TEXT_ADJUSTMENTS and not include_text:
            continue
        lines.append(ADJUSTMENT_PRESETS.get(adjustment, adjustment))

    lines.append("High quality, realistic, commercial photography.")
    return " ".join(lines)
