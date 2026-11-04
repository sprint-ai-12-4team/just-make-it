"""게시 문구 키트: 고른 광고 문구를 채널별로 올릴 글로 바꿉니다 (api_spec_consult 4장).

품질 text_quality는 natural(luna, 기본)과 basic(Gemma, 하루 OpenAI 상한을 넘었을 때)을 씁니다.

규칙
- 모든 형식에서 오타·띄어쓰기를 먼저 정리 (fixed_typos: 고친 게 있었는지)
- 할인율·가격·날짜 같은 숫자는 입력 문구와 facts에 있는 것만 씀. 모델이 지어내면 한 번 다시 시키고,
  그래도 남으면 그 부분을 빼고 돌려줌 (모델에게 "지어내지 마"라고만 하는 것으로는 부족함)
- 과장 표현(최고·1위·100%)·효능 표현 금지
"""

import json
import re

from just_make_it.core.base import TextGenerationError
from just_make_it.core.structured import ask_json

FORMATS = (
    "instagram_post",
    "instagram_hashtags",
    "instagram_location",
    "instagram_story",
    "naver_coupon",
    "naver_blog_title",
    "store_description",
)
MAX_TEXT = 300

_STRING = {"type": "string"}
_LIST = {"type": "array", "items": {"type": "string"}}
_COUPON = {
    "type": "object",
    "properties": {"title": _STRING, "condition": _STRING, "period": _STRING},
    "required": ["title", "condition", "period"],
    "additionalProperties": False,
}
_RESULT_TYPE = {
    "instagram_post": _STRING,
    "instagram_hashtags": _LIST,
    "instagram_location": _LIST,
    "instagram_story": _STRING,
    "naver_coupon": _COUPON,
    "naver_blog_title": _LIST,
    "store_description": _STRING,
}

_TASK = {
    "instagram_post": (
        "인스타그램 게시물 본문을 써. 3~6줄. 첫 줄은 눈길을 끄는 한 문장, 가운데는 상품 이야기, "
        "마지막 줄은 방문·주문을 부르는 한 문장. 이모지는 1~3개까지. 해시태그는 넣지 마. 2,200자 이하."
    ),
    "instagram_hashtags": (
        "인스타그램 해시태그 10개. 각각 '#'으로 시작하고 띄어쓰기 없이. 동네 이름(area가 있을 때만)·"
        "업종·상품·분위기를 섞고 같은 태그를 반복하지 마."
    ),
    "instagram_location": (
        "인스타그램 위치 태그 후보 3개. area가 있으면 그 동네 이름과 '역 근처'·구 이름 같은 변형으로. "
        "area가 없으면 빈 배열. 실제로 없는 장소 이름을 지어내지 마."
    ),
    "instagram_story": "인스타그램 스토리에 얹을 15자 안팎의 짧은 한 줄.",
    "naver_coupon": (
        "네이버 플레이스 쿠폰 문구. title은 20자 이하. condition은 facts의 조건(할인 등)으로, "
        "없으면 '조건을 적어 주세요'. period는 facts의 기간으로, 없으면 '기간을 적어 주세요'."
    ),
    "naver_blog_title": "네이버 블로그 글 제목 3개. 각 25~35자, 검색할 만한 말(상품·동네)을 앞쪽에.",
    "store_description": (
        "스마트스토어·쿠팡 상품 설명 첫 문단. 3~5문장. 상품의 특징과 받는 사람이 얻는 점을 구체적으로."
    ),
}

RULES = """\
너는 소상공인 광고 글을 채널에 맞게 바꾸는 편집자야.
순서
1. 입력 문구의 오타·띄어쓰기를 먼저 고쳐. 고친 게 있으면 fixed_typos=true
2. 아래 [할 일]대로 결과를 result에 써
규칙
- 할인율·가격·날짜·개수 같은 숫자는 입력 문구나 facts에 있는 것만 써. 없는 숫자를 만들지 마
- 최고, 1위, 100% 같은 근거 없는 과장 표현과 병에 좋다 같은 효능 표현은 쓰지 마
- 존댓말, 사장님이 손님에게 말하는 말투
- 상품 이름·동네 이름은 입력된 그대로"""

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# 숫자 + 바로 뒤 단위. 긴 단위를 앞에 둬야 "개월"이 "개"로, "시간"이 "시"로 잘리지 않음
_NUMBER_UNIT = re.compile(
    r"(\d+(?:[.,]\d+)*)\s*(%|퍼센트|만\s?원|천\s?원|원|개월|개|명|인분|잔|병|일|주|시간|시|분|회|차)?"
)


