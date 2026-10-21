"""파이프라인에서 쓰는 모델 4개를 꺼내 주는 곳.

- 로컬 모델 (VM): Gemma 4 12B (텍스트), FLUX.2 [klein] 4B (이미지)
- API 모델 (OpenAI): gpt-5.6-luna (텍스트), gpt-image-2.5-flare (이미지)

모델은 처음 부를 때 한 번만 만들고 계속 재사용합니다.
"""

import threading

_loaded = {}
_lock = threading.Lock()


def _get(key, make):
    with _lock:
        if key not in _loaded:
            _loaded[key] = make()
    return _loaded[key]


def get_gemma():
    """로컬 텍스트 모델 Gemma 4 12B를 돌려줍니다."""
    from just_make_it.core.ai_models.gemma import GemmaTextModel

    return _get("gemma", GemmaTextModel)


def get_luna():
    """API 텍스트 모델 gpt-5.6-luna를 돌려줍니다.

    Raises:
        TextGenerationError: OPENAI_API_KEY가 없을 때
    """
    from just_make_it.core.ai_models.luna import LunaTextModel

    return _get("luna", LunaTextModel)


def get_klein():
    """로컬 이미지 모델 FLUX.2 [klein] 4B를 돌려줍니다.

    Raises:
        ImageGenerationError: GPU가 없거나 불러오기에 실패했을 때
    """
    from just_make_it.core.ai_models.klein import KleinImageModel

    return _get("klein", KleinImageModel)


def get_flare():
    """API 이미지 모델 gpt-image-2.5-flare를 돌려줍니다.

    Raises:
        ImageGenerationError: OPENAI_API_KEY가 없을 때
    """
    from just_make_it.core.ai_models.flare import FlareImageModel

    return _get("flare", FlareImageModel)


def clear_models():
    """불러온 모델을 모두 비웁니다. GPU 메모리를 비울 때 씁니다."""
    with _lock:
        klein = _loaded.get("klein")
        if klein is not None and hasattr(klein, "close"):
            klein.close()
        _loaded.clear()
