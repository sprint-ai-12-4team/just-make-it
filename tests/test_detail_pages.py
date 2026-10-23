"""상세페이지 비동기 생성 API 테스트 (api_spec 3장 /detail-pages).

Mock 생성기와 core 가짜 모델을 써서 API 비용·GPU 없이 실행된다.
실행: uv run pytest tests/test_detail_pages.py
"""

import json
import time

import pytest
from test_serving import (  # noqa: F401 (isolate_env·fake_core는 fixture)
    FakeText,
    RecordingMock,
    core_client,
    db_rows,
    fake_core,
    fetch_image,
    isolate_env,
    make_client,
    png_bytes,
)

from just_make_it.core.base import TextResult
from just_make_it.serving.detail_pages import (
    DETAIL_RULES,
    CoreDetailWriter,
    DetailWriter,
    MockDetailWriter,
    parse_sections,
)
from just_make_it.serving.generators import GeneratorError, MockGenerator

DETAIL_BODY = {
    "product_name": "수제 딸기잼",
    "message": "국산 딸기 100% 신상품",
    "features": ["무첨가", "소량 생산", "선물 포장"],
    "style": "따뜻한",
}

MODEL_OUTPUT = """\
1 | 국산 딸기 100%, 그대로 담았어요 | 설탕 말고 딸기 맛만 남겼습니다 | 유리병에 담긴 딸기잼
2 | 첨가물 없이 | 보존료·색소 없이 만들어요 | 나무 숟가락으로 떠낸 잼
3 | 조금씩 만들어요 | 매일 필요한 만큼만 끓여요 | 냄비에서 끓는 딸기
4 | 선물하기 좋아요 | 리본 하나로 마음까지 | 리본으로 묶은 잼 병
5 | 아침 식탁에 딸기 한 스푼 | 오늘 주문하면 내일 만나요 | 토스트와 커피가 놓인 식탁"""


class FailingWriter(DetailWriter):
    def write(self, product_name, message, features, style, text_quality="basic"):
        raise GeneratorError("Ollama 연결 실패")


class SlowWriter(MockDetailWriter):
    def __init__(self, delay):
        self.delay = delay

    def write(self, *args, **kwargs):
        time.sleep(self.delay)
        return super().write(*args, **kwargs)


class DetailFakeText(FakeText):
    """상세페이지 규칙이 오면 5칸 문구를, 아니면 영어 묘사를 돌려주는 가짜 Gemma."""

    def __init__(self, name, outputs=None):
        super().__init__(name)
        self.outputs = list(outputs or [MODEL_OUTPUT])

    def generate(self, instructions, user_input, max_tokens=300):
        if instructions != DETAIL_RULES:
            return super().generate(instructions, user_input, max_tokens)
        self.calls += 1
        text = self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]
        return TextResult(text=text, model=self.name, elapsed_sec=0.0, cost_usd=0.0)


def wait_done(client, pid, timeout=10.0) -> dict:
    """프론트처럼 폴링: 페이지와 모든 칸이 끝날 때까지."""
    deadline = time.monotonic() + timeout
    while True:
        res = client.get(f"/detail-pages/{pid}")
        assert res.status_code == 200, res.text
        page = res.json()
        busy = page["status"] == "processing" or any(
            s["status"] in ("pending", "processing") for s in page["sections"]
        )
        if not busy:
            return page
        assert time.monotonic() < deadline, page
        time.sleep(0.02)


def section_rows(tmp_path) -> list[dict]:
    return db_rows(
        tmp_path,
        "SELECT * FROM generations WHERE detail_page_id IS NOT NULL ORDER BY rowid",
    )


# ---------------------------------------------------------------------- 접수·조회
def test_detail_page_runs_to_success(tmp_path):
    with make_client(tmp_path) as client:
        res = client.post(
            "/detail-pages", json=DETAIL_BODY, headers={"X-Client-Id": "u1"}
        )
        assert res.status_code == 202, res.text
        started = res.json()
        page = wait_done(client, started["id"])
        image = fetch_image(client, page["sections"][0]["image_url"])
    assert started["status"] == "processing" and len(started["id"]) == 36
    # 스펙 3장 응답 모양
    assert set(page) >= {"id", "status", "progress", "sections", "created_at"}
    assert page["status"] == "success"
    assert page["progress"] == {"done": 5, "total": 5}
    assert [s["role"] for s in page["sections"]] == [
        "hero",
        "feature",
        "feature",
        "feature",
        "closing",
    ]
    for section in page["sections"]:
        assert section["status"] == "success"
        assert section["title"] and section["body"] and section["image_url"]
        assert section["source"] == "mock"
    # 직접 적은 특징이 2~4칸 제목
    assert [s["title"] for s in page["sections"][1:4]] == DETAIL_BODY["features"]
    assert image.size == (1024, 1024)  # 커머스 크기
    rows = section_rows(tmp_path)
    assert [r["section_index"] for r in rows] == [0, 1, 2, 3, 4]
    assert {r["client_id"] for r in rows} == {"u1"}
    assert {r["purpose"] for r in rows} == {"commerce"}


