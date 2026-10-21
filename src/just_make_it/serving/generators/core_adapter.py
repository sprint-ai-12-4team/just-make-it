"""core 파트의 `generate_ad_image()`를 서빙 규격으로 감싸는 어댑터.

모델 선택·프롬프트·크기·문구 줄이기는 모두 core가 처리하고, 서빙은 결과 바이트만 받는다.
core의 함수 이름이나 인자가 바뀌면 이 파일만 고치면 된다.
"""

import logging

from ..schemas import GenerationOutput, GenerationSpec, Source
from .base import GeneratorError, ImageGenerator

logger = logging.getLogger(__name__)

# 글자는 프론트가 이미지 위에 얹는다 (api_spec 5장, 2026-10-20 결정).
# core에서 generation_mode가 빠지기 전까지 글자 없는 프롬프트를 쓰는 모드를 고정으로 넘긴다
TEXT_FREE_MODE = "canvas"


class CoreGenerator(ImageGenerator):
    """core registry에 등록된 이미지 모델 하나로 생성한다.

    Args:
        backend: registry의 모델 이름. None이면 core 기본 모델.
    """

    def __init__(self, backend: str | None = None) -> None:
        from just_make_it.core import registry

        self.backend = backend or registry.DEFAULT_IMAGE_BACKEND
        self.name = f"core:{self.backend}"
        self._provider: str | None = None
        self._load_error: str | None = None

    @property
    def source(self) -> Source:
        return "openai" if self._provider == "openai" else "local"

    @property
    def is_ready(self) -> bool:
        return self._provider is not None

    def load(self) -> None:
        """모델 객체를 미리 만들어 둔다 (이름 오류·API 키 누락을 서버 시작 때 발견)."""
        from just_make_it.core import registry

        try:
            model = registry.get_image_model(self.backend)
        except Exception as exc:
            self._load_error = str(exc)
            logger.warning("이미지 모델 준비 실패 (%s): %s", self.backend, exc)
            return
        self._provider = getattr(model, "name", "local")
        logger.info("이미지 모델 준비 완료: %s (%s)", self.backend, self._provider)

    def generate(self, spec: GenerationSpec) -> GenerationOutput:
        from just_make_it.core import (
            ImageGenerationError,
            TextGenerationError,
            generate_ad_image,
        )

        if not self.is_ready:
            raise GeneratorError(f"{self.name} 준비 안 됨: {self._load_error}")

        try:
            result = generate_ad_image(
                product_name=spec.product_name,
                message=spec.message,
                purpose=spec.purpose,
                style=spec.style,
                generation_mode=TEXT_FREE_MODE,
                backend=self.backend,
                reference_image=spec.reference_image,
                adjustments=spec.adjustments,
            )
        except ValueError as exc:
            # 입력 오류는 다시 시도하거나 다른 모델로 넘겨도 같은 결과
            raise GeneratorError(str(exc), retryable=False) from exc
        except (ImageGenerationError, TextGenerationError) as exc:
            raise GeneratorError(str(exc)) from exc
        except Exception as exc:  # 예상 못 한 오류도 큐 워커가 죽지 않게 감싼다
            raise GeneratorError(f"{type(exc).__name__}: {exc}") from exc

        return GenerationOutput(
            image_bytes=result.image_bytes,
            message=result.message,
            model=result.model,
            width=result.width,
            height=result.height,
            prompt=result.prompt,
        )
