"""AI 광고 상담·게시 문구 변환·대기 카드·진행 막대 확장 테스트 (api_spec_consult).

모델은 MockTextModels와 가짜 ask_json으로 바꿔 API 비용·GPU 없이 실행된다.
실행: uv run pytest tests/test_assistant.py
"""

import time

import pytest
from test_detail_pages import DETAIL_BODY, wait_done
from test_serving import (  # noqa: F401 (isolate_env는 fixture)
    BASE_BODY,
    db_rows,
    isolate_env,
    make_client,
)

from just_make_it.core import consultant, copy_convert, deadline
from just_make_it.core.base import TextGenerationError
from just_make_it.core.structured import JsonResult, _parse
from just_make_it.serving.assistant import MockTextModels
from just_make_it.serving.generators import MockGenerator

CHIP_ANSWERS = [
    "카페",
    "신메뉴",
    "소금빵",
    "직장인",
    "맛",
    "이번 주말까지",
    "인스타그램",
]


def start(client, cid="user-1", **body):
    res = client.post("/consults", json=body, headers={"X-Client-Id": cid})
    assert res.status_code == 201, res.text
    return res.json()


def say(client, consult_id, text, chip=True, cid="user-1"):
    return client.post(
        f"/consults/{consult_id}/messages",
        json={"text": text, "chip": chip},
        headers={"X-Client-Id": cid},
    )


def answer_all(client, consult_id, cid="user-1"):
    last = None
    for text in CHIP_ANSWERS:
        last = say(client, consult_id, text, cid=cid)
        assert last.status_code == 200, last.text
    return last.json()


# ---------------------------------------------------------------------- 상담 흐름
def test_consult_fixed_questions_then_brief(tmp_path):
    models = MockTextModels()
    with make_client(tmp_path, text_models=models) as client:
        first = start(client, purpose="instagram")
        done = answer_all(client, first["id"])
        again = client.get(
            f"/consults/{first['id']}", headers={"X-Client-Id": "user-1"}
        ).json()

    assert first["reply"].startswith("안녕하세요") and first["chips"][0] == "카페"
    assert first["turn"] == 1 and first["brief"] is None and first["source"] is None
    brief = done["brief"]
    assert brief["product_name"] == "소금빵" and brief["purpose"] == "instagram"
    assert brief["period"] == "이번 주말까지" and len(brief["copies"]) == 2
    assert done["edits_left"] == 2 and done["source"] == "openai"
    # 칩만 눌렀으면 모델은 기획서 1번만 (질문 단계 비용 0)
    assert models.calls == [("write_brief", "terra")]
    assert len(again["messages"]) == 1 + 2 * len(CHIP_ANSWERS)
    assert again["brief"] == brief


def test_free_text_answer_uses_luna_and_off_topic_ends(tmp_path):
    models = MockTextModels()
    with make_client(tmp_path, text_models=models) as client:
        c = start(client)
        ok = say(client, c["id"], "동네 빵집이에요", chip=False).json()
        off = [
            say(client, c["id"], "주식 추천해 줘", chip=False).json() for _ in range(3)
        ]
        after = say(client, c["id"], "다시", chip=False)

    assert ok["reply"].startswith("좋아요") and ok["source"] == "openai"
    assert ("read_answer", "natural") in models.calls
    assert off[0]["reply"].startswith("그 부분은") and off[0]["chips"]
    assert off[2]["ended"] is True and off[2]["allow_free_text"] is False
    assert after.status_code == 409


def test_product_name_from_create_screen_becomes_chip(tmp_path):
    with make_client(tmp_path) as client:
        c = start(client, product_name="소금빵")
        say(client, c["id"], "카페")
        third = say(client, c["id"], "신메뉴").json()
    assert third["chips"] == ["소금빵"]


def test_brief_edits_twice_then_ends(tmp_path):
    with make_client(tmp_path) as client:
        c = start(client)
        answer_all(client, c["id"])
        one = say(client, c["id"], "문구를 더 짧게", chip=False).json()
        two = say(client, c["id"], "따뜻하게", chip=False).json()
        three = say(client, c["id"], "한 번 더", chip=False)
    assert one["edits_left"] == 1 and one["brief"]["copies"][0] == "문구를 더 짧게"
    assert two["edits_left"] == 0 and two["ended"] is True
    assert three.status_code == 409