def test_each_section_image_uses_its_own_scene(tmp_path):
    primary = RecordingMock(0.0)
    with make_client(tmp_path, primary=primary) as client:
        pid = client.post("/detail-pages", json=DETAIL_BODY).json()["id"]
        wait_done(client, pid)
    texts = MockDetailWriter().write(
        DETAIL_BODY["product_name"],
        DETAIL_BODY["message"],
        DETAIL_BODY["features"],
        None,
    )
    scenes = [section["image_prompt"] for section in texts]
    assert sorted(spec.message for spec in primary.specs) == sorted(scenes)
    assert {spec.purpose for spec in primary.specs} == {"commerce"}
    assert {spec.style for spec in primary.specs} == {"따뜻한"}


def test_get_unknown_detail_page_returns_404(tmp_path):
    with make_client(tmp_path) as client:
        res = client.get("/detail-pages/nope")
    assert res.status_code == 404
    assert res.json()["detail"] == "결과를 찾을 수 없어요."


@pytest.mark.parametrize(
    "body",
    [
        {**DETAIL_BODY, "product_name": ""},
        {**DETAIL_BODY, "message": "   "},
        {"product_name": "잼"},
    ],
)
def test_detail_missing_required_returns_400(tmp_path, body):
    with make_client(tmp_path) as client:
        res = client.post("/detail-pages", json=body)
    assert res.status_code == 400


@pytest.mark.parametrize(
    "body",
    [
        {**DETAIL_BODY, "features": ["a", "b", "c", "d"]},  # 최대 3개
        {**DETAIL_BODY, "features": ["가" * 51]},
        {**DETAIL_BODY, "image_model": "dall-e"},
    ],
)
def test_detail_invalid_values_return_422(tmp_path, body):
    with make_client(tmp_path) as client:
        res = client.post("/detail-pages", json=body)
    assert res.status_code == 422


def test_one_running_page_per_client(tmp_path):
    with make_client(tmp_path, detail_writer=SlowWriter(0.3)) as client:
        first = client.post(
            "/detail-pages", json=DETAIL_BODY, headers={"X-Client-Id": "u1"}
        )
        again = client.post(
            "/detail-pages", json=DETAIL_BODY, headers={"X-Client-Id": "u1"}
        )
        other = client.post(
            "/detail-pages", json=DETAIL_BODY, headers={"X-Client-Id": "u2"}
        )
        wait_done(client, first.json()["id"])
        wait_done(client, other.json()["id"])
        after = client.post(
            "/detail-pages", json=DETAIL_BODY, headers={"X-Client-Id": "u1"}
        )
        wait_done(client, after.json()["id"])
    assert first.status_code == 202
    assert again.status_code == 409
    assert (
        again.json()["detail"]
        == "만들고 있는 상세페이지가 있어요. 끝나면 다시 시도해 주세요."
    )
    assert other.status_code == 202  # 다른 사용자는 따로
    assert after.status_code == 202  # 끝나면 다시 만들 수 있음


def test_daily_limit_must_fit_all_sections(tmp_path):
    with make_client(tmp_path, daily_job_limit=4) as client:
        res = client.post("/detail-pages", json=DETAIL_BODY)
    assert res.status_code == 429
    assert section_rows(tmp_path) == []


def test_text_failure_fails_whole_page(tmp_path):
    with make_client(tmp_path, detail_writer=FailingWriter()) as client:
        pid = client.post("/detail-pages", json=DETAIL_BODY).json()["id"]
        page = wait_done(client, pid)
        redo = client.post(f"/detail-pages/{pid}/sections/0", json={})
        # 실패했으니 같은 사용자가 바로 새로 만들 수 있다
        again = client.post("/detail-pages", json=DETAIL_BODY)
    assert page["status"] == "error"
    assert {s["status"] for s in page["sections"]} == {"error"}
    assert redo.status_code == 409
    assert again.status_code == 202


def test_failed_section_does_not_block_page(tmp_path):
    # 3번째 호출만 실패 (재시도 1회까지 실패하도록 Fallback 없음)
    class FailThird(MockGenerator):
        def generate(self, spec):
            if spec.message.startswith("소량 생산"):
                raise GeneratorError("GPU 메모리 부족")
            return super().generate(spec)

    with make_client(tmp_path, primary=FailThird(0.0)) as client:
        pid = client.post("/detail-pages", json=DETAIL_BODY).json()["id"]
        page = wait_done(client, pid)
    assert page["status"] == "success"  # 일부 칸이 error여도 페이지는 끝남 (스펙)
    statuses = [s["status"] for s in page["sections"]]
    assert statuses == ["success", "success", "error", "success", "success"]
    assert page["progress"]["done"] == 5


