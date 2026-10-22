"""문구를 이미지에 얹는 모듈.

이미지 모델은 글자 없는 이미지만 만들고, 텍스트 모델이 만든 문구는 여기서 얹습니다.
분위기 칩마다 글꼴, 색, 테두리, 장식, 기울기가 다른 디자인 5종이 있고,
이미지에서 물체가 적은 곳을 찾아 배경 밝기에 맞는 색으로 넣습니다.

글꼴은 모두 무료이고 상업적으로 쓸 수 있는 글꼴(OFL)이며 assets/fonts에 들어 있습니다.
"""

import io
import math
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

FONT_DIR = Path(__file__).parent / "assets" / "fonts"
FONTS = {
    "jua": FONT_DIR / "Jua.woff",
    "yeonsung": FONT_DIR / "YeonSung.woff",
    "batang": FONT_DIR / "GowunBatang-Bold.woff",
    "dodum": FONT_DIR / "GowunDodum.woff",
    "blackhan": FONT_DIR / "BlackHanSans.woff",
}
# 다른 글꼴에 없는 글자가 문구에 있으면 이 글꼴로 대신 씀 (한글 전체를 가진 글꼴)
FALLBACK_FONT = "dodum"

# 문구를 놓을 수 있는 위치와 각 위치의 세로 범위 (이미지 높이 비율)
POSITIONS = {
    "top": (0.03, 0.38),
    "middle": (0.32, 0.68),
    "bottom": (0.62, 0.97),
}
SIZE_SCALE_RANGE = (0.6, 1.6)


@dataclass
class TextPlacement:
    """문구를 어디에, 어떤 글꼴과 크기로 놓았는지.

    Args:
        position: 위치 (top, middle, bottom)
        font: 실제로 쓴 글꼴 키 (jua, yeonsung, batang, dodum, blackhan)
        size_scale: 글자 크기 배율
        x: 문구 레이어 왼쪽 위 가로 위치(px)
        y: 문구 레이어 왼쪽 위 세로 위치(px)
        width: 문구 레이어 가로 크기(px). 테두리, 그림자, 장식 포함
        height: 문구 레이어 세로 크기(px). 테두리, 그림자, 장식 포함
    """

    position: str
    font: str
    size_scale: float
    x: int
    y: int
    width: int
    height: int

    @property
    def layout(self):
        """API 스펙의 text_layout 형식."""
        return {
            "position": self.position,
            "font": self.font,
            "size_scale": self.size_scale,
        }

    @property
    def box(self):
        """문구 레이어 위치와 크기 (x, y, 가로, 세로)."""
        return (self.x, self.y, self.width, self.height)


DESIGNS = {
    "밝고 경쾌한": {
        "font": "jua",
        "size": 0.13,
        "max_width": 0.72,
        "align": "center",
        "tracking": 0.0,
        "fill": (255, 255, 255),
        "stroke": ((232, 84, 120), 0.09),
        "depth": ((150, 40, 75), 0.0, 0.07),
        "shadow": ((0, 0, 0, 110), 0.08, 0.12),
        "deco": "sparkle",
        "deco_color": (255, 226, 110),
        "rotate": -3,
        "shear": 0.0,
    },
    "따뜻한": {
        "font": "yeonsung",
        "size": 0.12,
        "max_width": 0.74,
        "align": "center",
        "tracking": 0.0,
        "fill": (255, 247, 232),
        "stroke": ((122, 72, 40), 0.06),
        "depth": None,
        "shadow": ((90, 50, 25, 170), 0.12, 0.05),
        "deco": "wave",
        "deco_color": (255, 236, 205),
        "rotate": -2,
        "shear": 0.0,
    },
    "고급스러운": {
        "font": "batang",
        "size": 0.085,
        "max_width": 0.7,
        "align": "center",
        "tracking": 0.12,
        "fill": "gold",
        "stroke": None,
        "depth": None,
        "shadow": ((0, 0, 0, 120), 0.06, 0.03),
        "deco": "rules",
        "deco_color": "same",
        "rotate": 0,
        "shear": 0.0,
    },
    "심플한": {
        "font": "dodum",
        "size": 0.075,
        "max_width": 0.5,
        "align": "left",
        "tracking": 0.02,
        "fill": "auto",
        "stroke": None,
        "depth": None,
        "shadow": ((0, 0, 0, 60), 0.05, 0.02),
        "deco": "accent",
        "deco_color": "same",
        "rotate": 0,
        "shear": 0.0,
    },
    "강렬한": {
        "font": "blackhan",
        "size": 0.14,
        "max_width": 0.78,
        "align": "center",
        "tracking": 0.0,
        "fill": (255, 232, 60),
        "stroke": ((20, 20, 20), 0.08),
        "depth": ((205, 25, 25), 0.06, 0.06),
        "shadow": ((0, 0, 0, 140), 0.06, 0.1),
        "deco": None,
        "deco_color": None,
        "rotate": -4,
        "shear": 0.18,
    },
}
DEFAULT_DESIGN = "밝고 경쾌한"


