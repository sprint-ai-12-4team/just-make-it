"""AI로 꾸미기(restyle) 테스트: core.restyle_text와 POST /generations/{id}/restyle.

글자 표현 실험(experiment/model-text)에서 채택한 flare_restyle을 서비스 옵션으로 붙인 것.
flare는 가짜로 바꾸고, 서빙은 Mock 생성기로 돌려 키·GPU 없이 실행한다.
실행: uv run pytest tests/test_restyle.py
"""

import io

import pytest
from PIL import Image
from test_detail_pages import DETAIL_BODY, wait_done
from test_roadmap_api import poll
from test_serving import (  # noqa: F401 (isolate_env는 fixture)
    BASE_BODY,
    db_rows,
    fetch_image,
    isolate_env,
    make_client,
)

from just_make_it import config
from just_make_it.core import ImageGenerationError, ai_models, restyle_text
from just_make_it.core.ai_models.flare import FlareImageModel
from just_make_it.core.base import ImageResult
from just_make_it.core.restyle import (
    MASK_PAD,
    plain_text,
    restyle_prompt,
    text_mask,
)
from just_make_it.serving.generators import CoreGenerator, GeneratorError, MockGenerator
from just_make_it.serving.schemas import GenerationSpec, RestyleInput

# 예전 분위기별 글씨체·색 묘사. 넣으면 결과가 우리 PIL 디자인을 따라가서 프롬프트에 넣지 않음
OLD_DESIGN_WORDS = ("brush", "pink outline", "gold foil", "yellow", "serif", "cream")