def test_multipart_with_features_and_reference(tmp_path):
    primary = RecordingMock(0.0)
    with make_client(tmp_path, primary=primary) as client:
        res = client.post(
            "/detail-pages",
            data={**DETAIL_BODY, "features": ["무첨가", "선물 포장"]},
            files={"reference_image": ("p.png", png_bytes(), "image/png")},
        )
        page = wait_done(client, res.json()["id"])
    assert res.status_code == 202, res.text
    assert [s["title"] for s in page["sections"][1:3]] == ["무첨가", "선물 포장"]
    assert all(spec.reference_image is not None for spec in primary.specs)
    assert len(primary.specs) == 5


def test_detailed_image_model_uses_premium_for_sections(tmp_path):
    premium = MockGenerator(0.0, name="mock-premium")
    with make_client(tmp_path, premium=premium) as client:
        pid = client.post(
            "/detail-pages",
            json={**DETAIL_BODY, "image_model": "openai-image-2.5-flare"},
        ).json()["id"]
        wait_done(client, pid)
    assert {r["route"] for r in section_rows(tmp_path)} == {"premium"}
    assert premium.calls == 5


def test_sections_wait_in_queue_instead_of_falling_back(tmp_path):
    # 5칸이 한꺼번에 들어와 예상 대기가 길어도 OpenAI로 넘기지 않는다 (폴링이라 기다려도 됨)
    fallback = MockGenerator(0.0, name="mock-fallback")
    with make_client(
        tmp_path,
        primary=MockGenerator(0.05),
        fallback=fallback,
        max_wait_seconds=1,
        seconds_per_job_init=20,
    ) as client:
        pid = client.post("/detail-pages", json=DETAIL_BODY).json()["id"]
        wait_done(client, pid)
    assert {r["route"] for r in section_rows(tmp_path)} == {"primary"}
    assert fallback.calls == 0


# ---------------------------------------------------------------------- 섹션 다시 만들기
def test_regenerate_section_keeps_text_and_makes_new_image(tmp_path):
    primary = RecordingMock(0.0)
    with make_client(tmp_path, primary=primary) as client:
        pid = client.post("/detail-pages", json=DETAIL_BODY).json()["id"]
        before = wait_done(client, pid)
        res = client.post(
            f"/detail-pages/{pid}/sections/2",
            json={"adjustments": ["더 밝게", "텍스트 짧게"]},
        )
        after = wait_done(client, pid)
    assert res.status_code == 202, res.text
    assert res.json() == {"id": pid, "index": 2, "status": "processing"}
    old, new = before["sections"][2], after["sections"][2]
    assert (new["title"], new["body"]) == (old["title"], old["body"])
    assert new["image_url"] != old["image_url"]
    assert [s["image_url"] for i, s in enumerate(after["sections"]) if i != 2] == [
        s["image_url"] for i, s in enumerate(before["sections"]) if i != 2
    ]
    # 문구를 바꾸는 칩은 이미지 쪽에 넘기지 않는다
    assert primary.specs[-1].adjustments == ["더 밝게"]
    rows = section_rows(tmp_path)
    assert len(rows) == 6
    assert rows[-1]["parent_id"] == next(
        r["id"] for r in rows[:5] if r["section_index"] == 2
    )


def test_regenerate_without_body(tmp_path):
    with make_client(tmp_path) as client:
        pid = client.post("/detail-pages", json=DETAIL_BODY).json()["id"]
        wait_done(client, pid)
        res = client.post(f"/detail-pages/{pid}/sections/4")
        wait_done(client, pid)
    assert res.status_code == 202


def test_regenerate_while_page_processing_returns_409(tmp_path):
    with make_client(tmp_path, detail_writer=SlowWriter(0.3)) as client:
        pid = client.post("/detail-pages", json=DETAIL_BODY).json()["id"]
        res = client.post(f"/detail-pages/{pid}/sections/0", json={})
        wait_done(client, pid)
    assert res.status_code == 409


def test_regenerate_same_section_twice_returns_409(tmp_path):
    with make_client(tmp_path, primary=MockGenerator(0.0)) as client:
        pid = client.post("/detail-pages", json=DETAIL_BODY).json()["id"]
        wait_done(client, pid)
        client.app.state.manager.primary.delay_seconds = 0.3
        first = client.post(f"/detail-pages/{pid}/sections/1", json={})
        second = client.post(f"/detail-pages/{pid}/sections/1", json={})
        other = client.post(f"/detail-pages/{pid}/sections/3", json={})
        wait_done(client, pid)
    assert first.status_code == 202
    assert second.status_code == 409
    assert other.status_code == 202  # 다른 칸은 같이 다시 만들 수 있음


