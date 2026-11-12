"""정량평가 요청(11-05) 서빙 테스트: S1 POST /advice · S2 reference_source · S3 /stats 정량평가 칸.

모델은 MockTextModels·Mock 이미지 생성기로 바꿔 GPU·API 비용 없이 실행된다.
실행: uv run pytest tests/test_eval_serving.py
"""

import pytest
from test_assistant import answer_all, start
from test_roadmap_api import generate, send_event
from test_serving import (  # noqa: F401 (isolate_env는 fixture)
    BASE_BODY,
    RecordingMock,
    db_rows,
    isolate_env,
    make_client,
    png_bytes,
)

from just_make_it.serving.assistant import MockTextModels
from just_make_it.serving.generators import GeneratorError, MockGenerator


def ask(client, text, advice_id=None, cid="user-1", **extra):
    return client.post(
        "/advice",
        json={"advice_id": advice_id, "text": text, **extra},
        headers={"X-Client-Id": cid},
    )


# ---------------------------------------------------------------------- S1 /advice
def test_advice_new_conversation_then_continue(tmp_path):
    models = MockTextModels()
    with make_client(tmp_path, text_models=models) as client:
        first = ask(client, "손님이 동네 주민인데 어디에 올려요?")
        assert first.status_code == 200, first.text
        body = first.json()
        second = ask(client, "사진은 어떻게 찍어요?", body["advice_id"]).json()
        third = ask(client, "이제 만들어 볼래요", body["advice_id"]).json()

    assert body["advice_id"].startswith("a_")
    assert body["reply"] and body["chips"] and body["go_create"] is False
    assert body["turn"] == 1 and body["max_turns"] == 12 and body["source"] == "openai"
    assert second["turn"] == 2 and third["go_create"] is True
    assert models.calls == [("advise", "terra")] * 3  # terra로 부름
    row = db_rows(tmp_path, "SELECT * FROM advices")[0]
    assert row["turn"] == 3 and row["client_id"] == "user-1"
    calls = db_rows(tmp_path, "SELECT kind FROM text_calls ORDER BY id")
    assert [c["kind"] for c in calls] == ["advice_start", "advice_turn", "advice_turn"]


def test_advice_uses_my_consult_brief_as_context(tmp_path):
    with make_client(tmp_path) as client:
        c = start(client, product_name="소금빵")
        answer_all(client, c["id"])  # 기획서까지
        mine = ask(client, "어디에 올려요?", consult_id=c["id"]).json()
        other = ask(client, "어디에 올려요?", consult_id=c["id"], cid="user-2").json()
    assert "기획서" in mine["reply"]
    assert "기획서" not in other["reply"]  # 남의 상담은 무시
    assert (
        db_rows(tmp_path, "SELECT consult_id FROM advices")[0]["consult_id"] == c["id"]
    )


def test_advice_errors(tmp_path):
    with make_client(tmp_path) as client:
        aid = ask(client, "안녕하세요 카페 해요").json()["advice_id"]
        empty = ask(client, "   ", aid)
        long = ask(client, "가" * 501, aid)
        missing = ask(client, "어디에 올려요?", "a_nope")
        others = ask(client, "어디에 올려요?", aid, cid="user-2")
        flagged = ask(client, "MODERATION_TEST 나쁜 말", aid)
        bad = client.post("/advice", json={"text": 3})
    assert empty.status_code == 400 and long.status_code == 413
    assert missing.status_code == 404 and others.status_code == 404
    assert flagged.status_code == 400 and bad.status_code == 422
    assert (
        db_rows(tmp_path, "SELECT turn FROM advices")[0]["turn"] == 2
    )  # Moderation도 턴은 셈
    flags = db_rows(tmp_path, "SELECT reason, consult_id FROM flags")
    assert flags == [{"reason": "advice_moderation", "consult_id": None}]


def test_advice_new_conversation_flagged_is_not_saved(tmp_path):
    with make_client(tmp_path) as client:
        res = ask(client, "MODERATION_TEST")
    assert res.status_code == 400
    assert db_rows(tmp_path, "SELECT * FROM advices") == []


def test_advice_off_topic_three_times_ends(tmp_path):
    with make_client(tmp_path) as client:
        aid = ask(client, "카페 홍보 어떻게 해요?").json()["advice_id"]
        replies = [ask(client, "주식 추천해 줘", aid).json() for _ in range(3)]
        after = ask(client, "다시 광고 얘기", aid)
    assert [r["ended"] for r in replies] == [False, False, True]
    assert replies[-1]["chips"] == [] and "마칠게요" in replies[-1]["reply"]
    assert after.status_code == 409
    flags = db_rows(tmp_path, "SELECT reason FROM flags")
    assert [f["reason"] for f in flags] == ["advice_off_topic"]


def test_advice_max_turns_and_daily_limit(tmp_path):
    with make_client(tmp_path, advice_max_turns=2, advice_daily_limit=2) as client:
        aid = ask(client, "카페 해요").json()["advice_id"]
        last = ask(client, "어디에 올려요?", aid).json()
        over = ask(client, "또 물어볼게요", aid)
        ask(client, "두 번째 대화")
        limit = ask(client, "세 번째 대화")
    assert last["ended"] is True and over.status_code == 409
    assert limit.status_code == 429


