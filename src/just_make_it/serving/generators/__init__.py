"""서빙 생성기 모음과 설정 기반 생성기 선택."""

from ..settings import ServingSettings
from .base import GeneratorError, ImageGenerator
from .core_adapter import CoreGenerator
from .mock import MockGenerator

__all__ = [
    "CoreGenerator",
    "Generators",
    "GeneratorError",
    "ImageGenerator",
    "MockGenerator",
    "build_generators",
]

Generators = tuple[ImageGenerator, ImageGenerator | None, ImageGenerator | None]


def build_generators(settings: ServingSettings) -> Generators:
    """(기본, Fallback, 프리미엄) 생성기를 만든다. 설정하지 않은 자리는 None."""
    if settings.image_backend == "mock":
        delay = settings.mock_delay_seconds
        return (
            MockGenerator(delay, name="mock"),
            MockGenerator(delay, name="mock-fallback"),
            MockGenerator(delay, name="mock-premium"),
        )

    def optional(name: str | None) -> CoreGenerator | None:
        return CoreGenerator(name) if name else None

    return (
        CoreGenerator(settings.primary_image_model),
        optional(settings.fallback_image_model),
        optional(settings.premium_image_model),
    )
