"""AI로 꾸미기 (restyle): 만든 광고 이미지의 글자를 flare가 장면에 맞게 다시 그립니다.

글자 표현 실험(11-04~11-09, experiment/model-text의 flare_restyle)에서 채택한 방식입니다.
기본 결과(klein 배경 + PIL 글자)를 먼저 만든 뒤, 사용자가 고르면 덧붙이는 옵션으로 씁니다.

흐름
1. 글자 없는 원본에 기본형 PIL 글자를 얹음. 장식·테두리·그림자 없는 고운돋움, 흰색·검정 중
   그 자리 배경과 대비가 큰 색. 위치·줄바꿈·글자 모양만 전하는 뼈대
2. 글자 영역(조금 넓힘)만 투명한 mask를 만듦
3. flare 편집 API가 mask 안의 글자만 장면에 맞는 글씨체·색·효과로 새로 그림 (나머지 그림은 그대로)

주의
- 분위기별 디자인 묘사(글씨체·색)는 프롬프트에 넣지 않음. 넣으면 결과가 우리 PIL 디자인을
  따라감 (실험에서 확인). 분위기 칩은 "가게가 원하는 느낌" 힌트로만 넣음
- 결과 글자는 그림에 박혀서 옮길 수 없음. 글자를 고치려면 원본(background)에서 다시 시작
- OpenAI(flare)만 씀. klein은 한글을 쓰지 못함
"""

import io
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageStat

from just_make_it.core import ai_models
from just_make_it.core.text_overlay import overlay_text, text_area

# 분위기 칩 → 느낌 힌트 (글씨체·색은 정하지 않음)
STYLE_EN = {
    "밝고 경쾌한": "bright and cheerful",
    "따뜻한": "warm and cozy",
    "고급스러운": "luxurious and elegant",
    "심플한": "simple and minimal",
    "강렬한": "bold and energetic",
}
MASK_PAD = (
    0.15  # 글자 영역을 이만큼(가로·세로 비율) 넓혀서 다시 그림 (장식이 들어갈 여유)
)
# 기본형 PIL 글자 (text_overlay.DESIGNS와 같은 키). fill은 plain_text가 배경을 보고 고름
PLAIN_DESIGN = {
    "font": "dodum",
    "size": 0.1,
    "max_width": 0.8,
    "align": "center",
    "tracking": 0.0,
    "fill": (255, 255, 255),
    "stroke": None,
    "depth": None,
    "shadow": ((0, 0, 0, 0), 0.0, 0.0),
    "deco": None,
    "deco_color": None,
    "rotate": 0,
    "shear": 0.0,
}
PLAIN_FILLS = ((255, 255, 255), (28, 28, 28))
POSITIONS = ("top", "middle", "bottom")


@dataclass
class RestyleResult:
    """AI로 꾸미기 결과.

    Args:
        image_bytes: 글자를 다시 그린 최종 PNG (원본과 같은 크기)
        model: 실제로 쓴 이미지 모델 (flare)
        prompt: flare에 보낸 편집 지시
        elapsed_sec: flare 호출에 걸린 시간(초)
        cost_usd: 예상 비용(달러)
        text_box: 다시 그린 글자 자리 (x, y, 가로, 세로). mask는 이보다 MASK_PAD만큼 넓음
    """

    image_bytes: bytes
    model: str
    prompt: str
    elapsed_sec: float
    cost_usd: float
    text_box: tuple[int, int, int, int]


def restyle_prompt(message, style=None):
    """기본형 글자를 얹은 그림을 넣고, 글자 디자인만 장면에 맞게 새로 하게 하는 지시."""
    mood = f" The shop wants a {STYLE_EN[style]} feel." if style in STYLE_EN else ""
    return (
        f'This image contains the Korean text "{message}" in a plain placeholder font. '
        "Keep exactly the same characters, spelling and line breaks, "
        "at about the same size and position. "
        "Redesign the lettering yourself so it looks naturally part of this scene: "
        "choose the typeface, color, effects and decoration that best match the scene's "
        "mood, colors, lighting, materials and perspective, and keep it easy to read."
        f"{mood} "
        "Keep the rest of the image unchanged. Do not add any other text, logos or watermark."
    )


