"""파이프라인 V1 테스트. 실제 모델 대신 가짜 모델을 끼워서 API 비용과 GPU 없이 확인합니다."""

import io
import re

import pytest
from PIL import Image

from just_make_it import config
from just_make_it.core import ai_models
from just_make_it.core.base import (
    ImageGenerationError,
    ImageResult,
    TextGenerationError,
    TextResult,
)
from just_make_it.core.copywriter import (
    describe_for_image,
    parse_copies,
    shorten_message,
    suggest_ad_copies,
)
from just_make_it.core.pipeline import generate_ad_image
from just_make_it.core.prompt_builder import (
    PURPOSE_SIZES,
    build_image_prompt,
    get_image_size,
)
from just_make_it.core.text_overlay import DESIGNS, render_text


def png_bytes(width=256, height=256, color="skyblue", fmt="PNG"):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format=fmt)
    return buffer.getvalue()


class FakeText:
    """지시문을 보고 그럴듯한 답을 돌려주는 가짜 텍스트 모델."""

    def __init__(self, name, fail=False, cost=0.0):
        self.name = name
        self.fail = fail
        self.cost = cost
        self.calls = []

    def generate(self, instructions, user_input, max_tokens=300):
        self.calls.append(instructions)
        if self.fail:
            raise TextGenerationError("Ollama 연결 실패")
        if "카피라이터" in instructions:
            text = '1. 갓 구운 버터 향, 오늘의 첫 소금빵\n- 따뜻한 온기에 담은 소금빵\n"입안 가득 고소한 풍미"'
        elif "편집자" in instructions:
            text = "오늘의 소금빵"
        else:
            text = "PRODUCT: a golden roll (소금빵)\nSCENE: Warm morning light on a wooden table."
        return TextResult(
            text=text, model=self.name, elapsed_sec=0.0, cost_usd=self.cost
        )


