"""Terra 광고 조언 챗봇(core/advisor.py) 테스트. 모델은 부르지 않고 ask_json을 바꿔 끼웁니다."""

import json

import pytest

from just_make_it.core import advisor
from just_make_it.core.structured import JsonResult

USER = {"role": "user", "text": "인스타 처음인데 뭐부터 해요?"}


@pytest.fixture
def fake_ask(monkeypatch):
    """ask_json에 들어온 값을 기록하고 정해 둔 답을 돌려줌."""
    calls = []
    answer = {
        "off_topic": False,
        "reply": " 프로필 사진부터 가게 간판 사진으로 바꿔 보세요. ",
        "chips": ["해시태그는요?", " ", "언제 올려요?", "사진 팁", "넷째"],
        "go_create": False,
    }

    def fake(instructions, user_input, schema, name, quality):
        calls.append(
            {"input": json.loads(user_input), "name": name, "quality": quality}
        )
        return JsonResult(
            data=dict(answer), model="m", source="openai", cost_usd=0.01, elapsed_sec=1
        )

    monkeypatch.setattr(advisor, "ask_json", fake)
    return calls, answer


def test_advise_returns_clean_reply(fake_ask):
    reply, result = advisor.advise([USER])
    assert reply["reply"] == "프로필 사진부터 가게 간판 사진으로 바꿔 보세요."
    assert reply["chips"] == ["해시태그는요?", "언제 올려요?", "사진 팁"]
    assert reply["off_topic"] is False and reply["go_create"] is False
    assert result.cost_usd == 0.01


def test_advise_passes_context_and_quality(fake_ask):
    calls, _ = fake_ask
    context = {"category": "카페", "product_name": "소금빵"}
    advisor.advise([USER], context, "basic")
    assert calls[0]["input"]["context"] == context
    assert calls[0]["quality"] == "basic"
    assert calls[0]["name"] == "advisor"


def test_advise_keeps_recent_history_only(fake_ask):
    calls, _ = fake_ask
    history = [{"role": "user", "text": str(i)} for i in range(15)]
    advisor.advise(history)
    sent = calls[0]["input"]["대화"]
    assert len(sent) == advisor.MAX_HISTORY
    assert sent[-1]["text"] == "14"


def test_advise_off_topic(fake_ask):
    _, answer = fake_ask
    answer.update(off_topic=True, chips=None, reply="광고 이야기로 돌아갈게요.")
    reply, _ = advisor.advise([{"role": "user", "text": "숙제 해줘"}])
    assert reply["off_topic"] is True
    assert reply["chips"] == []


def test_advise_empty_history():
    with pytest.raises(ValueError):
        advisor.advise([])


def test_schema_requires_all_fields():
    schema = advisor.ADVICE_SCHEMA
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
