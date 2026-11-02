"""고도화 서빙 API 테스트: S2 같은 원본 목록, S4 사용 기록·지표, V3 비동기 생성.

S2·S4는 PM·서비스 추가 명세(api_spec_next)를 따른다.

Mock 생성기로 API 비용·GPU 없이 실행된다.
실행: uv run pytest tests/test_roadmap_api.py
"""

import json
import time

import pytest
from test_detail_pages import DETAIL_BODY, wait_done
from test_serving import (  # noqa: F401 (isolate_env는 fixture)
    BASE_BODY,
    db_rows,
    fetch_image,
    isolate_env,
    make_client,
)
from test_text_edit import edited_png

from just_make_it.serving.generators import MockGenerator


def generate(client, **extra) -> dict:
    res = client.post("/generate", json={**BASE_BODY, **extra})
    assert res.status_code == 200, res.text
    return res.json()


def poll(client, gid, timeout=10.0) -> dict:
    """비동기 생성 결과를 끝날 때까지 조회 (프론트의 2초 폴링 흉내)."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        body = client.get(f"/generations/{gid}").json()
        if body["status"] != "processing":
            return body
        time.sleep(0.05)
    raise AssertionError(f"{gid}가 {timeout}초 안에 안 끝남")


# ---------------------------------------------------------------------- S2 같은 원본 목록
def test_family_follows_parent_chain_from_any_member(tmp_path):
    with make_client(tmp_path) as client:
        a = generate(client)["id"]
        b = generate(client, parent_id=a)["id"]
        c = generate(client, parent_id=b, adjustments=["더 밝게"])["id"]
        d = generate(client, parent_id=a)["id"]
        other = generate(client)["id"]
        from_leaf = client.get(f"/generations/{c}/family").json()
        from_root = client.get(f"/generations/{a}/family").json()
        alone = client.get(f"/generations/{other}/family").json()

    assert [i["id"] for i in from_leaf["items"]] == [a, b, c, d]  # 만든 순서
    assert from_root == from_leaf
    by_id = {i["id"]: i for i in from_leaf["items"]}
    assert by_id[a]["parent_id"] is None and by_id[c]["parent_id"] == b
    assert set(by_id[c]) == {"id", "parent_id", "image_url", "created_at"}
    assert all(i["image_url"] for i in by_id.values())
    assert [i["id"] for i in alone["items"]] == [other]  # 혼자여도 자기 1개


def test_family_only_success_and_max_50(tmp_path):
    fail_second = MockGenerator(0.0)
    with make_client(tmp_path, primary=fail_second, retry_count=0) as client:
        a = generate(client)["id"]
        fail_second.fail_times = fail_second.calls + 1  # 다음 1건 실패
        failed = client.post("/generate", json={**BASE_BODY, "parent_id": a})
        failed_id = db_rows(tmp_path)[1]["id"]
        for _ in range(51):
            generate(client, parent_id=a)
        items = client.get(f"/generations/{a}/family").json()["items"]
    assert failed.status_code == 503
    assert len(items) == 50
    assert failed_id not in {i["id"] for i in items}


def test_family_unknown_or_detail_section_returns_404(tmp_path):
    with make_client(tmp_path) as client:
        missing = client.get("/generations/nope/family")
        pid = client.post("/detail-pages", json=DETAIL_BODY).json()["id"]
        wait_done(client, pid)
        section_id = db_rows(tmp_path)[0]["id"]
        section = client.get(f"/generations/{section_id}/family")
    assert missing.status_code == 404
    assert section.status_code == 404


# ---------------------------------------------------------------------- S4 사용 기록
def send_event(client, gid, kind, detail=None, client_id="user-1"):
    body = {"generation_id": gid, "type": kind}
    if detail is not None:
        body["detail"] = detail
    return client.post("/events", json=body, headers={"X-Client-Id": client_id})


def test_events_are_recorded_and_mark_download(tmp_path):
    with make_client(tmp_path) as client:
        gid = generate(client)["id"]
        results = [
            send_event(client, gid, "download", {"edited": False}),
            send_event(client, gid, "download", {"edited": True}),
            send_event(client, gid, "pick_copy", {"index": 1, "copy": "신메뉴!"}),
            send_event(client, gid, "remake", {"adjustments": ["더 밝게"]}),
        ]
    assert [r.status_code for r in results] == [204] * 4
    events = db_rows(tmp_path, "SELECT * FROM events ORDER BY id")
    assert [e["type"] for e in events] == [
        "download",
        "download",
        "pick_copy",
        "remake",
    ]
    assert {e["client_id"] for e in events} == {"user-1"}
    assert json.loads(events[2]["detail_json"]) == {"index": 1, "copy": "신메뉴!"}
    assert db_rows(tmp_path)[0]["downloaded_at"] is not None


@pytest.mark.parametrize(
    "body",
    [
        {"type": "download"},  # generation_id 없음
        {"generation_id": "nope", "type": "download"},  # 없는 결과
        {"generation_id": "GID", "type": "like"},  # 모르는 type
        {"generation_id": "GID", "type": "download", "detail": "문자열"},
        {"generation_id": "GID", "type": "download", "detail": {"x": "가" * 2000}},
    ],
)
def test_bad_events_return_400(tmp_path, body):
    with make_client(tmp_path) as client:
        gid = generate(client)["id"]
        if body.get("generation_id") == "GID":
            body = {**body, "generation_id": gid}
        res = client.post("/events", json=body)
    assert res.status_code == 400
    assert db_rows(tmp_path, "SELECT * FROM events") == []


def test_stats_counts_usage_per_day(tmp_path):
    with make_client(tmp_path) as client:
        a = generate(client)["id"]
        b = generate(client)["id"]
        c = generate(client, parent_id=a)["id"]  # a를 다시 만들기
        for gid, kind in [(a, "download"), (a, "copy_link"), (b, "cutout")]:
            send_event(client, gid, kind)
        save = client.post(
            f"/generations/{c}/image",
            files={"image": ("e.png", edited_png(), "image/png")},
        )
        pid = client.post("/detail-pages", json=DETAIL_BODY).json()["id"]
        wait_done(client, pid)  # 상세페이지 칸은 지표에서 빠짐
        stats = client.get("/stats").json()

    assert save.status_code == 200
    total = stats["total"]
    assert total["generated"] == 3
    assert total["downloaded"] == 1  # 다운로드 + 링크 복사여도 결과 1개
    assert total["edited"] == 2  # b 배경 지우기, c 고친 그림 저장
    assert total["remade"] == 1
    assert total["download_rate"] == pytest.approx(1 / 3, abs=1e-3)
    assert len(stats["days"]) == 1 and stats["days"][0]["generated"] == 3


def test_stats_days_range(tmp_path):
    with make_client(tmp_path) as client:
        empty = client.get("/stats", params={"days": 1}).json()
        bad = client.get("/stats", params={"days": 0})
    assert empty["days"] == [] and empty["total"]["generated"] == 0
    assert empty["total"]["download_rate"] == 0.0
    assert bad.status_code == 422


# ---------------------------------------------------------------------- V3 비동기 생성
def test_async_generation_returns_202_then_result(tmp_path):
    with make_client(tmp_path, primary=MockGenerator(0.2)) as client:
        res = client.post("/generations", json={**BASE_BODY, "purpose": "youtube"})
        started = res.json()
        done = poll(client, started["id"])
        image = fetch_image(client, done["image_url"])
    assert res.status_code == 202
    assert started["status"] == "processing"
    assert started["message"] == BASE_BODY["message"]  # 문구를 먼저 보여줄 수 있음
    assert (started["width"], started["height"]) == (1536, 864)
    assert started["estimated_seconds"] > 0
    assert done["status"] == "success" and done["progress"] is None
    assert done["background_url"] and done["text_layout"]
    assert image.size == (1536, 864)


def test_async_progress_shows_queue_order(tmp_path):
    primary = MockGenerator(0.4)
    with make_client(tmp_path, primary=primary, max_wait_seconds=1000) as client:
        ids = [
            client.post("/generations", json=BASE_BODY).json()["id"] for _ in range(3)
        ]
        time.sleep(0.1)  # 첫 작업이 워커에 잡힐 때까지
        progress = [client.get(f"/generations/{gid}").json()["progress"] for gid in ids]
        results = [poll(client, gid) for gid in ids]
    assert progress[0]["stage"] == "running" and progress[0]["jobs_ahead"] == 0
    assert progress[1] == {**progress[1], "stage": "queued", "jobs_ahead": 1}
    assert progress[2]["stage"] == "queued" and progress[2]["jobs_ahead"] == 2
    assert progress[2]["estimated_seconds"] > progress[1]["estimated_seconds"]
    assert all(r["status"] == "success" for r in results)


def test_async_generation_is_not_cancelled_by_wait_limit(tmp_path):
    # 동기 /generate는 generate_wait_seconds가 지나면 작업을 취소하지만 비동기는 끝까지 만든다
    with make_client(
        tmp_path, primary=MockGenerator(0.4), generate_wait_seconds=0.05
    ) as client:
        gid = client.post("/generations", json=BASE_BODY).json()["id"]
        done = poll(client, gid)
    assert done["status"] == "success"


def test_async_generation_validates_like_generate(tmp_path):
    with make_client(tmp_path, daily_job_limit=1) as client:
        missing = client.post("/generations", json={**BASE_BODY, "message": " "})
        bad = client.post("/generations", json={**BASE_BODY, "purpose": "tiktok"})
        first = client.post("/generations", json=BASE_BODY)
        over = client.post("/generations", json=BASE_BODY)
        poll(client, first.json()["id"])
    assert missing.status_code == 400
    assert bad.status_code == 422
    assert first.status_code == 202
    assert over.status_code == 429


def test_async_generation_failure_is_visible_by_polling(tmp_path):
    with make_client(tmp_path, primary=MockGenerator(0.0, fail_times=5)) as client:
        gid = client.post("/generations", json=BASE_BODY).json()["id"]
        done = poll(client, gid)
    assert done["status"] == "error" and done["progress"] is None


def test_docs_list_new_endpoints(tmp_path):
    with make_client(tmp_path) as client:
        paths = client.get("/openapi.json").json()["paths"]
    assert "post" in paths["/generations"]
    assert "get" in paths["/generations/{generation_id}/family"]
    events = paths["/events"]["post"]
    schema = events["requestBody"]["content"]["application/json"]["schema"]
    assert {"generation_id", "type", "detail"} <= set(schema["properties"])
    assert "get" in paths["/stats"]