class FakeImage:
    """요청한 크기의 4분의 1로 단색 이미지를 돌려주는 가짜 이미지 모델."""

    def __init__(self, name, fail=False, cost=0.0):
        self.name = name
        self.fail = fail
        self.cost = cost
        self.calls = []

    def generate(self, prompt, width, height, reference_image=None, seed=None):
        self.calls.append(
            {
                "prompt": prompt,
                "size": (width, height),
                "reference": reference_image,
                "seed": seed,
            }
        )
        if self.fail:
            raise ImageGenerationError("GPU 메모리 부족")
        return ImageResult(
            image_bytes=png_bytes(width // 4, height // 4),
            model=self.name,
            elapsed_sec=0.1,
            cost_usd=self.cost,
            seed=seed if seed is not None else 7,
        )


@pytest.fixture
def fakes(monkeypatch):
    """가짜 모델 4개를 끼워 넣습니다."""
    gemma = FakeText("gemma4:12b-it-qat")
    luna = FakeText("gpt-5.6-luna", cost=0.0004)
    klein = FakeImage("FLUX.2 [klein] 4B")
    flare = FakeImage("gpt-image-2.5-flare", cost=0.0136)
    monkeypatch.setattr(ai_models, "get_gemma", lambda: gemma)
    monkeypatch.setattr(ai_models, "get_luna", lambda: luna)
    monkeypatch.setattr(ai_models, "get_klein", lambda: klein)
    monkeypatch.setattr(ai_models, "get_flare", lambda: flare)
    monkeypatch.setattr(config, "USE_FALLBACK", True)
    return {"text": gemma, "gemma": gemma, "luna": luna, "klein": klein, "flare": flare}


def test_parse_copies_removes_numbers_and_symbols():
    assert parse_copies('1. 첫 문구\n- 둘째 문구\n"셋째"\n넷째', 3) == [
        "첫 문구",
        "둘째 문구",
        "셋째",
    ]


def test_suggest_ad_copies_returns_three(fakes):
    copies = suggest_ad_copies("소금빵", "신메뉴 출시", style="따뜻한")
    assert copies == [
        "갓 구운 버터 향, 오늘의 첫 소금빵",
        "따뜻한 온기에 담은 소금빵",
        "입안 가득 고소한 풍미",
    ]


def test_suggest_ad_copies_requires_input(fakes):
    with pytest.raises(ValueError):
        suggest_ad_copies(" ", "신메뉴 출시")
    assert fakes["text"].calls == []


def test_shorten_message(fakes):
    message, _, reason = shorten_message("갓 구운 버터 향 가득한 오늘의 첫 소금빵")
    assert (message, reason) == ("오늘의 소금빵", "")


def test_describe_uses_dictionary_for_known_item(fakes):
    product, scene, source, _, _ = describe_for_image("소금빵", "신메뉴 출시", "따뜻한")
    assert source == "품목 사전"
    assert "butter roll" in product
    assert scene == "Warm morning light on a wooden table"


def test_describe_removes_korean_for_unknown_item(fakes):
    product, scene, source, _, _ = describe_for_image("동네빵집 버터롤", "신메뉴 출시")
    assert source == "텍스트 모델"
    assert product == "a golden roll"
    assert not re.search("[가-힣]", product + scene)


def test_prompt_is_english_and_text_free():
    prompt = build_image_prompt(
        "a golden roll", "Warm light", purpose="instagram", style="따뜻한"
    )
    assert "No text" in prompt
    assert "reference image" not in prompt
    assert not re.search("[가-힣]", prompt)


def test_prompt_with_reference_keeps_product():
    prompt = build_image_prompt(
        "a golden roll", "Warm light", has_reference=True, adjustments=["더 밝게"]
    )
    assert prompt.startswith("Use the product in the reference image")
    assert "brighter" in prompt


def test_sizes_are_multiples_of_16():
    for purpose in PURPOSE_SIZES:
        width, height = get_image_size(purpose)
        assert width % 16 == 0 and height % 16 == 0
    assert get_image_size("없는목적") == PURPOSE_SIZES["free"]


def test_render_text_all_designs_keep_size():
    background = png_bytes(512, 512)
    for mood in list(DESIGNS) + [None]:
        result = render_text(background, "갓 구운 버터 향, 오늘의 소금빵", mood)
        image = Image.open(io.BytesIO(result))
        assert image.size == (512, 512)
        assert result != background


def test_render_text_rare_glyph_uses_fallback_font():
    result = render_text(png_bytes(512, 512), "똠양꿍 신메뉴", "밝고 경쾌한")
    assert Image.open(io.BytesIO(result)).size == (512, 512)


def test_quick_mode_uses_klein_and_overlays_text(fakes):
    result = generate_ad_image(
        "동네빵집 버터롤", "신메뉴 출시", purpose="youtube", style="밝고 경쾌한"
    )
    assert result.image_model == "FLUX.2 [klein] 4B"
    assert result.image_fallback_reason == ""
    assert result.text_model == "gemma4:12b-it-qat"
    assert fakes["luna"].calls == []
    assert result.image_bytes != result.background_bytes
    assert fakes["klein"].calls[0]["size"] == (1536, 864)
    assert result.cost_usd == 0
    assert not re.search("[가-힣]", result.prompt)


def test_template_mode_returns_image_only(fakes):
    result = generate_ad_image(
        "동네빵집 버터롤", "신메뉴 출시", generation_mode="template"
    )
    assert result.image_bytes == result.background_bytes


def test_fallback_when_klein_fails(fakes):
    fakes["klein"].fail = True
    result = generate_ad_image("동네빵집 버터롤", "신메뉴 출시")
    assert result.image_model == "gpt-image-2.5-flare"
    assert "klein 실패" in result.image_fallback_reason
    assert result.cost_usd > 0


def test_no_fallback_raises(fakes, monkeypatch):
    fakes["klein"].fail = True
    monkeypatch.setattr(config, "USE_FALLBACK", False)
    with pytest.raises(ImageGenerationError):
        generate_ad_image("동네빵집 버터롤", "신메뉴 출시")
    assert fakes["flare"].calls == []


def test_unknown_item_without_reference_goes_to_flare(fakes):
    result = generate_ad_image("소금빵", "신메뉴 출시", style="따뜻한")
    assert result.image_model == "gpt-image-2.5-flare"
    assert result.product_source == "품목 사전"
    assert fakes["klein"].calls == []


def test_unknown_item_with_reference_uses_klein(fakes):
    result = generate_ad_image(
        "소금빵", "신메뉴 출시", reference_image=png_bytes(fmt="JPEG")
    )
    assert result.image_model == "FLUX.2 [klein] 4B"
    assert result.used_reference
    reference = fakes["klein"].calls[0]["reference"]
    assert reference.startswith(b"\x89PNG")
    assert result.prompt.startswith("Use the product in the reference image")


def test_bad_reference_raises_value_error(fakes):
    with pytest.raises(ValueError):
        generate_ad_image(
            "동네빵집 버터롤", "신메뉴 출시", reference_image=b"not an image"
        )


def test_empty_input_raises_before_any_model_call(fakes):
    with pytest.raises(ValueError):
        generate_ad_image("", "신메뉴 출시", adjustments=["텍스트 짧게"])
    assert fakes["text"].calls == []
    assert fakes["klein"].calls == []


def test_shorten_chip_changes_message(fakes):
    result = generate_ad_image(
        "동네빵집 버터롤",
        "갓 구운 버터 향 가득한 오늘의 첫 소금빵",
        adjustments=["텍스트 짧게"],
    )
    assert result.message == "오늘의 소금빵"


def test_bigger_text_chip_changes_overlay(fakes):
    normal = generate_ad_image("동네빵집 버터롤", "신메뉴 출시", style="심플한")
    bigger = generate_ad_image(
        "동네빵집 버터롤", "신메뉴 출시", style="심플한", adjustments=["글자 더 크게"]
    )
    assert normal.image_bytes != bigger.image_bytes


def test_unknown_style_is_not_in_prompt():
    prompt = build_image_prompt("a golden roll", "Warm light", style="없는 분위기")
    assert "Mood" not in prompt
    assert not re.search("[가-힣]", prompt)


def test_describe_reads_bold_labels(fakes, monkeypatch):
    def bold_answer(instructions, user_input, max_tokens=300):
        text = "**PRODUCT**: a red cake\n**Scene:** Soft light on a table."
        return TextResult(text=text, model="fake-gemma", elapsed_sec=0.0)

    monkeypatch.setattr(fakes["text"], "generate", bold_answer)
    product, scene, *_ = describe_for_image("동네빵집 케이크", "신메뉴 출시")
    assert product == "a red cake"
    assert scene == "Soft light on a table"


def test_result_size_is_real_image_size(fakes):
    result = generate_ad_image("동네빵집 버터롤", "신메뉴 출시", purpose="youtube")
    image = Image.open(io.BytesIO(result.image_bytes))
    assert (result.width, result.height) == image.size


def test_gemma_retries_without_think(monkeypatch):
    from just_make_it.core.ai_models import gemma

    class Response:
        def __init__(self, status, payload):
            self.status_code = status
            self.text = str(payload)
            self.payload = payload

        def raise_for_status(self):
            if self.status_code >= 400:
                raise gemma.requests.HTTPError(self.text)

        def json(self):
            return self.payload

    bodies = []

    def fake_post(url, json, timeout):
        bodies.append(dict(json))
        if "think" in json:
            return Response(400, {"error": "think not supported"})
        return Response(200, {"message": {"content": "오늘의 소금빵"}})

    monkeypatch.setattr(gemma.requests, "post", fake_post)
    model = gemma.GemmaTextModel()
    assert model.generate("규칙", "입력").text == "오늘의 소금빵"
    assert "think" in bodies[0] and "think" not in bodies[1]


def test_report_counts_models_and_cost():
    from just_make_it.core.evaluation.make_report import build_report

    base = {
        "case_id": "C01",
        "purpose": "free",
        "product_name": "소금빵",
        "message": "신메뉴",
        "style": "",
        "generation_mode": "quick",
        "error": "",
        "image": "images/C01.png",
        "prompt": "p",
        "elapsed_sec": "1",
    }
    rows = [
        {**base, "model": "FLUX.2 [klein] 4B", "cost_usd": "0"},
        {
            **base,
            "case_id": "C02",
            "model": "gpt-image-2.5-flare",
            "cost_usd": "0.0142",
        },
    ]
    report = build_report({"run1": rows})
    assert "FLUX.2 [klein] 4B 1, gpt-image-2.5-flare 1" in report
    assert "0.0142" in report


def test_seed_is_returned_and_reused(fakes):
    first = generate_ad_image("동네빵집 버터롤", "신메뉴 출시")
    assert first.seed == 7
    assert fakes["klein"].calls[0]["seed"] is None
    generate_ad_image(
        "동네빵집 버터롤", "신메뉴 출시", adjustments=["더 밝게"], seed=first.seed
    )
    assert fakes["klein"].calls[1]["seed"] == 7


def test_detailed_and_natural_use_api_models(fakes):
    result = generate_ad_image(
        "동네빵집 버터롤",
        "신메뉴 출시",
        image_quality="detailed",
        text_quality="natural",
    )
    assert result.image_model == "gpt-image-2.5-flare"
    assert result.text_model == "gpt-5.6-luna"
    assert result.image_fallback_reason == ""
    assert result.text_fallback_reason == ""
    assert fakes["klein"].calls == []
    assert fakes["gemma"].calls == []


def test_gemma_fails_falls_back_to_luna(fakes):
    fakes["gemma"].fail = True
    result = generate_ad_image("동네빵집 버터롤", "신메뉴 출시")
    assert result.text_model == "gpt-5.6-luna"
    assert "Gemma 실패" in result.text_fallback_reason
    assert result.image_model == "FLUX.2 [klein] 4B"


def test_gemma_fails_without_fallback_raises(fakes, monkeypatch):
    fakes["gemma"].fail = True
    monkeypatch.setattr(config, "USE_FALLBACK", False)
    with pytest.raises(TextGenerationError):
        suggest_ad_copies("소금빵", "신메뉴 출시")
    assert fakes["luna"].calls == []


def test_suggest_with_natural_uses_luna(fakes):
    copies = suggest_ad_copies("소금빵", "신메뉴 출시", text_quality="natural")
    assert len(copies) == 3
    assert fakes["gemma"].calls == []


def test_wrong_quality_raises_before_any_model_call(fakes):
    with pytest.raises(ValueError):
        generate_ad_image("동네빵집 버터롤", "신메뉴 출시", image_quality="best")
    with pytest.raises(ValueError):
        generate_ad_image("동네빵집 버터롤", "신메뉴 출시", text_quality="best")
    with pytest.raises(ValueError):
        suggest_ad_copies("소금빵", "신메뉴 출시", text_quality="best")
    assert fakes["gemma"].calls == [] and fakes["klein"].calls == []


def test_cost_adds_flare_and_luna(fakes):
    result = generate_ad_image(
        "동네빵집 버터롤",
        "갓 구운 버터 향 가득한 오늘의 첫 소금빵",
        image_quality="detailed",
        text_quality="natural",
        adjustments=["텍스트 짧게"],
    )
    # flare 1번 + luna 2번 (문구 줄이기, 영어 묘사)
    assert result.cost_usd == pytest.approx(0.0136 + 0.0004 * 2)


def test_flare_cost_splits_text_and_image_input():
    from types import SimpleNamespace

    from just_make_it.core.ai_models.flare import _cost_usd

    usage = SimpleNamespace(
        input_tokens=1100,
        input_tokens_details=SimpleNamespace(text_tokens=100, image_tokens=1000),
        output_tokens=1000,
    )
    assert _cost_usd(usage) == pytest.approx((100 * 5 + 1000 * 8 + 1000 * 30) / 1e6)
    no_details = SimpleNamespace(input_tokens=100, output_tokens=1000)
    assert _cost_usd(no_details) == pytest.approx((100 * 5 + 1000 * 30) / 1e6)
    assert _cost_usd(None) == 0.0


def test_luna_cost():
    from types import SimpleNamespace

    from just_make_it.core.ai_models.luna import LunaTextModel

    model = LunaTextModel.__new__(LunaTextModel)
    model.model = "gpt-5.6-luna"
    response = SimpleNamespace(
        output_text="오늘의 소금빵",
        usage=SimpleNamespace(input_tokens=1000, output_tokens=500),
    )
    model.client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: response)
    )
    result = model.generate("규칙", "입력")
    assert result.cost_usd == pytest.approx((1000 * 0.20 + 500 * 1.20) / 1e6)
