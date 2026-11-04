"""keep_product(상품 사진 그대로, 배경 장면만 AI)·상담 악용 기록·대기 카드 출처 테스트.

keep_product: api_spec_next 4장. 모델은 가짜로 바꿔 GPU·API 비용 없이 실행된다.
실행: uv run pytest tests/test_keep_product.py
"""

import io

import pytest
from PIL import Image
from test_assistant import say, start
from test_core import fakes  # noqa: F401 (fixture)
from test_serving import (  # noqa: F401 (isolate_env는 fixture)
    BASE_BODY,
    RecordingMock,
    db_rows,
    isolate_env,
    make_client,
    png_bytes,
)

from just_make_it.core.pipeline import generate_ad_image
from just_make_it.core.prompt_builder import build_scene_prompt
from just_make_it.service.tips import TIPS, pick_tips


def cutout_png(size=(64, 64)) -> bytes:
    """가운데만 불투명한 상품, 나머지는 투명 (배경을 지운 사진)."""
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    w, h = size
    image.paste((200, 100, 50, 255), (w // 4, h // 4, w * 3 // 4, h * 3 // 4))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def keep(client, photo=None, **body):
    files = {"reference_image": ("p.png", photo, "image/png")} if photo else None
    data = {**BASE_BODY, "keep_product": "true", **body}
    if files:
        return client.post("/generate", data=data, files=files)
    return client.post("/generate", json={**data, "keep_product": True})


# ---------------------------------------------------------------------- core
def test_scene_prompt_leaves_lower_center_empty():
    prompt = build_scene_prompt(
        "warm morning light on a wooden table", purpose="commerce", style="따뜻한"
    )
    assert "no product" in prompt and "lower center" in prompt
    assert "60 percent" in prompt and "upper third" in prompt
    assert "product centered" not in prompt  # commerce 기본 구도 문구는 빼야 함
    assert "No text" in prompt


def test_core_keep_product_draws_scene_only(fakes):  # noqa: F811
    result = generate_ad_image(
        "소금빵", "신메뉴 출시", reference_image=cutout_png(), keep_product=True
    )
    call = fakes["klein"].calls[0]
    assert call["reference"] is None  # 사진은 모델에 넣지 않음
    assert "butter roll" not in call["prompt"]  # 상품 묘사도 넣지 않음
    assert "no product" in call["prompt"]
    # 소금빵은 local_ok=False지만 상품을 안 그리므로 flare로 가지 않음
    assert fakes["flare"].calls == []
    assert result.image_fallback_reason == ""
    assert result.text_layout["position"] == "top"
    assert result.used_reference is False


def test_core_keep_product_needs_photo(fakes):  # noqa: F811
    with pytest.raises(ValueError):
        generate_ad_image("소금빵", "신메뉴 출시", keep_product=True)


# ---------------------------------------------------------------------- serving
def test_keep_product_returns_product_url(tmp_path):
    primary = RecordingMock(0.01)
    with make_client(tmp_path, primary=primary) as client:
        res = keep(client, cutout_png())
        assert res.status_code == 200, res.text
        body = res.json()
        got = client.get(f"/generations/{body['id']}").json()
        product = client.get(body["product_url"].split("8000", 1)[-1])
    assert primary.specs[0].keep_product is True
    assert body["product_url"].endswith(f"{body['id']}-product.png")
    assert body["text_layout"]["position"] == "top"
    assert got["product_url"] == body["product_url"]
    assert got["input"]["keep_product"] is True
    assert product.status_code == 200
    assert Image.open(io.BytesIO(product.content)).mode == "RGBA"


def test_normal_generation_has_no_product_url(tmp_path):
    with make_client(tmp_path) as client:
        body = client.post("/generate", json=BASE_BODY).json()
        got = client.get(f"/generations/{body['id']}").json()
    assert body["product_url"] is None and got["product_url"] is None
    assert got["input"]["keep_product"] is False


@pytest.mark.parametrize("photo", [None, png_bytes()], ids=["no-photo", "opaque-photo"])
def test_keep_product_needs_cutout_photo(tmp_path, photo):
    with make_client(tmp_path) as client:
        res = keep(client, photo)
    assert res.status_code == 400
    assert db_rows(tmp_path) == []  # 대기열에 넣지 않음


def test_keep_product_regenerate_reuses_parent_product(tmp_path):
    primary = RecordingMock(0.01)
    with make_client(tmp_path, primary=primary) as client:
        first = keep(client, cutout_png()).json()
        again = keep(client, parent_id=first["id"])
        assert again.status_code == 200, again.text
    assert primary.specs[1].reference_image == primary.specs[0].reference_image
    assert again.json()["product_url"].endswith("-product.png")


def test_keep_product_rejects_normal_parent_photo(tmp_path):
    with make_client(tmp_path) as client:
        first = client.post(
            "/generate",
            data=BASE_BODY,
            files={"reference_image": ("p.png", png_bytes(), "image/png")},
        ).json()
        res = keep(client, parent_id=first["id"])
    assert res.status_code == 400


def test_product_url_kept_after_saving_edited_image(tmp_path):
    with make_client(tmp_path) as client:
        body = keep(client, cutout_png()).json()
        size = (body["width"], body["height"])
        saved = client.post(
            f"/generations/{body['id']}/image",
            files={
                "image": ("i.png", png_bytes(size), "image/png"),
                "background": ("b.png", png_bytes(size), "image/png"),
            },
        )
        assert saved.status_code == 200, saved.text
    assert saved.json()["edited"] is True
    assert saved.json()["product_url"] == body["product_url"]


# ---------------------------------------------------------------------- 상담 악용 기록
def test_moderation_and_off_topic_end_are_flagged(tmp_path):
    with make_client(tmp_path) as client:
        c = start(client)
        assert (
            say(client, c["id"], "MODERATION_TEST 나쁜 말", chip=False).status_code
            == 400
        )
        other = start(client)
        for _ in range(3):
            say(client, other["id"], "주식 추천해 줘", chip=False)
    rows = db_rows(tmp_path, "SELECT * FROM flags ORDER BY id")
    assert [(r["reason"], r["consult_id"]) for r in rows] == [
        ("moderation", c["id"]),
        ("off_topic", other["id"]),
    ]
    assert rows[0]["client_id"] == "user-1"
    assert not db_rows(tmp_path, "SELECT * FROM events")  # events에는 남기지 않음


# ---------------------------------------------------------------------- 대기 카드 출처
def test_tip_sources_are_official_links():
    with_source = [t for t in TIPS if t.get("source")]
    assert {t["id"] for t in with_source} >= {
        "platform-yt-size",
        "platform-kakao-ad",
        "law-best",
        "law-food",
        "law-discount",
    }
    for t in with_source:
        assert t["source"]["url"].startswith(
            ("https://www.law.go.kr/", "https://support.google.com/")
        )
    yt = next(
        t for t in pick_tips("youtube", limit=12) if t["id"] == "platform-yt-size"
    )
    assert yt["source"]["name"] == "YouTube 고객센터"
    assert yt["checked_at"] == "2026-11-04"
    assert "50MB" in yt["body"]
