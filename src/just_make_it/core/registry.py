"""이름으로 이미지, 텍스트 모델을 골라주는 모듈.

새 이미지 모델은 IMAGE_MODELS와 MODEL_LABELS에, 새 텍스트 모델은 TEXT_MODELS에
한 줄씩만 추가하면 됩니다.
"""

from functools import partial

from just_make_it import config
from just_make_it.core.image_models.openai_image import OpenAIImageModel
from just_make_it.core.text_models.openai_text import OpenAITextModel

# 사용자가 고를 수 있는 이미지 모델 목록

IMAGE_MODELS = {
    "gpt-image-2.5-flare": partial(OpenAIImageModel, model="gpt-image-2.5-flare"),
}

# 화면 선택지에 보여줄 설명
MODEL_LABELS = {
    "gpt-image-2.5-flare": "OpenAI 최신 빠른 모델",
}

DEFAULT_IMAGE_BACKEND = config.DEFAULT_IMAGE_BACKEND

# 광고 문구 추천에 쓰는 텍스트 모델 목록
TEXT_MODELS = {
    "gpt-5.6-luna": partial(OpenAITextModel, model="gpt-5.6-luna"),
}

DEFAULT_TEXT_BACKEND = config.DEFAULT_TEXT_BACKEND

# 한 번 만든 모델을 이름별로 보관 (같은 모델을 두 번 불러오지 않기 위해)
_loaded_image_models = {}
_loaded_text_models = {}


def get_image_model(name=None):
    """이름에 맞는 이미지 모델을 한 번만 만들어서 재사용합니다.

    로컬 모델은 불러오는 데 오래 걸리기 때문에 요청마다 새로 만들지 않고 보관해둡니다.

    Args:
        name: 모델 이름 (IMAGE_MODELS의 키). 비우면 기본 모델

    Returns:
        BaseImageModel: 이미지 모델 객체

    Raises:
        ValueError: 등록되지 않은 모델 이름일 때
    """
    name = name or DEFAULT_IMAGE_BACKEND
    if name not in IMAGE_MODELS:
        raise ValueError(
            f"지원하지 않는 이미지 모델입니다: {name} (사용 가능: {list(IMAGE_MODELS)})"
        )
    if name not in _loaded_image_models:
        _loaded_image_models[name] = IMAGE_MODELS[name]()
    return _loaded_image_models[name]


def list_image_models():
    """사용자가 고를 수 있는 이미지 모델 목록을 반환합니다.

    프론트에서 모델 선택지를 만들 때 사용합니다.

    Returns:
        list: 모델 이름과 설명이 담긴 목록 (예: [{"name": "gpt-image-2.5-flare", "label": "..."}])
    """
    return [
        {"name": name, "label": MODEL_LABELS.get(name, name)} for name in IMAGE_MODELS
    ]


def get_text_model(name=None):
    """이름에 맞는 텍스트 모델을 한 번만 만들어서 재사용합니다.

    Args:
        name: 모델 이름 (TEXT_MODELS의 키). 비우면 기본 모델

    Returns:
        BaseTextModel: 텍스트 모델 객체

    Raises:
        ValueError: 등록되지 않은 모델 이름일 때
    """
    name = name or DEFAULT_TEXT_BACKEND
    if name not in TEXT_MODELS:
        raise ValueError(
            f"지원하지 않는 텍스트 모델입니다: {name} (사용 가능: {list(TEXT_MODELS)})"
        )
    if name not in _loaded_text_models:
        _loaded_text_models[name] = TEXT_MODELS[name]()
    return _loaded_text_models[name]


def clear_loaded_models():
    """보관해둔 모델을 모두 비웁니다. 테스트에서 모델을 바꿔 끼울 때 사용합니다."""
    _loaded_image_models.clear()
    _loaded_text_models.clear()
