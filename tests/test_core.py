"""모델 파트(core) 테스트. 가짜 모델을 쓰기 때문에 API 비용이 들지 않슴당.

실행: python -m pytest tests/test_core.py
"""

import pytest

from just_make_it.core import pipeline, registry
from just_make_it.core.base import (
    BaseImageModel,
    BaseTextModel,
    ImageGenerationError,
    ImageResult,
    TextResult,
)
from just_make_it.core.copywriter import parse_copies, suggest_ad_copies
from just_make_it.core.image_models.openai_image import OpenAIImageModel, _guess_mime
from just_make_it.core.prompt_builder import build_image_prompt, get_image_size
from just_make_it.core.registry import list_image_models


class FakeImageModel(BaseImageModel):
    """테스트용 가짜 모델. 새 모델을 추가하는 방법의 예시."""

    name = "fake"

    def __init__(self):
        self.last_call = None

    def generate(self, prompt, width, height, **options):
        self.last_call = {"prompt": prompt, "width": width, "height": height, **options}
        return ImageResult(image_bytes=b"fake-png", model="fake-model", elapsed_sec=0.1)


@pytest.fixture
def fake_model(monkeypatch):
    """registry에 가짜 모델을 등록하고 캐시를 비웁니다."""
    monkeypatch.setitem(registry.IMAGE_MODELS, "fake", FakeImageModel)
    registry.clear_loaded_models()
    yield
    registry.clear_loaded_models()


def test_size_by_purpose():
    assert get_image_size("youtube") == (1536, 864)
    assert get_image_size("없는목적") == (1024, 1024)


def test_prompt_quick_mode_includes_korean_text():
    prompt = build_image_prompt(
        "소금빵", "신메뉴 출시", style="따뜻한", include_text=True
    )
    assert '"신메뉴 출시"' in prompt
    assert "warm" in prompt


def test_prompt_requires_inputs():
    with pytest.raises(ValueError):
        build_image_prompt("  ", "신메뉴 출시")


def test_openai_size_is_multiple_of_16():
    assert OpenAIImageModel._size_for(1536, 864) == "1536x864"
    assert OpenAIImageModel._size_for(1080, 1920) == "1072x1920"


def test_new_model_plugs_in_without_changing_generator(fake_model):
    result = pipeline.generate_ad_image(
        "소금빵",
        "신메뉴 출시",
        purpose="kakao",
        generation_mode="template",
        backend="fake",
    )
    model = registry.get_image_model("fake")

    assert result.image_bytes == b"fake-png"
    assert result.backend == "fake"
    assert (result.width, result.height) == (1024, 1536)
    assert "Do not include any text" in model.last_call["prompt"]


def test_model_is_loaded_only_once(fake_model, monkeypatch):
    assert registry.get_image_model("fake") is registry.get_image_model("fake")
    # 이름을 비웠을 때와 기본 모델 이름을 넣었을 때도 같은 모델이어야 함
    monkeypatch.setattr(registry, "DEFAULT_IMAGE_BACKEND", "fake")
    assert registry.get_image_model() is registry.get_image_model("fake")


def test_unknown_backend():
    with pytest.raises(ValueError):
        pipeline.generate_ad_image("소금빵", "신메뉴 출시", backend="없는모델")


def test_default_model_is_gpt_image_2_5_flare(monkeypatch):
    monkeypatch.setattr(OpenAIImageModel, "__init__", _fake_openai_init)
    registry.clear_loaded_models()

    names = [m["name"] for m in list_image_models()]
    assert names == ["gpt-image-2.5-flare"]
    assert registry.get_image_model().model == "gpt-image-2.5-flare"
    registry.clear_loaded_models()


def _fake_openai_init(self, model=None, quality=None):
    """키 없이 모델 이름만 확인하려고 쓰는 가짜 초기화."""
    self.model = model
    self.quality = quality


# ---------- 참고 사진 ----------


def test_prompt_with_reference_keeps_product():
    prompt = build_image_prompt("청담 카페라떼", "오픈 이벤트", has_reference=True)
    assert "reference image" in prompt
    assert "exactly as they are" in prompt


def test_reference_image_is_passed_to_model(fake_model):
    photo = b"\x89PNG fake photo"
    pipeline.generate_ad_image(
        "청담 카페라떼", "오픈 이벤트", backend="fake", reference_image=photo
    )
    assert registry.get_image_model("fake").last_call["reference_image"] == photo


