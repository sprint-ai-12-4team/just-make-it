"""텍스트 모델이 맡는 일 세 가지.

1. 광고 문구 3개 추천
2. 긴 문구를 짧게 줄이기
3. 상품과 메시지를 이미지 모델용 영어 묘사로 바꾸기 (이미지 프롬프트에 한글이 들어가지 않게)

문구 추천 품질
- basic (기본): Gemma 4 12B. 실패하면 luna로 폴백
- natural (더 자연스럽게): gpt-5.6-luna
"""

import re

from just_make_it import config
from just_make_it.core import ai_models
from just_make_it.core.base import TextGenerationError
from just_make_it.core.product_dictionary import lookup

TEXT_QUALITIES = ("basic", "natural")

_EXAMPLES = """\
예시
- 상품: 소금빵 / 메시지: 신메뉴 출시 / 분위기: 따뜻한
  문구: 갓 구운 버터 향, 오늘의 첫 소금빵
- 상품: 동네꽃집 / 메시지: 주말 20% 할인 / 분위기: 밝고 경쾌한
  문구: 이번 주말엔 꽃 한 다발 20% 할인"""

COPY_RULES = f"""\
너는 소상공인 광고 문구를 쓰는 카피라이터야.
규칙
- 한 문구는 20자 안팎, 이미지 위에 얹기 좋게 짧고 읽기 쉽게
- 최고, 1위, 100% 같은 근거 없는 과장 표현과 의학적 효능 표현은 쓰지 않기
- 입력된 할인율, 가격, 날짜는 바꾸지 말고 그대로 쓰기
- 문구만 한 줄에 하나씩 출력하고 번호나 설명은 붙이지 않기

{_EXAMPLES}"""

SHORTEN_RULES = """\
너는 광고 문구를 줄이는 편집자야.
규칙
- 입력 문구의 핵심 뜻은 유지하고 12자 안팎으로 줄이기
- 할인율, 가격, 날짜는 바꾸지 말고 그대로 쓰기
- 줄인 문구 한 줄만 출력하기"""

SCENE_RULES = """\
너는 광고 사진 기획자야. 한국어 광고 정보를 이미지 생성 모델이 이해할 영어 묘사로 바꿔.
이미지 모델은 한국 음식이나 한국에서 유행하는 상품 이름을 모르는 경우가 많아.
그래서 상품 이름을 영어로 옮기지 말고, 처음 보는 사람도 그릴 수 있게 생김새를 묘사해.
규칙
- 반드시 영어로만 쓰고 한글은 쓰지 않기
- PRODUCT에는 모양, 크기, 색, 질감, 위에 올라간 토핑이나 장식을 구체적으로 쓰기
- 글자, 간판, 로고, 포스터, 메뉴판처럼 문자가 들어가는 물건은 묘사하지 않기
- 아래 두 줄 형식만 출력하기
PRODUCT: 상품의 생김새를 묘사한 영어 명사구
SCENE: 메시지와 분위기를 살린 사진 장면을 영어 한 문장으로

예시
- 상품: 떡볶이 / 메시지: 매운맛 신메뉴 / 분위기: 강렬한
  PRODUCT: chewy cylindrical white rice cakes coated in a glossy bright red spicy sauce, with sliced fish cakes and chopped green onions
  SCENE: A steaming shallow pan of the rice cakes under dramatic warm light with rising steam"""

DEFAULT_PRODUCT = "a freshly made product"
DEFAULT_SCENE = "an inviting close-up shot of the product"


def check_text_quality(text_quality):
    """문구 추천 품질 값이 맞는지 확인합니다.

    Raises:
        ValueError: basic, natural이 아닐 때
    """
    if text_quality not in TEXT_QUALITIES:
        raise ValueError(f"text_quality는 {TEXT_QUALITIES} 중 하나여야 합니다.")


def generate_text(instructions, user_input, text_quality="basic", max_tokens=300):
    """품질에 맞는 텍스트 모델로 글을 만듭니다.

    Args:
        instructions: 모델이 지켜야 할 규칙
        user_input: 사용자 입력
        text_quality: basic(Gemma) 또는 natural(luna)
        max_tokens: 최대로 쓸 토큰 수 (Gemma만 적용)

    Returns:
        tuple: (TextResult, 폴백 이유. 폴백 안 했으면 빈 문자열)

    Raises:
        TextGenerationError: 폴백을 끈 상태에서 Gemma가 실패했거나, luna까지 실패했을 때
    """
    check_text_quality(text_quality)
    if text_quality == "natural":
        return ai_models.get_luna().generate(instructions, user_input, max_tokens), ""
    try:
        return ai_models.get_gemma().generate(instructions, user_input, max_tokens), ""
    except TextGenerationError as e:
        if not config.USE_FALLBACK:
            raise
        result = ai_models.get_luna().generate(instructions, user_input, max_tokens)
        return result, f"Gemma 실패로 luna 사용 ({e})"


