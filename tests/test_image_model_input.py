"""11-09 요청 S1: 결과 조회 input.image_model (다시 만들기 기본 품질).

실행: uv run pytest tests/test_image_model_input.py
"""

from test_serving import (  # noqa: F401 (isolate_env는 fixture)
    BASE_BODY,
    isolate_env,
    make_client,
)

from just_make_it.service import db
from just_make_it.serving.generators import MockGenerator


# ---------------------------------------------------------------------- S1 image_model
def test_input_image_model_is_saved_and_returned(tmp_path):
    with make_client(tmp_path, premium=MockGenerator(0.01, name="flare")) as client:
        fast = client.post("/generate", json=BASE_BODY).json()
        detailed = client.post(
            "/generate", json={**BASE_BODY, "image_model": "openai-image-2.6-flare"}
        ).json()
        again = client.post(
            "/generate",
            json={
                **BASE_BODY,
                "parent_id": detailed["id"],
                "image_model": "openai-image-2.6-flare",
            },
        ).json()
        got = {
            name: client.get(f"/generations/{body['id']}").json()["input"]
            for name, body in [("fast", fast), ("detailed", detailed), ("again", again)]
        }
    assert got["fast"]["image_model"] == "flux2-klein-4b"
    assert got["detailed"]["image_model"] == "openai-image-2.6-flare"
    assert got["again"]["image_model"] == "openai-image-2.6-flare"


def test_old_rows_have_null_image_model(tmp_path):
    with make_client(tmp_path) as client:
        old = db.start_generation(
            "user-1",
            {"purpose": "instagram", "product_name": "소금빵", "message": "신메뉴"},
            backend="local",
            model="klein",
        )
        got = client.get(f"/generations/{old}").json()["input"]
    assert got["image_model"] is None


# ---------------------------------------------------------------------- 11-11 flare 2.6
LEGACY = "openai-image-2.5-flare"


def test_legacy_flare_name_is_accepted_as_2_6(tmp_path):
    # 프론트가 바뀌기 전 값(2.5)도 받아서 "더 정교하게"로 처리하고 2.6으로 저장
    premium = MockGenerator(0.01, name="flare")
    with make_client(tmp_path, premium=premium) as client:
        body = client.post("/generate", json={**BASE_BODY, "image_model": LEGACY})
        got = client.get(f"/generations/{body.json()['id']}").json()["input"]
    assert body.status_code == 200 and premium.calls == 1  # OpenAI 경로
    assert got["image_model"] == "openai-image-2.6-flare"


def test_old_rows_with_legacy_name_read_as_2_6(tmp_path):
    with make_client(tmp_path) as client:
        old = db.start_generation(
            "user-1",
            {
                "purpose": "instagram",
                "product_name": "소금빵",
                "message": "신메뉴",
                "image_model": LEGACY,
            },
            backend="openai",
            model=LEGACY,
        )
        got = client.get(f"/generations/{old}").json()["input"]
    assert got["image_model"] == "openai-image-2.6-flare"