def test_moderation_blocks_without_calling_model(tmp_path):
    models = MockTextModels()
    with make_client(tmp_path, text_models=models) as client:
        c = start(client)
        bad = say(client, c["id"], "MODERATION_TEST 나쁜 말", chip=False)
        saved = client.get(f"/consults/{c['id']}", headers={"X-Client-Id": "user-1"})
    assert bad.status_code == 400
    assert models.calls == []
    assert "MODERATION_TEST" not in saved.text  # 원문은 남기지 않음
    assert db_rows(tmp_path, "SELECT turn FROM consults")[0]["turn"] == 2


def test_consult_owner_limits_and_errors(tmp_path):
    with make_client(
        tmp_path, consult_daily_limit=2, consult_ip_daily_limit=3
    ) as client:
        a = start(client, cid="a")
        other = client.get(f"/consults/{a['id']}", headers={"X-Client-Id": "b"})
        missing = say(client, "nope", "카페")
        empty = say(client, a["id"], "   ", cid="a")
        long = say(client, a["id"], "가" * 501, chip=False, cid="a")
        start(client, cid="a")
        over = client.post("/consults", json={}, headers={"X-Client-Id": "a"})
        start(client, cid="b")
        ip_over = client.post("/consults", json={}, headers={"X-Client-Id": "c"})
    assert other.status_code == 404
    assert missing.status_code == 404
    assert empty.status_code == 400
    assert long.status_code == 413
    assert over.status_code == 429  # client 2회
    assert ip_over.status_code == 429  # IP 3회 (테스트 클라이언트는 같은 IP)


def test_forwarded_for_is_used_for_ip_limit(tmp_path):
    with make_client(tmp_path, consult_ip_daily_limit=1) as client:
        h = {"X-Client-Id": "a", "X-Forwarded-For": "1.1.1.1, 10.0.0.1"}
        client.post("/consults", json={}, headers=h)
        same_ip = client.post("/consults", json={}, headers={**h, "X-Client-Id": "b"})
        other_ip = client.post(
            "/consults",
            json={},
            headers={"X-Client-Id": "c", "X-Forwarded-For": "2.2.2.2"},
        )
    assert same_ip.status_code == 429
    assert other_ip.status_code == 201
    ips = {r["ip"] for r in db_rows(tmp_path, "SELECT ip FROM consults")}
    assert ips == {"1.1.1.1", "2.2.2.2"}


def test_budget_over_uses_local_and_openai_failure_falls_back(tmp_path):
    models = MockTextModels()
    with make_client(
        tmp_path, text_models=models, openai_daily_budget_usd=0.01
    ) as client:
        c = start(client)
        answer_all(client, c["id"])  # 기획서 $0.01 → 상한 도달
        res = client.post(
            "/copies/convert", json={"text": "신메뉴 출시", "format": "instagram_post"}
        ).json()
    assert res["source"] == "local"
    assert models.calls[-1] == ("convert", "basic")

    failing = MockTextModels(fail=True)
    with make_client(tmp_path / "b", text_models=failing) as client:
        res = client.post(
            "/copies/convert", json={"text": "신메뉴 출시", "format": "instagram_post"}
        ).json()
    assert res["source"] == "local"
    assert failing.calls == [("convert", "natural"), ("convert", "basic")]


def test_consult_id_is_kept_on_generation(tmp_path):
    with make_client(tmp_path) as client:
        body = client.post(
            "/generate", json={**BASE_BODY, "consult_id": "c_123"}
        ).json()
        g = client.get(f"/generations/{body['id']}").json()
    assert g["input"]["consult_id"] == "c_123"


# ---------------------------------------------------------------------- 문구 변환
@pytest.mark.parametrize(
    ("fmt", "kind"),
    [
        ("instagram_post", str),
        ("instagram_hashtags", list),
        ("instagram_location", list),
        ("instagram_story", str),
        ("naver_coupon", dict),
        ("naver_blog_title", list),
        ("store_description", str),
    ],
)
def test_convert_formats(tmp_path, fmt, kind):
    with make_client(tmp_path) as client:
        res = client.post(
            "/copies/convert",
            json={
                "text": "주말 한정 10% 할인",
                "format": fmt,
                "product_name": "소금빵",
                "area": "망원동",
                "facts": {"discount": "10%"},
            },
        )
    assert res.status_code == 200, res.text
    assert isinstance(res.json()["result"], kind)
    assert db_rows(tmp_path, "SELECT kind FROM text_calls")[0]["kind"] == "convert"


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"text": "", "format": "instagram_post"}, 400),
        ({"text": "문구", "format": "tiktok"}, 400),
        ({"text": "가" * 301, "format": "instagram_post"}, 413),
        ({"text": "문구", "format": "instagram_post", "facts": {"a": 1}}, 422),
    ],
)
def test_convert_errors(tmp_path, body, status):
    with make_client(tmp_path) as client:
        res = client.post("/copies/convert", json=body)
    assert res.status_code == status