def suggest_ad_copies(product_name, message, style=None, n=3, text_quality="basic"):
    """광고 문구 후보를 추천합니다.

    Args:
        product_name: 가게 또는 상품 이름
        message: 핵심 메시지
        style: 분위기 칩 값
        n: 받을 문구 개수
        text_quality: basic(기본, Gemma) 또는 natural(더 자연스럽게, luna)

    Returns:
        list: 광고 문구 후보 (최대 n개)

    Raises:
        ValueError: 상품 이름이나 핵심 메시지가 비었거나 text_quality가 잘못됐을 때
        TextGenerationError: 텍스트 모델이 생성에 실패했을 때
    """
    if not product_name.strip() or not message.strip():
        raise ValueError("상품 이름과 핵심 메시지는 꼭 입력해야 합니다.")
    check_text_quality(text_quality)

    user_input = f"상품: {product_name} / 메시지: {message}"
    if style:
        user_input += f" / 분위기: {style}"
    user_input += f"\n문구 {n}개를 써줘."

    result, _ = generate_text(COPY_RULES, user_input, text_quality)
    return parse_copies(result.text, n)


def shorten_message(message, text_quality="basic"):
    """긴 문구를 짧게 줄입니다.

    Args:
        message: 원래 문구
        text_quality: basic(Gemma) 또는 natural(luna)

    Returns:
        tuple: (줄인 문구. 결과가 비어 있으면 원래 문구, TextResult, 폴백 이유)

    Raises:
        TextGenerationError: 텍스트 모델이 생성에 실패했을 때
    """
    result, reason = generate_text(SHORTEN_RULES, message, text_quality, max_tokens=60)
    copies = parse_copies(result.text, 1)
    return (copies[0] if copies else message), result, reason


def describe_for_image(product_name, message, style=None, text_quality="basic"):
    """상품과 메시지를 이미지 모델용 영어 묘사로 바꿉니다.

    품목 사전에 있는 상품은 사람이 쓴 생김새 묘사를 그대로 쓰고, 장면 묘사만 텍스트 모델이 씁니다.
    텍스트 모델이 한글을 섞어 쓰면 지워서, 이미지 프롬프트에 한글이 들어가지 않게 합니다.

    Args:
        product_name: 가게 또는 상품 이름
        message: 핵심 메시지
        style: 분위기 칩 값
        text_quality: basic(Gemma) 또는 natural(luna)

    Returns:
        tuple: (상품 묘사, 장면 묘사, 상품 묘사 출처, TextResult, 폴백 이유)
            출처는 "품목 사전" 또는 "텍스트 모델"

    Raises:
        TextGenerationError: 텍스트 모델이 생성에 실패했을 때
    """
    user_input = f"상품: {product_name} / 메시지: {message}"
    if style:
        user_input += f" / 분위기: {style}"
    result, reason = generate_text(SCENE_RULES, user_input, text_quality)
    text = result.text

    product = re.search(r"PRODUCT\W*:\W*(.+)", text, re.IGNORECASE)
    scene = re.search(r"SCENE\W*:\W*(.+)", text, re.IGNORECASE)
    product = _remove_korean(product.group(1)) if product else ""
    scene = _remove_korean(scene.group(1)) if scene else ""

    entry = lookup(product_name)
    if entry:
        return entry["description"], scene or DEFAULT_SCENE, "품목 사전", result, reason
    return (
        product or DEFAULT_PRODUCT,
        scene or DEFAULT_SCENE,
        "텍스트 모델",
        result,
        reason,
    )


def parse_copies(text, n):
    """모델 출력에서 문구만 뽑아냅니다.

    Args:
        text: 모델이 돌려준 원문
        n: 최대 개수

    Returns:
        list: 정리된 문구 목록
    """
    copies = []
    for line in text.splitlines():
        cleaned = re.sub(r"^\s*(\d+[.)]|[-*•])\s*", "", line).strip().strip("\"'")
        if cleaned:
            copies.append(cleaned)
    return copies[:n]


def _remove_korean(text):
    """한글과 빈 괄호, 앞뒤 기호를 지웁니다."""
    text = re.sub(r"[가-힣ㄱ-ㅎㅏ-ㅣ]", "", text)
    text = re.sub(r"\(\s*\)", "", text)
    return re.sub(r"\s+", " ", text).strip(" .\"'*")
