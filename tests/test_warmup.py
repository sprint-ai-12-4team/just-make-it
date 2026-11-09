"""서버 시작 시 klein 웜업(pipeline.warmup) 테스트. 모델은 가짜로 바꿉니다."""

from test_core import fakes  # noqa: F401 (fixture)

from just_make_it import config
from just_make_it.core import ai_models, pipeline
from just_make_it.core.base import ImageGenerationError


def test_warmup_makes_one_small_klein_image(fakes):  # noqa: F811
    elapsed = pipeline.warmup()
    assert isinstance(elapsed, float)
    assert fakes["klein"].calls == [
        {
            "prompt": pipeline.WARMUP_PROMPT,
            "size": (pipeline.WARMUP_SIZE, pipeline.WARMUP_SIZE),
            "reference": None,
            "seed": 0,
        }
    ]


def test_warmup_never_calls_openai(fakes):  # noqa: F811
    fakes["klein"].fail = True
    assert pipeline.warmup() is None
    assert fakes["flare"].calls == []
    assert fakes["luna"].calls == []


def test_warmup_survives_klein_load_failure(fakes, monkeypatch):  # noqa: F811
    def no_gpu():
        raise ImageGenerationError("GPU가 없습니다")

    monkeypatch.setattr(ai_models, "get_klein", no_gpu)
    assert pipeline.warmup() is None
    assert fakes["flare"].calls == []


def test_warmup_skipped_when_unloading_after_use(fakes, monkeypatch):  # noqa: F811
    monkeypatch.setattr(config, "KLEIN_UNLOAD_AFTER_USE", True)
    assert pipeline.warmup() is None
    assert fakes["klein"].calls == []