def test_convert_daily_limit(tmp_path):
    with make_client(tmp_path, convert_daily_limit=2) as client:
        codes = [
            client.post(
                "/copies/convert",
                json={"text": "문구", "format": "instagram_story"},
                headers={"X-Client-Id": "a"},
            ).status_code
            for _ in range(3)
        ]
    assert codes == [200, 200, 429]


def _fake_ask(answers):
    """ask_json 자리에 끼우는 가짜. answers를 차례로 돌려줌."""
    calls = []

    def ask(instructions, user_input, schema, name, quality="natural"):
        calls.append({"instructions": instructions, "quality": quality, "name": name})
        return JsonResult(
            data=answers[len(calls) - 1],
            model="fake",
            source="openai",
            cost_usd=0.001,
            elapsed_sec=0.0,
        )

    return ask, calls


def test_core_convert_retries_then_drops_invented_numbers(monkeypatch):
    ask, calls = _fake_ask(
        [
            {"result": ["#소금빵", "#30퍼할인"], "fixed_typos": False},
            {"result": ["#소금빵", "#50%할인", "#망원동"], "fixed_typos": True},
        ]
    )
    monkeypatch.setattr(copy_convert, "ask_json", ask)
    out = copy_convert.convert_copy(
        "소금빵 10% 할인",
        "instagram_hashtags",
        area="망원동",
        facts={"discount": "10%"},
    )
    assert len(calls) == 2 and "30" in calls[1]["instructions"]
    assert out["result"] == ["#소금빵", "#망원동"]  # 지어낸 50% 항목은 뺌
    assert out["removed_numbers"] is True and out["cost_usd"] == 0.002


def test_core_convert_keeps_allowed_numbers(monkeypatch):
    ask, calls = _fake_ask(
        [
            {
                "result": {
                    "title": "10% 할인",
                    "condition": "10% 할인",
                    "period": "11월 30일까지",
                },
                "fixed_typos": False,
            }
        ]
    )
    monkeypatch.setattr(copy_convert, "ask_json", ask)
    out = copy_convert.convert_copy(
        "소금빵 할인", "naver_coupon", facts={"discount": "10%", "until": "11월 30일"}
    )
    assert len(calls) == 1 and out["removed_numbers"] is False
    assert out["result"]["period"] == "11월 30일까지"


def test_core_consultant_read_and_brief(monkeypatch):
    ask, calls = _fake_ask(
        [
            {
                "off_topic": False,
                "category": "카페",
                "goal": "신메뉴",
                "product_name": "소금빵",
                "audience": "",
                "strengths": "",
                "period": "",
                "channel": "",
            },
            {
                "off_topic": False,
                "category": "카페",
                "goal": "신메뉴",
                "product_name": "소금빵",
                "period": None,
                "strengths": ["맛"],
                "audience": "직장인",
                "channel": "카카오톡 채널",
                "message": "출근길 소금빵",
                "copies": ["갓 구운 소금빵", "30% 할인 소금빵", "셋째"],
                "style": "따뜻한",
                "reason": "단골에게 바로 닿아요.",
                "next_tips": [],
            },
        ]
    )
    monkeypatch.setattr(consultant, "ask_json", ask)
    off, filled, _ = consultant.read_answer(
        "category", "어떤 가게?", "망원동 카페인데 소금빵 신메뉴", {}
    )
    assert not off and filled == {
        "category": "카페",
        "goal": "신메뉴",
        "product_name": "소금빵",
    }
    assert consultant.next_question(filled)[0] == "audience"  # 찬 칸은 건너뜀

    _, brief, _ = consultant.write_brief({**filled, "audience": "직장인"}, "instagram")
    assert calls[1]["quality"] == "terra"
    assert brief["purpose"] == "kakao"  # 채널에서 정함
    assert brief["copies"] == [
        "갓 구운 소금빵",
        "% 할인 소금빵",
    ]  # 답에 없는 30은 뺌, 2개까지