def text_area(position, width, height):
    """위치 이름에 해당하는 영역 (왼쪽, 위, 오른쪽, 아래)."""
    top, bottom = POSITIONS[position]
    return (0, int(height * top), width, int(height * bottom))


def calm_area(image):
    """위쪽과 아래쪽 중 물체가 적은 쪽 이름(top 또는 bottom)을 고릅니다. 위쪽을 조금 우대합니다."""
    width, height = image.size
    edges = image.convert("L").filter(ImageFilter.FIND_EDGES)
    busy = {
        name: ImageStat.Stat(edges.crop(text_area(name, width, height))).mean[0]
        for name in ("top", "bottom")
    }
    busy["top"] *= 0.85
    return min(busy, key=busy.get)


def check_layout(position=None, font=None, size_scale=1.0):
    """위치, 글꼴, 크기 값이 맞는지 확인합니다.

    Raises:
        ValueError: 없는 위치나 글꼴이거나 크기 배율이 범위를 벗어났을 때
    """
    if position is not None and position not in POSITIONS:
        raise ValueError(f"position은 {list(POSITIONS)} 중 하나여야 합니다.")
    if font is not None and font not in FONTS:
        raise ValueError(f"font는 {list(FONTS)} 중 하나여야 합니다.")
    low, high = SIZE_SCALE_RANGE
    if not low <= size_scale <= high:
        raise ValueError(f"size_scale은 {low}~{high} 사이여야 합니다.")


def line_width(text, font, tracking):
    """자간을 넣었을 때 한 줄의 가로 길이."""
    if not tracking:
        return font.getlength(text)
    return sum(font.getlength(ch) for ch in text) + tracking * (len(text) - 1)


def split_lines(text, font, tracking, max_width):
    """한 줄에 안 들어가면 쉼표나 공백 기준으로 두 줄로 나눕니다."""
    if line_width(text, font, tracking) <= max_width:
        return [text]
    for sep in [", ", ",", " "]:
        positions = [i for i in range(len(text)) if text.startswith(sep, i)]
        if positions:
            cut = min(positions, key=lambda i: abs(i - len(text) / 2))
            first = text[: cut + (1 if sep.startswith(",") else 0)].strip()
            return [first, text[cut + len(sep) :].strip()]
    middle = len(text) // 2
    return [text[:middle], text[middle:]]


def draw_line(draw, xy, text, font, tracking, **kwargs):
    """자간을 반영해서 한 줄을 그립니다."""
    x, y = xy
    if not tracking:
        draw.text((x, y), text, font=font, **kwargs)
        return
    for ch in text:
        draw.text((x, y), ch, font=font, **kwargs)
        x += font.getlength(ch) + tracking


def sparkle(draw, cx, cy, size, color, outline, side):
    """글자 옆 반짝이 선 3개. side는 -1(왼쪽) 또는 1(오른쪽)."""
    width = max(3, int(size * 0.07))
    for angle in (-35, 0, 35):
        rad = math.radians(angle)
        x1, y1 = (
            cx + side * math.cos(rad) * size * 0.25,
            cy + math.sin(rad) * size * 0.25,
        )
        x2, y2 = cx + side * math.cos(rad) * size * 0.6, cy + math.sin(rad) * size * 0.6
        for w, c in ((width + 4, outline), (width, color)):
            draw.line((x1, y1, x2, y2), fill=c, width=w)
            for x, y in ((x1, y1), (x2, y2)):
                draw.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=c)