def test_guess_mime():
    assert _guess_mime(b"\x89PNG....") == "image/png"
    assert _guess_mime(b"\xff\xd8\xff....") == "image/jpeg"
    assert _guess_mime(b"RIFF1234WEBPVP8") == "image/webp"
    with pytest.raises(ImageGenerationError):
        _guess_mime(b"GIF89a")


# ---------- 조금 수정하기 ----------


def test_adjustments_are_added_to_prompt():
    prompt = build_image_prompt(
        "소금빵",
        "신메뉴 출시",
        include_text=True,
        adjustments=["더 밝게", "글자 더 크게"],
    )
    assert "brighter" in prompt
    assert "larger" in prompt


def test_text_adjustments_skipped_without_text():
    prompt = build_image_prompt(
        "소금빵",
        "신메뉴 출시",
        include_text=False,
        adjustments=["글자 더 크게", "배경 단순하게"],
    )
    assert "larger" not in prompt
    assert "simpler" in prompt


def test_shorten_adjustment_changes_message(fake_model, monkeypatch):
    monkeypatch.setattr(pipeline, "shorten_message", lambda message: "오픈 이벤트")
    result = pipeline.generate_ad_image(
        "청담 카페라떼",
        "청담 카페라떼 오픈 기념 전 메뉴 이벤트",
        backend="fake",
        adjustments=["텍스트 짧게"],
    )
    assert result.message == "오픈 이벤트"
    assert '"오픈 이벤트"' in result.prompt


def test_shorten_works_in_template_mode(fake_model, monkeypatch):
    monkeypatch.setattr(pipeline, "shorten_message", lambda message: "오픈 이벤트")
    result = pipeline.generate_ad_image(
        "청담 카페라떼",
        "청담 카페라떼 오픈 기념 전 메뉴 이벤트",
        generation_mode="template",
        backend="fake",
        adjustments=["텍스트 짧게"],
    )
    # 템플릿 모드는 웹에서 글자를 얹으니 줄인 문구가 결과로 넘어가야 함
    assert result.message == "오픈 이벤트"


def test_empty_message_checked_before_shorten(fake_model, monkeypatch):
    def fail_if_called(message):
        raise AssertionError("빈 문구인데 문구 줄이기를 호출했습니다")

    monkeypatch.setattr(pipeline, "shorten_message", fail_if_called)
    with pytest.raises(ValueError):
        pipeline.generate_ad_image(
            "청담 카페라떼", "  ", backend="fake", adjustments=["텍스트 짧게"]
        )


# ---------- 광고 문구 추천 ----------


class FakeTextModel(BaseTextModel):
    """테스트용 가짜 텍스트 모델."""

    def generate(self, instructions, user_input, **options):
        text = '1. 갓 구운 버터 향\n- 오늘의 첫 소금빵\n\n"주말 한정 20% 할인"\n넷째 줄'
        return TextResult(text=text, model="fake-text", elapsed_sec=0.1)


def test_parse_copies_removes_numbering():
    text = '1. 갓 구운 버터 향\n- 오늘의 첫 소금빵\n\n"주말 한정 20% 할인"\n넷째 줄'
    assert parse_copies(text, 3) == [
        "갓 구운 버터 향",
        "오늘의 첫 소금빵",
        "주말 한정 20% 할인",
    ]


def test_suggest_ad_copies_with_fake_model(monkeypatch):
    monkeypatch.setitem(registry.TEXT_MODELS, "fake-text", FakeTextModel)
    registry.clear_loaded_models()
    copies = suggest_ad_copies("소금빵", "신메뉴 출시", backend="fake-text")
    assert copies == ["갓 구운 버터 향", "오늘의 첫 소금빵", "주말 한정 20% 할인"]
    registry.clear_loaded_models()


def test_empty_quality_uses_default(monkeypatch):
    calls = []

    class FakeImages:
        def generate(self, **request):
            calls.append(request)
            raise RuntimeError("요청 내용만 확인하고 멈춤")

    monkeypatch.setattr(OpenAIImageModel, "__init__", _fake_openai_init)
    model = OpenAIImageModel("gpt-image-2.5-flare", "medium")
    model.client = type("FakeClient", (), {"images": FakeImages()})()
    with pytest.raises(ImageGenerationError):
        model.generate("prompt", 1024, 1024, quality=None)
    assert calls[0]["quality"] == "medium"