def test_parse_json_variants():
    assert _parse('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(TextGenerationError):
        _parse("not json")


# ---------------------------------------------------------------------- 대기 카드
def test_tips_filter_and_cache(tmp_path):
    with make_client(tmp_path) as client:
        res = client.get("/tips", params={"purpose": "commerce", "limit": 12})
        bad = client.get("/tips", params={"limit": 20})
        unknown_cat = client.get("/tips", params={"category": "zzz"})
    tips = res.json()["tips"]
    assert res.headers["cache-control"] == "max-age=600"
    assert any(t["id"] == "platform-store-main" for t in tips)
    assert not any(t["id"].startswith("platform-ig") for t in tips)
    assert all(t["checked_at"] for t in tips if t["kind"] in ("platform", "law"))
    assert bad.status_code == 422 and unknown_cat.status_code == 200


def test_tips_season_first():
    from datetime import date

    from just_make_it.service.tips import pick_tips

    tips = pick_tips("instagram", today=date(2026, 11, 3))
    assert tips[0]["id"] == "season-1111"
    assert all(t["id"] != "season-0214" for t in tips)


def test_new_event_types(tmp_path):
    with make_client(tmp_path) as client:
        gid = client.post("/generate", json=BASE_BODY).json()["id"]
        ok = [
            client.post("/events", json={"generation_id": gid, "type": t}).status_code
            for t in ("add_qr", "tip_click", "copy_kit")
        ]
        flag = client.post("/events", json={"generation_id": gid, "type": "flag"})
    assert ok == [204, 204, 204]
    assert flag.status_code == 400  # flag는 서버만


# ---------------------------------------------------------------------- 진행 막대 확장
class PhasedMock(MockGenerator):
    """core처럼 진행 상황을 남기는 Mock: 문구 → 그림 1/4 … (단계마다 잠깐 쉼)."""

    def generate(self, spec):
        deadline.report("text")
        time.sleep(0.15)
        callback = deadline.step_callback("mock", steps=4)
        callback(None, 0, None, {})
        time.sleep(0.3)
        return super().generate(spec)


def test_progress_reports_phase_step_and_elapsed(tmp_path):
    with make_client(tmp_path, primary=PhasedMock(0.0)) as client:
        gid = client.post("/generations", json=BASE_BODY).json()["id"]
        time.sleep(0.05)
        text = client.get(f"/generations/{gid}").json()["progress"]
        time.sleep(0.25)
        image = client.get(f"/generations/{gid}").json()["progress"]
        deadline_end = time.monotonic() + 5
        while client.get(f"/generations/{gid}").json()["status"] == "processing":
            assert time.monotonic() < deadline_end
            time.sleep(0.05)
    assert text["phase"] == "text" and text["step"] is None
    assert image["phase"] == "image" and (image["step"], image["steps"]) == (1, 4)
    assert image["elapsed_seconds"] > text["elapsed_seconds"] > 0


def test_progress_overdue_when_past_estimate(tmp_path):
    with make_client(
        tmp_path, primary=MockGenerator(0.6), seconds_per_job_init=0.2
    ) as client:
        gid = client.post("/generations", json=BASE_BODY).json()["id"]
        time.sleep(0.4)
        p = client.get(f"/generations/{gid}").json()["progress"]
        while client.get(f"/generations/{gid}").json()["status"] == "processing":
            time.sleep(0.05)
    assert p["stage"] == "running" and p["overdue"] is True
    assert p["estimated_seconds"] == 0


def test_detail_sections_get_progress(tmp_path):
    with make_client(tmp_path, primary=MockGenerator(0.3)) as client:
        pid = client.post("/detail-pages", json=DETAIL_BODY).json()["id"]
        seen = None
        end = time.monotonic() + 5
        while time.monotonic() < end and seen is None:
            page = client.get(f"/detail-pages/{pid}").json()
            seen = next(
                (
                    s["progress"]
                    for s in page["sections"]
                    if s["status"] == "processing" and s.get("progress")
                ),
                None,
            )
            time.sleep(0.05)
        wait_done(client, pid)
    assert seen is not None and seen["stage"] in ("queued", "running")


def test_speeds_skip_warmup_and_key_by_size():
    from just_make_it.serving.queue_manager import _Speeds

    speeds = _Speeds(20.0)
    key = ("primary", "1024x1024", False)
    speeds.add(key, 100.0)  # 첫 호출(워밍업)은 버림
    assert speeds.get(key) == 20.0
    speeds.add(key, 10.0)
    assert speeds.get(key) == 10.0
    assert speeds.get(("primary", "1536x864", False)) == 10.0  # 같은 경로 평균
    assert speeds.get(("extra", "1024x1024", False)) == 20.0  # 기록 없음 → 초기값
