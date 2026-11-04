"""지어낸 숫자를 뺄 때 단위까지 같이 빠지는지, Gemma JSON 답 길이 테스트."""

from just_make_it.core import consultant, copy_convert, structured
from just_make_it.core.base import TextResult


def test_keep_numbers_removes_unit_too():
    out = consultant._keep_numbers("오늘만 30% 할인, 2개 사면 1개 더", ["2"])
    assert out == "오늘만 할인, 2개 사면 더"


def test_keep_numbers_keeps_allowed_with_unit():
    out = consultant._keep_numbers("30% 할인 3,000원", ["30", "3,000"])
    assert out == "30% 할인 3,000원"


def test_keep_numbers_long_unit_first():
    assert consultant._keep_numbers("3개월 무료", []) == "무료"
    assert consultant._keep_numbers("2시간 주차", []) == "주차"


def test_drop_numbers_removes_unit_too():
    assert (
        copy_convert._drop_numbers("지금 30% 할인 중이에요", {"30"})
        == "지금 할인 중이에요"
    )
    assert copy_convert._drop_numbers(["#소금빵", "#30%할인"], {"30"}) == ["#소금빵"]


def test_gemma_json_gets_enough_tokens(monkeypatch):
    seen = {}

    class FakeGemma:
        def generate(self, instructions, user_input, max_tokens=300, json_schema=None):
            seen["max_tokens"] = max_tokens
            return TextResult(text='{"a": 1}', model="gemma", elapsed_sec=0.1)

    monkeypatch.setattr(structured.ai_models, "get_gemma", lambda: FakeGemma())
    result = structured.ask_json("규칙", "입력", {"type": "object"}, "t", "basic")
    assert result.data == {"a": 1} and result.source == "local"
    assert seen["max_tokens"] >= 1500
