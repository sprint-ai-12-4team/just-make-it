"""keep_product일 때 장면 묘사에 상품이 들어가지 않는지 테스트. 모델은 가짜로 바꿉니다."""

import io

from PIL import Image
from test_core import fakes  # noqa: F401 (fixture)

from just_make_it.core import ai_models, copywriter
from just_make_it.core.base import TextResult
from just_make_it.core.pipeline import generate_ad_image


def cutout_png():
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    image.paste((200, 100, 50, 255), (16, 16, 48, 48))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_scene_only_uses_backdrop_rules(fakes):  # noqa: F811
    product, scene, source, _, _ = copywriter.describe_for_image(
        "소금빵", "신메뉴 출시", "따뜻한", scene_only=True
    )
    assert fakes["gemma"].calls[-1] == copywriter.SCENE_ONLY_RULES
    assert (product, source) == ("", "")
    assert scene.startswith("Warm morning light on a wooden table")


def test_scene_only_default_has_no_product(monkeypatch):
    class Empty:
        def generate(self, instructions, user_input, max_tokens=300):
            return TextResult(text="", model="gemma", elapsed_sec=0.0)

    monkeypatch.setattr(ai_models, "get_gemma", lambda: Empty())
    _, scene, *_ = copywriter.describe_for_image("떡볶이", "신메뉴", scene_only=True)
    assert scene == copywriter.DEFAULT_BACKDROP
    assert "product" not in scene


def test_normal_mode_keeps_product_rules(fakes):  # noqa: F811
    product, _, source, _, _ = copywriter.describe_for_image("소금빵", "신메뉴 출시")
    assert fakes["gemma"].calls[-1] == copywriter.SCENE_RULES
    assert source == "품목 사전" and product


def test_keep_product_pipeline_asks_backdrop_only(fakes):  # noqa: F811
    generate_ad_image(
        "소금빵", "신메뉴 출시", reference_image=cutout_png(), keep_product=True
    )
    assert copywriter.SCENE_ONLY_RULES in fakes["gemma"].calls
    assert copywriter.SCENE_RULES not in fakes["gemma"].calls