def convert_copy(
    text, fmt, product_name=None, area=None, facts=None, text_quality="natural"
):
    """광고 문구를 채널별 형식으로 바꿉니다.

    Args:
        text: 바꿀 문구 (300자 이하)
        fmt: FORMATS 중 하나
        product_name: 상품·가게 이름 (선택)
        area: 동네 이름 (선택, 위치 태그·해시태그에만 씀)
        facts: 사장님이 입력한 값 (예: {"discount": "10%", "until": "11월 30일"})
        text_quality: natural(luna) 또는 basic(Gemma)

    Returns:
        dict: {"result", "fixed_typos", "source", "model", "cost_usd", "removed_numbers"}
            removed_numbers: 두 번 시켜도 지어낸 숫자가 남아 뺀 경우 True

    Raises:
        ValueError: 문구가 비었거나 길거나, 모르는 형식일 때
        TextGenerationError: 모델 호출 실패
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("바꿀 문구가 없어요.")
    if len(text) > MAX_TEXT:
        raise ValueError(f"문구는 {MAX_TEXT}자 이하로 보내 주세요.")
    if fmt not in FORMATS:
        raise ValueError(f"모르는 형식: {fmt}")
    facts = {str(k): str(v) for k, v in (facts or {}).items()}

    schema = {
        "type": "object",
        "properties": {"result": _RESULT_TYPE[fmt], "fixed_typos": {"type": "boolean"}},
        "required": ["result", "fixed_typos"],
        "additionalProperties": False,
    }
    user_input = json.dumps(
        {
            "문구": text,
            "상품": product_name or "",
            "동네": area or "",
            "facts": facts,
        },
        ensure_ascii=False,
    )
    instructions = f"{RULES}\n\n[할 일]\n{_TASK[fmt]}"
    allowed = _numbers(
        " ".join([text, product_name or "", area or "", *facts.values()])
    )

    cost = 0.0
    answer = ask_json(instructions, user_input, schema, "copy_convert", text_quality)
    cost += answer.cost_usd
    result = _clean(fmt, answer.data.get("result"))
    invented = _numbers(_flatten(result)) - allowed
    if invented:
        retry = ask_json(
            instructions
            + f"\n\n주의: 지난 답에 입력에 없는 숫자({', '.join(sorted(invented))})가 있었어. 빼고 다시 써.",
            user_input,
            schema,
            "copy_convert",
            text_quality,
        )
        cost += retry.cost_usd
        answer = retry
        result = _clean(fmt, retry.data.get("result"))
        invented = _numbers(_flatten(result)) - allowed
    removed = bool(invented)
    if removed:
        result = _drop_numbers(result, invented)
    return {
        "result": result,
        "fixed_typos": bool(answer.data.get("fixed_typos")),
        "source": answer.source,
        "model": answer.model,
        "cost_usd": round(cost, 6),
        "removed_numbers": removed,
    }


def _clean(fmt, result):
    """형식에 맞게 정리. 모양이 틀리면 TextGenerationError."""
    kind = _RESULT_TYPE[fmt]
    if kind is _STRING:
        if not isinstance(result, str) or not result.strip():
            raise TextGenerationError("빈 답")
        return result.strip()
    if kind is _LIST:
        if not isinstance(result, list):
            raise TextGenerationError("목록이 아닌 답")
        items = [str(x).strip() for x in result if str(x).strip()]
        if fmt == "instagram_hashtags":
            tags = []
            for item in items:
                tag = "#" + item.lstrip("#").replace(" ", "")
                if tag != "#" and tag not in tags:
                    tags.append(tag)
            items = tags[:10]
        if fmt in ("instagram_location", "naver_blog_title"):
            items = items[:3]
        return items
    if not isinstance(result, dict):
        raise TextGenerationError("쿠폰 모양이 아닌 답")
    return {k: str(result.get(k, "")).strip() for k in ("title", "condition", "period")}


def _flatten(result):
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        return " ".join(result)
    return " ".join(result.values())


def _numbers(text):
    return {m.replace(",", "") for m in _NUMBER.findall(text or "")}


def _drop_numbers(result, invented):
    """지어낸 숫자가 든 부분을 뺌: 목록은 그 항목을, 글은 그 숫자와 단위를."""

    def has(s):
        return bool(_numbers(s) & invented)

    def strip(s):
        out = _NUMBER_UNIT.sub(
            lambda m: "" if m.group(1).replace(",", "") in invented else m.group(),
            s,
        )
        return re.sub(r"[ \t]{2,}", " ", out).strip()

    if isinstance(result, str):
        return strip(result)
    if isinstance(result, list):
        return [x for x in result if not has(x)]
    return {k: strip(v) for k, v in result.items()}
