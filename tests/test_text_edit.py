"""글자는 서버가 얹기 + 글자 고치기 API 테스트 (api_spec 3장 POST /generations/{id}/text).

Mock 생성기도 core `render_text`로 글자를 얹으므로 실제와 같은 흐름을 키·GPU 없이 검사한다.
실행: uv run pytest tests/test_text_edit.py
"""

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

from just_make_it.serving.generators import MockGenerator


def generate(client, body=BASE_BODY) -> dict:
    res = client.post("/generate", json=body)
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------------- 생성 응답
def test_generate_returns_final_image_background_and_layout(tmp_path):
    with make_client(tmp_path) as client:
        body = generate(client)
        final = fetch_image(client, body["image_url"])
        background = fetch_image(client, body["background_url"])
        again = client.get(f"/generations/{body['id']}").json()
    assert body["image_url"] != body["background_url"]
    assert set(body["text_layout"]) == {"position", "font", "size_scale"}
    assert final.size == background.size == (1024, 1024)
    assert final.tobytes() != background.tobytes()  # 최종 이미지에만 글자
    assert again["background_url"] == body["background_url"]
    assert again["text_layout"] == body["text_layout"]


def test_bigger_text_chip_sets_size_scale(tmp_path):
    with make_client(tmp_path) as client:
        body = generate(client, {**BASE_BODY, "adjustments": ["글자 더 크게"]})
    assert body["text_layout"]["size_scale"] == 1.25


def test_detail_sections_stay_text_free(tmp_path):
    # 상세페이지 칸은 아직 프론트가 글자를 얹는다 → 원본·text_layout 없음
    with make_client(tmp_path) as client:
        pid = client.post("/detail-pages", json=DETAIL_BODY).json()["id"]
        wait_done(client, pid)
        row = db_rows(tmp_path)[0]
        section = client.get(f"/generations/{row['id']}").json()
    assert section["background_url"] is None and section["text_layout"] is None


# ---------------------------------------------------------------------- 글자 고치기
def test_edit_text_rerenders_without_new_generation(tmp_path):
    primary = MockGenerator(0.0)
    with make_client(tmp_path, primary=primary) as client:
        body = generate(client)
        res = client.post(
            f"/generations/{body['id']}/text",
            json={
                "message": "이번 주말만 20% 할인",
                "position": "bottom",
                "font": "blackhan",
            },
        )
        edited = res.json()
        image = fetch_image(client, edited["image_url"])
        latest = client.get(f"/generations/{body['id']}").json()
    assert res.status_code == 200, res.text
    assert primary.calls == 1  # 이미지는 다시 만들지 않음
    assert edited["id"] == body["id"]
    assert edited["message"] == "이번 주말만 20% 할인"
    assert edited["text_layout"]["position"] == "bottom"
    assert edited["text_layout"]["font"] == "blackhan"
    assert edited["image_url"] != body["image_url"]  # 새 주소 (캐시 회피)
    assert edited["background_url"] == body["background_url"]
    assert image.size == (1024, 1024)
    # 링크 공유도 최신 상태
    assert latest["image_url"] == edited["image_url"]
    assert latest["message"] == edited["message"]


def test_edit_keeps_fields_not_sent(tmp_path):
    with make_client(tmp_path) as client:
        body = generate(client)
        first = client.post(
            f"/generations/{body['id']}/text",
            json={"position": "middle", "font": "jua"},
        ).json()
        second = client.post(
            f"/generations/{body['id']}/text", json={"size_scale": 1.4}
        ).json()
    assert second["message"] == body["message"]
    assert second["text_layout"] == {
        "position": "middle",
        "font": "jua",
        "size_scale": 1.4,
    }
    assert first["image_url"] != second["image_url"]


def test_edit_does_not_count_toward_daily_limit(tmp_path):
    with make_client(tmp_path, daily_job_limit=1) as client:
        body = generate(client)
        edits = [
            client.post(f"/generations/{body['id']}/text", json={"size_scale": s})
            for s in (0.8, 1.2)
        ]
        health = client.get("/health").json()
    assert [r.status_code for r in edits] == [200, 200]
    assert health["jobs_today"] == 1


def test_edit_empty_message_returns_400(tmp_path):
    with make_client(tmp_path) as client:
        body = generate(client)
        res = client.post(f"/generations/{body['id']}/text", json={"message": "  "})
    assert res.status_code == 400


@pytest.mark.parametrize(
    "change",
    [
        {"position": "left"},
        {"font": "comic-sans"},
        {"size_scale": 0.5},
        {"size_scale": 1.7},
        {"message": "가" * 201},
    ],
)
def test_edit_invalid_values_return_422(tmp_path, change):
    with make_client(tmp_path) as client:
        body = generate(client)
        res = client.post(f"/generations/{body['id']}/text", json=change)
    assert res.status_code == 422


def test_edit_unknown_generation_returns_404(tmp_path):
    with make_client(tmp_path) as client:
        res = client.post("/generations/nope/text", json={"position": "top"})
    assert res.status_code == 404


def test_edit_processing_generation_returns_409(tmp_path):
    with make_client(
        tmp_path, primary=MockGenerator(0.5), generate_wait_seconds=0.05
    ) as client:
        assert client.post("/generate", json=BASE_BODY).status_code == 503
        gid = db_rows(tmp_path)[0]["id"]
        res = client.post(f"/generations/{gid}/text", json={"position": "top"})
        time.sleep(0.6)  # 뒤에서 돌던 작업이 끝날 때까지
    assert res.status_code == 409


def test_edit_result_without_background_returns_409(tmp_path):
    # 원본을 저장하지 않은 결과 (상세페이지 칸, 10-22 이전 결과)는 글자 고치기 불가
    with make_client(tmp_path) as client:
        pid = client.post("/detail-pages", json=DETAIL_BODY).json()["id"]
        wait_done(client, pid)
        gid = db_rows(tmp_path)[0]["id"]
        res = client.post(f"/generations/{gid}/text", json={"position": "top"})
    assert res.status_code == 409


def test_docs_show_text_edit_body(tmp_path):
    with make_client(tmp_path) as client:
        spec = client.get("/openapi.json").json()
    body = spec["paths"]["/generations/{generation_id}/text"]["post"]["requestBody"]
    properties = body["content"]["application/json"]["schema"]["properties"]
    assert {"message", "position", "font", "size_scale"} <= set(properties)