def test_advice_model_failure_is_503_and_not_counted(tmp_path):
    class Broken(MockTextModels):
        def advise(self, history, context, quality):
            raise GeneratorError("모델 없음")

    with make_client(tmp_path, text_models=Broken()) as client:
        res = ask(client, "카페 해요")
    assert res.status_code == 503
    assert db_rows(tmp_path, "SELECT * FROM advices") == []
    assert db_rows(tmp_path, "SELECT * FROM text_calls") == []


def test_advice_falls_back_to_local_when_budget_is_over(tmp_path):
    models = MockTextModels()
    with make_client(
        tmp_path, text_models=models, openai_daily_budget_usd=0.0001
    ) as client:
        client.app.state.manager.add_text_cost(1.0)
        res = ask(client, "카페 해요").json()
    assert res["source"] == "local" and models.calls == [("advise", "basic")]


# ---------------------------------------------------------------------- S2 reference_source
def photo_generate(client, source=None, **extra):
    data = {**BASE_BODY, **extra}
    if source:
        data["reference_source"] = source
    return client.post(
        "/generate",
        data=data,
        files={"reference_image": ("p.png", png_bytes(), "image/png")},
    )


def test_reference_source_saved_and_returned(tmp_path):
    with make_client(tmp_path) as client:
        up = photo_generate(client, "upload").json()
        stock = photo_generate(client, "stock").json()
        no_photo = client.post(
            "/generate", json={**BASE_BODY, "reference_source": "stock"}
        ).json()
        again = client.post(
            "/generate", json={**BASE_BODY, "parent_id": stock["id"]}
        ).json()
        bad = photo_generate(client, "camera")
        got = {
            name: client.get(f"/generations/{body['id']}").json()["input"]
            for name, body in [
                ("upload", up),
                ("stock", stock),
                ("no_photo", no_photo),
                ("again", again),
            ]
        }
    assert got["upload"]["reference_source"] == "upload"
    assert got["stock"]["reference_source"] == "stock"
    assert got["no_photo"]["reference_source"] is None  # 사진 없이 보내면 저장 안 함
    assert got["again"]["reference_source"] == "stock"  # 원본 사진을 다시 쓰면 이어 씀
    assert bad.status_code == 422


def test_reference_source_missing_for_old_and_photo_less(tmp_path):
    with make_client(tmp_path) as client:
        gid = generate(client)["id"]
        got = client.get(f"/generations/{gid}").json()["input"]
    assert got["reference_source"] is None


# ---------------------------------------------------------------------- S3 /stats
class LocalMock(MockGenerator):
    """backend가 local로 남는 mock (mock 결과는 정량평가에서 빠져서)."""

    @property
    def source(self):
        return "local"


class PaidMock(MockGenerator):
    @property
    def source(self):
        return "openai"

    def generate(self, spec):
        out = super().generate(spec)
        out.cost_usd = 0.04
        return out


def test_stats_eval_fields(tmp_path):
    with make_client(
        tmp_path, primary=LocalMock(0.01), premium=PaidMock(0.01)
    ) as client:
        up = photo_generate(client, "upload").json()["id"]
        photo_generate(client, "stock")
        plain = generate(client)["id"]
        paid = generate(client, image_model="openai-image-2.6-flare")["id"]
        generate(client, parent_id=plain)  # plain을 다시 만들기 (원본 사진 없음 → none)
        send_event(client, up, "download")
        stats = client.get("/stats").json()

    total = stats["total"]
    assert total["generated"] == 5
    assert total["local_rate"] == pytest.approx(4 / 5, abs=1e-3)
    assert total["cost_usd"] == pytest.approx(0.04)
    assert total["cost_per_image_usd"] == pytest.approx(0.04 / 5, abs=1e-4)
    assert total["error_rate"] == 0.0
    assert total["seconds_p50"] is not None
    assert total["seconds_p95"] >= total["seconds_p50"]
    ref = total["by_reference"]
    assert ref["upload"] == {"generated": 1, "download_rate": 1.0, "remake_rate": 0.0}
    assert ref["stock"]["generated"] == 1
    assert ref["none"]["generated"] == 3
    assert ref["none"]["remake_rate"] == pytest.approx(1 / 3, abs=1e-3)
    assert stats["days"][0]["local_rate"] == total["local_rate"]
    assert paid


def test_stats_eval_fields_skip_mock_and_count_errors(tmp_path):
    failing = LocalMock(0.01, fail_times=99)
    with make_client(tmp_path, primary=failing) as client:
        res = client.post("/generate", json=BASE_BODY)  # 실패 (fallback 없음)
        assert res.status_code == 503
        stats = client.get("/stats").json()
    total = stats["total"]
    assert total["generated"] == 0 and total["error_rate"] == 1.0
    assert total["seconds_p50"] is None and total["cost_per_image_usd"] is None
    assert total["by_reference"]["none"]["download_rate"] is None


def test_stats_eval_fields_null_when_only_mock(tmp_path):
    with make_client(tmp_path) as client:  # 기본 MockGenerator (backend mock)
        generate(client)
        total = client.get("/stats").json()["total"]
    assert total["generated"] == 1  # 기존 지표는 그대로
    assert total["local_rate"] is None and total["cost_usd"] is None
    assert total["error_rate"] is None
    assert total["by_reference"]["none"]["generated"] == 0
