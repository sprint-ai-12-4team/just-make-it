"""상세페이지 5칸 문구를 만드는 모듈.

칸 구성은 대표 1칸, 좋은 점 3칸, 마무리 1칸입니다.
칸마다 사진 위에 얹을 제목과 설명, 그 칸 사진에 담을 장면(한국어 한 문장)을 만듭니다.
장면은 서빙이 generate_ad_image(output="image")의 메시지로 넘기면, 텍스트 모델이 영어 묘사로 바꿉니다.
"""

import re

from just_make_it.core.base import TextGenerationError
from just_make_it.core.copywriter import check_text_quality, generate_text

SECTION_COUNT = 5
ROLES = ["hero", "feature", "feature", "feature", "closing"]
MAX_FEATURES = 3
ATTEMPTS = 2  # 형식이 깨지면 한 번 더 시도
MAX_TOKENS = 900

DETAIL_RULES = """\
너는 스마트스토어 상세페이지를 쓰는 카피라이터야.
상세페이지는 위에서 아래로 5칸이고, 칸마다 사진 위에 제목과 설명을 얹어.
칸 구성
1. 대표: 핵심 메시지를 살려 상품을 한눈에 소개
2~4. 좋은 점: 상품 특징을 한 칸에 하나씩
5. 마무리: 구매를 권하는 따뜻한 한마디
규칙
- 제목은 15자 안팎, 설명은 30자 안팎으로 짧고 읽기 쉽게
- 최고, 1위 같은 근거 없는 과장 표현과 의학적 효능 표현은 쓰지 않기
- 입력된 할인율, 가격, 날짜, 수치는 바꾸지 말고 그대로 쓰기
- 특징이 주어지면 2~4칸 제목에 그 특징을 순서대로 그대로 쓰기
- 특징이 모자라면 상품과 메시지에서 자연스럽게 떠올릴 수 있는 장점으로 채우되,
  확인할 수 없는 수치나 인증은 지어내지 않기
- 장면은 그 칸 사진에 담을 모습을 한 문장으로. 칸마다 다른 장면으로 쓰고,
  글자·간판·로고·포장 문구는 넣지 않기
- 한 칸에 한 줄씩 `번호 | 제목 | 설명 | 장면` 형식으로 5줄만 출력하고 다른 말은 붙이지 않기

예시
- 상품: 수제 딸기잼 / 메시지: 국산 딸기 100% 신상품 / 특징: 무첨가, 소량 생산, 선물 포장
1 | 국산 딸기 100%, 그대로 담았어요 | 설탕 말고 딸기 맛만 남겼습니다 | 유리병에 담긴 붉은 딸기잼과 생딸기
2 | 무첨가 | 보존료·색소 없이 만들어요 | 나무 숟가락으로 떠낸 윤기 나는 잼
3 | 소량 생산 | 매일 필요한 만큼만 끓여요 | 작은 냄비에서 보글보글 끓는 딸기
4 | 선물 포장 | 리본 하나로 마음까지 전해요 | 리본으로 묶은 잼 병 두 개
5 | 아침 식탁에 딸기 한 스푼 | 오늘 주문하면 내일 만나요 | 잼을 바른 토스트와 커피가 놓인 아침 식탁"""

_LINE = re.compile(r"^\s*[-*]?\s*(\d)\s*[.)]?\s*\|(.+)$")


def suggest_detail_sections(
    product_name, message, features=None, style=None, text_quality="basic"
):
    """상세페이지 5칸 문구를 만듭니다.

    Args:
        product_name: 가게 또는 상품 이름
        message: 핵심 메시지
        features: 상품 특징 목록 (최대 3개). 주면 2~4칸 제목으로 그대로 씀. 비우면 텍스트 모델이 만듦
        style: 분위기 칩 값
        text_quality: basic(Gemma) 또는 natural(luna)

    Returns:
        list: 칸 5개 [{"role", "title", "body", "image_prompt"}]
            role은 hero, feature, feature, feature, closing
            image_prompt는 그 칸 사진에 담을 장면 (한국어 한 문장)

    Raises:
        ValueError: 상품 이름이나 핵심 메시지가 비었거나 text_quality가 잘못됐을 때
        TextGenerationError: 텍스트 모델이 실패했거나, 두 번 시도해도 5칸 형식이 나오지 않을 때
    """
    if not product_name.strip() or not message.strip():
        raise ValueError("상품 이름과 핵심 메시지는 꼭 입력해야 합니다.")
    check_text_quality(text_quality)
    features = [f.strip() for f in (features or []) if f and f.strip()][:MAX_FEATURES]

    user_input = build_detail_input(product_name, message, features, style)
    last_error = ""
    for _ in range(ATTEMPTS):
        result, _ = generate_text(
            DETAIL_RULES, user_input, text_quality, max_tokens=MAX_TOKENS
        )
        try:
            return parse_sections(result.text, features)
        except ValueError as e:
            last_error = str(e)
    raise TextGenerationError(last_error)


def build_detail_input(product_name, message, features, style):
    """텍스트 모델에 넘길 입력을 만듭니다."""
    text = f"상품: {product_name} / 메시지: {message}"
    if features:
        text += f" / 특징: {', '.join(features)}"
    if style:
        text += f" / 분위기: {style}"
    return text + "\n상세페이지 5칸을 써줘."


def parse_sections(text, features):
    """모델 출력을 5칸으로 나눕니다. 특징을 줬으면 2~4칸 제목은 그 특징으로 고정합니다.

    Raises:
        ValueError: 5칸이 다 나오지 않았을 때
    """
    found = {}
    for line in text.splitlines():
        match = _LINE.match(line.strip("`"))
        if not match:
            continue
        number = int(match.group(1))
        parts = [p.strip().strip("\"'") for p in match.group(2).split("|")]
        if not 1 <= number <= SECTION_COUNT or len(parts) < 2 or not parts[0]:
            continue
        found.setdefault(
            number - 1,
            {
                "title": parts[0],
                "body": parts[1],
                "image_prompt": parts[2] if len(parts) > 2 and parts[2] else parts[0],
            },
        )
    if len(found) < SECTION_COUNT:
        raise ValueError(f"상세페이지 문구가 {len(found)}칸뿐입니다: {text[:200]!r}")

    sections = []
    for i in range(SECTION_COUNT):
        section = {"role": ROLES[i], **found[i]}
        if 1 <= i <= len(features):
            section["title"] = features[i - 1]
        sections.append(section)
    return sections
