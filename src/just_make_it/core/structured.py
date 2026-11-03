"""정해진 JSON 모양으로 답을 받는 텍스트 호출과 OpenAI Moderation.

상담(consultant.py)·문구 변환(copy_convert.py)이 씁니다. 서빙·서비스가 문자열을 파싱하지 않도록
모델이 JSON 스키마에 맞춰서만 답하게 합니다 (OpenAI Structured Outputs, Ollama format).

품질 값 quality
- terra: OpenAI gpt-5.6-terra (판단이 필요한 곳, 예: 상담 기획서)
- natural: OpenAI gpt-5.6-luna (형식 바꾸기·답 정리)
- basic: 로컬 Gemma 4 12B (하루 OpenAI 상한을 넘었을 때 서빙이 이 값으로 바꿔 부름)
"""

import json
import logging
import time
from dataclasses import dataclass

from just_make_it import config
from just_make_it.core import ai_models, deadline
from just_make_it.core.base import TextGenerationError

logger = logging.getLogger(__name__)

QUALITIES = ("terra", "natural", "basic")

_OPENAI = {
    "terra": (config.TERRA_MODEL, config.TERRA_PRICE_INPUT, config.TERRA_PRICE_OUTPUT),
    "natural": (config.LUNA_MODEL, config.LUNA_PRICE_INPUT, config.LUNA_PRICE_OUTPUT),
}


@dataclass
class JsonResult:
    """JSON 답 한 번.

    Args:
        data: 스키마에 맞춘 답
        model: 실제로 쓴 모델 이름
        source: openai 또는 local
        cost_usd: 예상 비용(달러). 로컬 모델은 0
        elapsed_sec: 걸린 시간(초)
    """

    data: dict
    model: str
    source: str
    cost_usd: float
    elapsed_sec: float


def ask_json(instructions, user_input, schema, name, quality="natural"):
    """지시문과 입력으로 schema 모양의 JSON 답을 받습니다.

    Args:
        instructions: 모델이 지켜야 할 규칙
        user_input: 입력
        schema: JSON 스키마 (모든 속성 required, additionalProperties false)
        name: 스키마 이름 (영문)
        quality: terra / natural / basic

    Returns:
        JsonResult

    Raises:
        ValueError: quality가 잘못됐을 때
        TextGenerationError: 호출 실패, 또는 JSON이 아닌 답이 왔을 때
    """
    if quality not in QUALITIES:
        raise ValueError(f"quality는 {QUALITIES} 중 하나여야 합니다.")
    start = time.perf_counter()
    if quality == "basic":
        result = ai_models.get_gemma().generate(
            instructions, user_input, max_tokens=800, json_schema=schema
        )
        return JsonResult(
            data=_parse(result.text),
            model=result.model,
            source="local",
            cost_usd=0.0,
            elapsed_sec=round(time.perf_counter() - start, 2),
        )

    model, price_in, price_out = _OPENAI[quality]
    if not config.OPENAI_API_KEY:
        raise TextGenerationError(
            "OPENAI_API_KEY가 없습니다. .env 파일을 확인해주세요."
        )
    try:
        client = deadline.openai_client(_openai_client(), model)
        response = client.responses.create(
            model=model,
            instructions=instructions,
            input=user_input,
            text={
                "format": {
                    "type": "json_schema",
                    "name": name,
                    "schema": schema,
                    "strict": True,
                }
            },
        )
    except deadline.DeadlineExceeded as e:
        raise TextGenerationError(str(e)) from e
    except Exception as e:
        raise TextGenerationError(f"{model} 호출 실패: {e}") from e

    usage = getattr(response, "usage", None)
    cost = (getattr(usage, "input_tokens", 0) or 0) * price_in + (
        getattr(usage, "output_tokens", 0) or 0
    ) * price_out
    return JsonResult(
        data=_parse(getattr(response, "output_text", "") or ""),
        model=model,
        source="openai",
        cost_usd=round(cost / 1_000_000, 6),
        elapsed_sec=round(time.perf_counter() - start, 2),
    )


def moderate(text):
    """OpenAI Moderation(무료)으로 유해한 내용인지 봅니다.

    유해성(혐오·괴롭힘·성적·폭력·자해·불법)만 거릅니다. 주제 이탈은 각 기능에서 따로 봅니다.
    키가 없거나 호출이 실패하면 막지 않고 False (기능이 멈추지 않게, 로그만 남김).

    Returns:
        bool: 걸렸으면 True
    """
    if not config.OPENAI_API_KEY or not text.strip():
        return False
    try:
        client = deadline.openai_client(_openai_client(), "moderation")
        response = client.moderations.create(model=config.MODERATION_MODEL, input=text)
        return bool(response.results and response.results[0].flagged)
    except Exception:
        logger.warning("Moderation 호출 실패 (막지 않고 진행)", exc_info=True)
        return False


_client = {}


def _openai_client():
    if "openai" not in _client:
        from openai import OpenAI

        _client["openai"] = OpenAI(
            api_key=config.OPENAI_API_KEY,
            timeout=config.OPENAI_TEXT_TIMEOUT,
            max_retries=config.OPENAI_MAX_RETRIES,
        )
    return _client["openai"]


def _parse(text):
    """모델 답을 dict로. ```json 감싸기나 앞뒤 공백은 벗김."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[4:] if text.startswith("json") else text
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise TextGenerationError(f"JSON이 아닌 답: {text[:80]}") from e
    if not isinstance(data, dict):
        raise TextGenerationError("JSON 객체가 아닌 답")
    return data
