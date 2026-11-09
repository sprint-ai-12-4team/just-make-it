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
            "/generate", json={**BASE_BODY, "image_model": "openai-image-2.5-flare"}
        ).json()
        again = client.post(
            "/generate",
            json={
                **BASE_BODY,
                "parent_id": detailed["id"],
                "image_model": "openai-image-2.5-flare",
            },
        ).json()
        got = {
            name: client.get(f"/generations/{body['id']}").json()["input"]
            for name, body in [("fast", fast), ("detailed", detailed), ("again", again)]
        }
    assert got["fast"]["image_model"] == "flux2-klein-4b"
    assert got["detailed"]["image_model"] == "openai-image-2.5-flare"
    assert got["again"]["image_model"] == "openai-image-2.5-flare"


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