@cache
def _glyphs(font_path):
    """글꼴이 가진 글자 목록. 확인할 수 없으면 None."""
    try:
        from fontTools.ttLib import TTFont

        return frozenset(TTFont(font_path).getBestCmap())
    except (ImportError, OSError, KeyError, ValueError, TypeError):
        return None


def has_all_glyphs(font_path, text):
    """글꼴에 문구의 모든 글자가 있는지 확인합니다. 확인할 수 없으면 있다고 봅니다."""
    glyphs = _glyphs(str(font_path))
    if glyphs is None:
        return True
    return all(ord(ch) in glyphs for ch in text if not ch.isspace())


def design_text(
    text,
    mood=None,
    size=(1024, 1024),
    size_scale=1.0,
    image=None,
    position=None,
    font=None,
):
    """분위기에 맞는 디자인으로 문구만 그린 투명 레이어를 만듭니다.

    색, 테두리, 장식, 기울기는 분위기(mood)를 따르고, 글꼴만 font로 바꿀 수 있습니다.
    이미지가 있으면 배경 밝기를 보고 글자색을 정하고, 위치를 비우면 물체가 적은 쪽(top, bottom)을 고릅니다.
    이미지가 없으면(텍스트만 받을 때) 사진 위에서 잘 보이는 밝은 글자로 그리고, 위치를 비우면 top에 놓습니다.

    Args:
        text: 그릴 문구
        mood: 분위기 칩 값 (밝고 경쾌한, 따뜻한, 고급스러운, 심플한, 강렬한). 없으면 밝고 경쾌한
        size: 문구를 놓을 이미지 크기 (가로, 세로). 글자 크기를 이 크기에 맞춰 정함
        size_scale: 글자 크기 배율 (0.6~1.6). 글자 더 크게 칩을 누르면 1.25
        image: 문구를 놓을 RGBA 이미지. 없으면 None
        position: 위치 (top, middle, bottom). 비우면 자동
        font: 글꼴 키 (jua, yeonsung, batang, dodum, blackhan). 비우면 분위기 글꼴

    Returns:
        tuple: (글자 부분만 잘라낸 투명 RGBA 레이어, TextPlacement)

    Raises:
        ValueError: 위치, 글꼴, 크기 배율 값이 잘못됐을 때
    """
    check_layout(position, font, size_scale)
    width, height = size
    d = DESIGNS.get(mood, DESIGNS[DEFAULT_DESIGN])
    if position is None:
        position = calm_area(image) if image is not None else "top"
    box = text_area(position, width, height)
    if image is not None:
        brightness = ImageStat.Stat(image.convert("L").crop(box)).mean[0]
        dark_bg = brightness < 150
    else:
        dark_bg = True

    fill = d["fill"]
    if fill == "auto":
        fill = (255, 255, 255) if dark_bg else (38, 38, 38)
    elif fill == "gold":
        fill = (236, 214, 160) if dark_bg else (70, 48, 28)
    deco_color = fill if d["deco_color"] == "same" else d["deco_color"]
    shadow_color = d["shadow"][0]
    if d["fill"] in ("auto", "gold") and not dark_bg:
        shadow_color = (255, 255, 255, 150)

    font_key = font or d["font"]
    if not FONTS[font_key].exists() or not has_all_glyphs(FONTS[font_key], text):
        font_key = FALLBACK_FONT
    font_path = str(FONTS[font_key])

    size = int(width * d["size"] * size_scale)
    while True:
        font = ImageFont.truetype(font_path, size)
        tracking = size * d["tracking"]
        lines = split_lines(
            text, font, tracking, width * min(0.9, d["max_width"] * size_scale)
        )
        line_h = int(size * 1.22)
        block_w = max(line_width(line, font, tracking) for line in lines)
        block_h = line_h * len(lines)
        max_w = width * min(0.9, d["max_width"] * size_scale)
        if (
            block_w <= max_w and block_h <= (box[3] - box[1]) * 0.85
        ) or size <= width * 0.04:
            break
        size -= 2

    stroke_w = max(2, int(size * d["stroke"][1])) if d["stroke"] else 0
    pad = int(size * 0.9)
    layer = Image.new("RGBA", (int(block_w) + pad * 2, block_h + pad * 2), (0, 0, 0, 0))
    lines_xy = []
    for i, line in enumerate(lines):
        lw = line_width(line, font, tracking)
        x = pad + (0 if d["align"] == "left" else (block_w - lw) / 2)
        lines_xy.append((x, pad + i * line_h, line, lw))

    shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    dy = size * d["shadow"][2]
    for x, y, line, _ in lines_xy:
        draw_line(
            sd,
            (x, y + dy),
            line,
            font,
            tracking,
            fill=shadow_color,
            stroke_width=stroke_w + 2,
            stroke_fill=shadow_color,
        )
    layer.alpha_composite(
        shadow.filter(ImageFilter.GaussianBlur(max(2, size * d["shadow"][1])))
    )

    draw = ImageDraw.Draw(layer)
    if d["depth"]:
        color, dx_r, dy_r = d["depth"]
        for x, y, line, _ in lines_xy:
            draw_line(
                draw,
                (x + size * dx_r, y + size * dy_r),
                line,
                font,
                tracking,
                fill=color,
                stroke_width=stroke_w,
                stroke_fill=color,
            )
    for x, y, line, _ in lines_xy:
        if d["stroke"]:
            draw_line(
                draw,
                (x, y),
                line,
                font,
                tracking,
                fill=fill,
                stroke_width=stroke_w,
                stroke_fill=d["stroke"][0],
            )
        else:
            draw_line(draw, (x, y), line, font, tracking, fill=fill)

    # 글꼴마다 위아래 여백이 달라서 실제 글자 범위 기준으로 장식 위치를 잡음
    first_x, first_y, first_line, first_w = lines_xy[0]
    last_x, last_y, last_line, last_w = lines_xy[-1]
    text_top = first_y + font.getbbox(first_line)[1]
    text_bottom = last_y + font.getbbox(last_line)[3]
    if d["deco"] == "sparkle":
        cy = (text_top + first_y + font.getbbox(first_line)[3]) / 2
        sparkle(draw, first_x - size * 0.2, cy, size, deco_color, d["stroke"][0], -1)
        sparkle(
            draw,
            first_x + first_w + size * 0.2,
            cy,
            size,
            deco_color,
            d["stroke"][0],
            1,
        )
    elif d["deco"] == "wave":
        y0 = text_bottom + size * 0.22
        points = [
            (last_x + t, y0 + math.sin(t / (size * 0.35) * math.pi) * size * 0.06)
            for t in range(0, int(last_w), 4)
        ]
        for w, c in (
            (max(4, int(size * 0.1)), d["stroke"][0]),
            (max(2, int(size * 0.06)), deco_color),
        ):
            draw.line(points, fill=c, width=w, joint="curve")
    elif d["deco"] == "rules":
        cx = pad + block_w / 2
        half = block_w * 0.42
        w = max(2, int(size * 0.035))
        for yy in (text_top - size * 0.35, text_bottom + size * 0.35):
            draw.line((cx - half, yy, cx - size * 0.25, yy), fill=deco_color, width=w)
            draw.line((cx + size * 0.25, yy, cx + half, yy), fill=deco_color, width=w)
            r = size * 0.12
            draw.polygon(
                [(cx, yy - r), (cx + r, yy), (cx, yy + r), (cx - r, yy)],
                fill=deco_color,
            )
    elif d["deco"] == "accent":
        w = max(3, int(size * 0.08))
        draw.line(
            (
                first_x,
                text_top - size * 0.4,
                first_x + size * 1.3,
                text_top - size * 0.4,
            ),
            fill=deco_color,
            width=w,
        )

    if d["shear"]:
        s = d["shear"]
        w0, h0 = layer.size
        layer = layer.transform(
            (int(w0 + s * h0), h0),
            Image.AFFINE,
            (1, s, -s * h0, 0, 1, 0),
            resample=Image.BICUBIC,
        )
    if d["rotate"]:
        layer = layer.rotate(d["rotate"], resample=Image.BICUBIC, expand=True)

    max_w = int(width * 0.96)
    ratio = 1.0
    if layer.width > max_w:
        ratio = max_w / layer.width
        layer = layer.resize((max_w, int(layer.height * ratio)), Image.LANCZOS)
    cy = (box[1] + box[3]) / 2
    x = int(width * 0.08) - pad if d["align"] == "left" else (width - layer.width) // 2
    y = int(cy - layer.height / 2)
    x = max(-pad // 2, min(x, width - layer.width + pad // 2))
    y = max(-pad // 2, min(y, height - layer.height + pad // 2))

    # 레이어에 남은 투명 여백을 잘라서, 웹에서 옮길 때 글자 영역만 잡히게 함
    bbox = layer.getchannel("A").getbbox()
    if bbox:
        layer = layer.crop(bbox)
        x, y = x + bbox[0], y + bbox[1]
    placement = TextPlacement(
        position=position,
        font=font_key,
        size_scale=size_scale,
        x=x,
        y=y,
        width=layer.width,
        height=layer.height,
    )
    return layer, placement


def render_text_layer(
    text, mood=None, size=(1024, 1024), size_scale=1.0, position=None, font=None
):
    """이미지 없이 문구 레이어만 PNG로 만듭니다. (텍스트만 받을 때)

    Returns:
        tuple: (투명 배경 PNG 바이트, TextPlacement)
    """
    layer, placement = design_text(
        text, mood, size, size_scale, position=position, font=font
    )
    return _to_png_bytes(layer), placement


def place_text(image_bytes, text, mood=None, size_scale=1.0, position=None, font=None):
    """문구를 얹지 않고, 이 이미지라면 어디에 어떤 글꼴로 놓을지만 계산합니다. (이미지만 받을 때)

    Returns:
        TextPlacement: 추천 위치와 글꼴
    """
    image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    return design_text(
        text, mood, image.size, size_scale, image, position=position, font=font
    )[1]


def overlay_text(
    image_bytes, text, mood=None, size_scale=1.0, position=None, font=None
):
    """문구를 이미지에 얹고, 얹은 이미지와 문구 레이어를 같이 돌려줍니다.

    Returns:
        tuple: (문구를 얹은 PNG 바이트, 문구 레이어 PNG 바이트, TextPlacement)
    """
    image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    layer, placement = design_text(
        text, mood, image.size, size_scale, image, position=position, font=font
    )
    canvas = Image.new("RGBA", image.size, (0, 0, 0, 0))
    canvas.paste(layer, (placement.x, placement.y))
    combined = Image.alpha_composite(image, canvas).convert("RGB")
    return _to_png_bytes(combined), _to_png_bytes(layer), placement


def render_text(image_bytes, text, mood=None, size_scale=1.0, position=None, font=None):
    """글자 없는 이미지에 문구를 얹습니다. 결과 화면의 글자 고치기도 이 함수를 씁니다.

    이미지는 다시 만들지 않고 문구, 위치, 글꼴, 크기만 바꿔 얹습니다.
    색, 테두리, 장식은 분위기(mood)를 그대로 따릅니다.

    Args:
        image_bytes: 글자 없는 원본 이미지 바이트 (결과의 background_bytes)
        text: 얹을 문구
        mood: 분위기 칩 값. 없으면 밝고 경쾌한
        size_scale: 글자 크기 배율 (0.6~1.6)
        position: 위치 (top, middle, bottom). 비우면 물체가 적은 쪽(top, bottom)을 자동으로 고름
        font: 글꼴 키 (jua, yeonsung, batang, dodum, blackhan). 비우면 분위기 글꼴

    Returns:
        tuple: (문구를 얹은 PNG 바이트, text_layout {"position", "font", "size_scale"})
            font는 실제로 쓴 글꼴. 글꼴에 없는 글자가 있으면 dodum

    Raises:
        ValueError: 위치, 글꼴, 크기 배율 값이 잘못됐을 때
    """
    combined, _, placement = overlay_text(
        image_bytes, text, mood, size_scale, position, font
    )
    return combined, placement.layout


def _to_png_bytes(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