@pytest.mark.parametrize("path", ["/detail-pages/nope/sections/0"])
def test_regenerate_unknown_page_returns_404(tmp_path, path):
    with make_client(tmp_path) as client:
        res = client.post(path, json={})
    assert res.status_code == 404


def test_regenerate_bad_index_returns_422(tmp_path):
    with make_client(tmp_path) as client:
        pid = client.post("/detail-pages", json=DETAIL_BODY).json()["id"]
        wait_done(client, pid)
        res = client.post(f"/detail-pages/{pid}/sections/5", json={})
    assert res.status_code == 422


# ---------------------------------------------------------------------- 문구 5칸
def test_parse_sections_accepts_model_format():
    sections = parse_sections(MODEL_OUTPUT, [])
    assert [s["role"] for s in sections] == [
        "hero",
        "feature",
        "feature",
        "feature",
        "closing",
    ]
    assert sections[0] == {
        "role": "hero",
        "title": "국산 딸기 100%, 그대로 담았어요",
        "body": "설탕 말고 딸기 맛만 남겼습니다",
        "image_prompt": "유리병에 담긴 딸기잼",
    }


def test_parse_sections_tolerates_decorations_and_fixes_feature_titles():
    text = "다음은 상세페이지입니다.\n" + "\n".join(
        f"{line[0]}. |{line[3:]}" for line in MODEL_OUTPUT.splitlines()
    )
    sections = parse_sections("```\n" + text + "\n```", ["무첨가"])
    assert sections[1]["title"] == "무첨가"  # 직접 적은 특징은 그대로
    assert sections[2]["title"] == "조금씩 만들어요"  # 모자란 특징은 모델 문구


def test_parse_sections_rejects_missing_rows():
    with pytest.raises(ValueError):
        parse_sections("\n".join(MODEL_OUTPUT.splitlines()[:4]), [])


@pytest.mark.usefixtures("fake_core")
def test_core_detail_writer_retries_bad_format(monkeypatch):
    from just_make_it.core import ai_models

    gemma = DetailFakeText("gemma4:12b-it-qat", outputs=["모르겠어요", MODEL_OUTPUT])
    monkeypatch.setattr(ai_models, "get_gemma", lambda: gemma)
    sections = CoreDetailWriter().write("수제 딸기잼", "국산 딸기", [], None)
    assert gemma.calls == 2
    assert len(sections) == 5


@pytest.mark.usefixtures("fake_core")
def test_core_detail_writer_gives_up_after_retries(monkeypatch):
    from just_make_it.core import ai_models

    gemma = DetailFakeText("gemma4:12b-it-qat", outputs=["모르겠어요"])
    monkeypatch.setattr(ai_models, "get_gemma", lambda: gemma)
    with pytest.raises(GeneratorError):
        CoreDetailWriter().write("수제 딸기잼", "국산 딸기", [], None)


def test_core_detail_page_end_to_end(
    tmp_path, fake_core, monkeypatch  # noqa: F811 (fixture)
):
    from just_make_it.core import ai_models, pipeline

    gemma = DetailFakeText("gemma4:12b-it-qat")
    monkeypatch.setattr(ai_models, "get_gemma", lambda: gemma)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("상세페이지 칸은 아직 프론트가 글자를 얹는다")

    monkeypatch.setattr(pipeline, "overlay_text", fail_if_called)
    with core_client(tmp_path, detail_writer=CoreDetailWriter()) as client:
        pid = client.post("/detail-pages", json=DETAIL_BODY).json()["id"]
        page = wait_done(client, pid)
        client.post(
            f"/detail-pages/{pid}/sections/0", json={"adjustments": ["더 밝게"]}
        )
        wait_done(client, pid)
    assert page["status"] == "success", page
    assert {s["source"] for s in page["sections"]} == {"local"}
    assert page["sections"][0]["title"] == "국산 딸기 100%, 그대로 담았어요"
    assert [s["title"] for s in page["sections"][1:4]] == DETAIL_BODY["features"]
    assert len(fake_core["klein"].calls) == 6 and fake_core["flare"].calls == []
    # 조금 수정하기: 직전 칸 이미지의 시드(가짜 klein은 7)로 구도 유지
    assert fake_core["klein"].calls[-1]["seed"] == 7
    page_row = db_rows(tmp_path, "SELECT * FROM detail_pages")[0]
    stored = json.loads(page_row["sections_json"])
    assert stored[0]["image_prompt"] == "유리병에 담긴 딸기잼"
    assert page_row["text_ms"] is not None
