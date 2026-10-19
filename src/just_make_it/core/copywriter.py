"""광고 문구 추천 모듈.

핵심 메시지를 이미지에 넣기 좋은 짧은 한글 문구로 다듬어줍니다.
결과 화면의 텍스트 짧게 칩에서도 사용합니다.
"""

import re

from just_make_it.core.registry import DEFAULT_TEXT_BACKEND, get_text_model

# 좋은 문구 예시를 몇 개 보여주면 길이와 말투를 비슷하게 맞춰줌
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


def suggest_ad_copies(
    product_name, message, style=None, n=3, backend=DEFAULT_TEXT_BACKEND
):
    """광고 문구 후보를 추천합니다.

    Args:
        product_name: 가게 또는 상품 이름
        message: 핵심 메시지
        style: 분위기 칩 값
        n: 받을 문구 개수
        backend: 사용할 텍스트 모델 이름

    Returns:
        list: 광고 문구 후보 (최대 n개)

    Raises:
        ValueError: 상품 이름이나 핵심 메시지가 비어 있을 때
        TextGenerationError: 모델이 생성에 실패했을 때
    """
    if not product_name.strip() or not message.strip():
        raise ValueError("상품 이름과 핵심 메시지는 꼭 입력해야 합니다.")

    user_input = f"상품: {product_name} / 메시지: {message}"
    if style:
        user_input += f" / 분위기: {style}"
    user_input += f"\n문구 {n}개를 써줘."

    result = get_text_model(backend).generate(COPY_RULES, user_input)
    return parse_copies(result.text, n)


def shorten_message(message, backend=DEFAULT_TEXT_BACKEND):
    """긴 문구를 짧게 줄입니다.

    Args:
        message: 원래 문구
        backend: 사용할 텍스트 모델 이름

    Returns:
        str: 줄인 문구. 결과가 비어 있으면 원래 문구

    Raises:
        TextGenerationError: 모델이 생성에 실패했을 때
    """
    result = get_text_model(backend).generate(SHORTEN_RULES, message)
    copies = parse_copies(result.text, 1)
    return copies[0] if copies else message


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
        # 모델이 규칙을 어기고 번호나 기호를 붙여도 떼어냄 (1. / - / * / 따옴표)
        cleaned = re.sub(r"^\s*(\d+[.)]|[-*•])\s*", "", line).strip().strip("\"'")
        if cleaned:
            copies.append(cleaned)
    return copies[:n]