def plain_text(background_bytes, message, position="top", size_scale=1.0):
    """글자 없는 원본에 기본형 PIL 글자를 얹습니다 (꾸미기 전 뼈대).

    Args:
        background_bytes: 글자 없는 원본 PNG
        message: 얹을 문구
        position: top, middle, bottom (원본 결과의 text_layout 위치)
        size_scale: 글자 크기 배율 (원본 결과의 text_layout 값)

    Returns:
        tuple: (글자를 얹은 PNG, 글자 상자 (x, y, 가로, 세로))
    """
    image = Image.open(io.BytesIO(background_bytes)).convert("RGB")
    area = image.crop(text_area(position, *image.size))
    mean = tuple(int(v) for v in ImageStat.Stat(area).mean[:3])
    fill = max(PLAIN_FILLS, key=lambda color: contrast(color, mean))
    combined, _, placement = overlay_text(
        background_bytes,
        message,
        size_scale=size_scale,
        position=position,
        design={**PLAIN_DESIGN, "fill": fill},
    )
    return combined, placement.box


def text_mask(size, box, pad=MASK_PAD):
    """flare 편집용 mask: 글자 영역(pad만큼 넓힘)만 투명, 나머지는 불투명. 투명한 곳만 다시 그림."""
    width, height = size
    x, y, w, h = box
    px, py = int(w * pad), int(h * pad)
    mask = Image.new("RGBA", size, (0, 0, 0, 255))
    ImageDraw.Draw(mask).rectangle(
        (
            max(0, x - px),
            max(0, y - py),
            min(width, x + w + px),
            min(height, y + h + py),
        ),
        fill=(0, 0, 0, 0),
    )
    return _png(mask)


def restyle_text(background_bytes, message, style=None, position=None, size_scale=1.0):
    """만든 광고 이미지의 글자를 flare가 장면에 맞게 다시 그립니다 (AI로 꾸미기).

    서빙이 Deadline을 걸었으면 flare는 남은 시간만 기다리고 재시도하지 않습니다.

    Args:
        background_bytes: 글자 없는 원본 PNG (generate_ad_image 결과의 background_bytes)
        message: 그림에 쓸 문구
        style: 분위기 칩 값. 느낌 힌트로만 씀 (없어도 됨)
        position: top, middle, bottom. 비우면 top (원본 결과의 text_layout 값을 넘김)
        size_scale: 글자 크기 배율 0.6~1.6 (원본 결과의 text_layout 값을 넘김)

    Returns:
        RestyleResult: 다시 그린 이미지 (원본과 같은 크기)

    Raises:
        ValueError: 문구가 비었거나 위치·크기 값이 잘못됐을 때
        ImageGenerationError: OPENAI_API_KEY가 없거나 flare 호출이 실패했을 때
    """
    message = (message or "").strip()
    if not message:
        raise ValueError("꾸밀 문구가 없습니다.")
    position = position or "top"
    if position not in POSITIONS:
        raise ValueError(f"position은 {POSITIONS} 중 하나: {position}")

    size = Image.open(io.BytesIO(background_bytes)).size
    image, box = plain_text(background_bytes, message, position, size_scale)
    mask = text_mask(size, box)
    prompt = restyle_prompt(message, style)

    result = ai_models.get_flare().edit(image, mask, prompt, *size)
    return RestyleResult(
        image_bytes=_fit(result.image_bytes, size),
        model=result.model,
        prompt=prompt,
        elapsed_sec=result.elapsed_sec,
        cost_usd=result.cost_usd,
        text_box=box,
    )


def contrast(a, b):
    """두 RGB 색의 WCAG 대비 (1~21)."""
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _luminance(rgb):
    def channel(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _fit(png, size):
    """flare가 16의 배수로 맞춘 크기로 돌려주면 원본 크기로 되돌림 (글자 고치기·다운로드 크기 유지)."""
    image = Image.open(io.BytesIO(png))
    if image.size == tuple(size):
        return png
    return _png(image.convert("RGB").resize(size, Image.LANCZOS))


def _png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