def png(color, size=(512, 512)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def image(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


class FakeFlare:
    """flare 편집 흉내: 받은 값을 기억하고, 16의 배수로 줄인 크기의 그림을 돌려준다."""

    model = config.FLARE_MODEL

    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def edit(self, image_bytes, mask_bytes, prompt, width, height):
        self.calls.append(
            {
                "image": image_bytes,
                "mask": mask_bytes,
                "prompt": prompt,
                "size": (width, height),
            }
        )
        if self.fail:
            raise self.fail
        return ImageResult(
            image_bytes=png((200, 40, 40), (width // 16 * 16, height // 16 * 16)),
            model=self.model,
            elapsed_sec=1.5,
            cost_usd=0.042,
        )


@pytest.fixture
def flare(monkeypatch):
    fake = FakeFlare()
    monkeypatch.setattr(ai_models, "get_flare", lambda: fake)
    return fake


# ---------------------------------------------------------------------- core
def test_prompt_keeps_text_and_drops_our_design():
    for style in ["밝고 경쾌한", "따뜻한", "고급스러운", "심플한", "강렬한", None]:
        prompt = restyle_prompt("주말 20% 할인", style)
        assert '"주말 20% 할인"' in prompt and "placeholder" in prompt
        assert "Keep exactly the same characters" in prompt
        assert not any(word in prompt for word in OLD_DESIGN_WORDS), style
    assert "warm and cozy" in restyle_prompt("신메뉴", "따뜻한")


@pytest.mark.parametrize(
    ("background", "fill"),
    [((20, 30, 40), (255, 255, 255)), ((235, 230, 220), (28, 28, 28))],
)
def test_plain_text_is_one_color_skeleton(background, fill):
    combined, box = plain_text(png(background), "두바이 쫀득쿠키 출시", "top")
    x, y, w, h = box
    crop = image(combined).convert("RGB").crop((x, y, x + w, y + h))
    colors = {c for _, c in crop.getcolors(maxcolors=1 << 16)}
    assert fill in colors  # 대비가 큰 색 하나로만 (테두리·그림자 없음)
    assert colors <= {background, fill} | _blends(background, fill)
    assert y < 512 * 0.38  # 위쪽


def _blends(a, b):
    """글자 가장자리 안티앨리어싱 색 (a와 b 사이)."""
    return {
        tuple(round(a[i] + (b[i] - a[i]) * t / 255) for i in range(3))
        for t in range(256)
    }


def test_mask_opens_only_text_area_with_padding():
    box = (100, 50, 200, 40)
    mask = image(text_mask((512, 512), box)).convert("RGBA")
    alpha = mask.getchannel("A")
    assert alpha.getpixel((200, 70)) == 0  # 글자 자리: 다시 그림
    assert alpha.getpixel((100 - int(200 * MASK_PAD) + 1, 70)) == 0  # 여유만큼 넓힘
    assert alpha.getpixel((10, 10)) == 255  # 나머지: 그대로
    assert alpha.getpixel((200, 300)) == 255


def test_restyle_text_sends_plain_text_and_mask(flare):
    background = png((20, 30, 40), (1000, 1000))
    result = restyle_text(background, "  신메뉴 출시  ", "따뜻한", "bottom", 1.2)

    call = flare.calls[0]
    assert call["size"] == (1000, 1000)
    assert image(call["image"]).size == image(call["mask"]).size == (1000, 1000)
    assert '"신메뉴 출시"' in call["prompt"] and "warm and cozy" in call["prompt"]
    assert image(result.image_bytes).size == (1000, 1000)  # 원본 크기로 되돌림
    assert result.cost_usd == 0.042 and result.model == config.FLARE_MODEL
    assert result.text_box[1] > 1000 * 0.5  # bottom


@pytest.mark.parametrize(("message", "position"), [("   ", "top"), ("문구", "left")])
def test_restyle_text_rejects_bad_input(flare, message, position):
    with pytest.raises(ValueError):
        restyle_text(png((0, 0, 0)), message, position=position)
    assert flare.calls == []  # OpenAI를 부르지 않음


def test_flare_edit_sends_mask_and_wraps_errors(monkeypatch):
    sent = {}

    class Images:
        def edit(self, **request):
            sent.update(request)
            raise RuntimeError("rate limit")

    class Client:
        images = Images()

    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    model = FlareImageModel()
    model.client = Client()
    with pytest.raises(ImageGenerationError, match="편집 실패"):
        model.edit(b"img", b"mask", "redesign", 1000, 1000)
    assert sent["mask"][0] == "mask.png" and sent["image"][0] == "image.png"
    assert sent["size"] == "992x992"


# ---------------------------------------------------------------------- 생성기
def spec(**restyle) -> GenerationSpec:
    return GenerationSpec(
        product_name="소금빵",
        message="신메뉴 출시",
        style="따뜻한",
        restyle=RestyleInput(
            background=png((20, 30, 40)),
            text_layout={
                "position": "top",
                "font": "jua",
                "size_scale": 1.0,
                **restyle,
            },
        ),
    )


def test_core_generator_restyles_with_flare(flare):
    generator = CoreGenerator("detailed")
    generator._ready = True
    out = generator.generate(spec())
    assert out.source == "openai" and out.cost_usd == 0.042
    assert (
        out.background_bytes == spec().restyle.background
    )  # 글자 고치기로 되돌릴 원본
    assert out.text_layout["font"] == "jua"
    assert out.params["restyle"] is True and out.image_ms == 1500


def test_core_generator_local_refuses_restyle(flare):
    generator = CoreGenerator("fast")
    generator._ready = True
    with pytest.raises(GeneratorError) as err:
        generator.generate(spec())
    assert err.value.retryable is False and flare.calls == []


def test_core_generator_flare_failure_is_retryable(monkeypatch):
    fake = FakeFlare(fail=ImageGenerationError("timeout"))
    monkeypatch.setattr(ai_models, "get_flare", lambda: fake)
    generator = CoreGenerator("detailed")
    generator._ready = True
    with pytest.raises(GeneratorError) as err:
        generator.generate(spec())
    assert err.value.retryable is True


# ---------------------------------------------------------------------- API
def premium_client(tmp_path, **overrides):
    return make_client(
        tmp_path, premium=MockGenerator(0.01, name="mock-premium"), **overrides
    )


def generate(client) -> dict:
    res = client.post("/generate", json=BASE_BODY)
    assert res.status_code == 200, res.text
    return res.json()


def test_restyle_makes_new_result_linked_to_original(tmp_path):
    with premium_client(tmp_path) as client:
        original = generate(client)
        res = client.post(
            f"/generations/{original['id']}/restyle", headers={"X-Client-Id": "u1"}
        )
        assert res.status_code == 202, res.text
        started = res.json()
        done = poll(client, started["id"])
        again = client.get(f"/generations/{original['id']}").json()
        family = client.get(f"/generations/{original['id']}/family").json()
        restyled = fetch_image(client, done["image_url"])
        before = fetch_image(client, original["image_url"])

    assert (
        started["status"] == "processing" and started["message"] == BASE_BODY["message"]
    )
    assert (started["width"], started["height"]) == (
        original["width"],
        original["height"],
    )
    assert done["status"] == "success" and done["parent_id"] == original["id"]
    assert done["input"]["restyle"] is True
    assert done["input"]["product_name"] == BASE_BODY["product_name"]
    assert done["text_layout"] == original["text_layout"]
    assert done["background_url"]  # 글자 고치기로 되돌릴 수 있음
    assert restyled.size == before.size and restyled.tobytes() != before.tobytes()
    assert again == {**original, **{k: again[k] for k in again if k not in original}}
    assert [item["id"] for item in family["items"]] == [original["id"], done["id"]]
    row = db_rows(tmp_path)[-1]
    assert row["route"] == "premium" and row["client_id"] == "u1"


def test_restyle_uses_edited_text(tmp_path):
    with premium_client(tmp_path) as client:
        original = generate(client)
        client.post(
            f"/generations/{original['id']}/text",
            json={"message": "오늘만 20% 할인", "position": "bottom"},
        )
        gid = client.post(f"/generations/{original['id']}/restyle").json()["id"]
        done = poll(client, gid)
        # 꾸민 결과에서 글자 고치기 → 기본 글자(PIL)로 다시 얹음
        edited = client.post(f"/generations/{gid}/text", json={"message": "내일까지"})
    assert done["message"] == "오늘만 20% 할인"
    assert done["text_layout"]["position"] == "bottom"
    assert edited.status_code == 200 and edited.json()["message"] == "내일까지"


def test_restyle_unknown_id_returns_404(tmp_path):
    with premium_client(tmp_path) as client:
        res = client.post("/generations/nope/restyle")
    assert res.status_code == 404


def test_restyle_without_background_returns_409(tmp_path):
    # 상세페이지 칸은 글자 없는 이미지만 있어 꾸밀 글자가 없음
    with premium_client(tmp_path) as client:
        pid = client.post("/detail-pages", json=DETAIL_BODY).json()["id"]
        wait_done(client, pid)
        section = db_rows(tmp_path)[0]["id"]
        res = client.post(f"/generations/{section}/restyle")
    assert res.status_code == 409


def test_restyle_without_openai_returns_503(tmp_path):
    with make_client(tmp_path) as client:  # 프리미엄(OpenAI) 생성기 없음
        original = generate(client)
        res = client.post(f"/generations/{original['id']}/restyle")
    assert res.status_code == 503
    assert len(db_rows(tmp_path)) == 1  # 새 결과를 만들지 않음


def test_restyle_blocked_by_budget_returns_503(tmp_path):
    with premium_client(tmp_path) as client:
        original = generate(client)
        client.app.state.manager.budget.set(999.0)  # 하루 금액 상한 초과
        res = client.post(f"/generations/{original['id']}/restyle")
    assert res.status_code == 503


@pytest.mark.parametrize(
    "limits",
    [{"daily_job_limit": 1}, {"extra_daily_limit": 1, "client_daily_limit": 0}],
)
def test_restyle_counts_daily_limits(tmp_path, limits):
    with premium_client(tmp_path, **limits) as client:
        original = generate(client)
        if "extra_daily_limit" in limits:  # OpenAI 한도 1번은 첫 꾸미기가 씀
            first = client.post(f"/generations/{original['id']}/restyle")
            assert first.status_code == 202
            poll(client, first.json()["id"])
        res = client.post(f"/generations/{original['id']}/restyle")
    assert res.status_code == 429
