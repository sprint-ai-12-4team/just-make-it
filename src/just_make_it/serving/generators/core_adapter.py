"""core 파이프라인 V1의 `generate_ad_image()`를 서빙 규격으로 감싸는 어댑터.

core가 품질 값에 맞는 모델을 고르고, 로컬 모델(klein·Gemma)이 실패하면 API 모델
(flare·luna)로 스스로 폴백한다. 서빙은 그 위에서 대기열·타임아웃·경로를 관리한다.

- 기본 경로: CoreGenerator("fast")     → 로컬 klein (VM GPU, 대기열 1개)
- 우회·선택: CoreGenerator("detailed") → OpenAI flare (대기열 없이 바로)

글자는 서버가 얹는다 (api_spec 5장, 10-22 결정). 단일 이미지는 output="combined"로 받아
글자 얹은 최종 이미지 + 글자 없는 원본 + text_layout을 함께 저장한다.
상세페이지 칸은 아직 프론트가 얹으므로 output="image"로 글자 없는 이미지만 받는다.

core의 함수 이름이나 인자가 바뀌면 이 파일만 고치면 된다.
"""

import logging

from ..schemas import GenerationOutput, GenerationSpec, Source
from .base import GeneratorError, ImageGenerator

logger = logging.getLogger(__name__)

# 품질 값 → 프론트 모델 이름 (DB·로그·/health에 남는 이름)
MODEL_NAMES = {"fast": "flux2-klein-4b", "detailed": "openai-image-2.5-flare"}


def _source_of(model: str) -> Source:
    """core가 돌려준 실제 모델 이름으로 이미지를 만든 곳을 판단한다."""
    from just_make_it import config

    return "openai" if model == config.FLARE_MODEL else "local"


class CoreGenerator(ImageGenerator):
    """core 파이프라인 V1을 정해진 그림 품질로 호출한다.

    Args:
        image_quality: fast(빠르게, klein) 또는 detailed(더 정교하게, flare)
    """

    def __init__(self, image_quality: str = "fast") -> None:
        if image_quality not in MODEL_NAMES:
            raise ValueError(
                f"image_quality는 {list(MODEL_NAMES)} 중 하나: {image_quality}"
            )
        self.image_quality = image_quality
        self.name = MODEL_NAMES[image_quality]
        self._ready = False
        self._load_error: str | None = None

    @property
    def source(self) -> Source:
        return "local" if self.image_quality == "fast" else "openai"

    @property
    def is_ready(self) -> bool:
        return self._ready

    def load(self) -> None:
        """모델을 미리 불러 둔다. klein은 GPU에 올리는 데 수십 초 이상 걸린다.

        실패하면 준비 안 됨 상태로 남고, 기본 경로 요청은 Fallback으로 넘어간다.
        (core가 요청마다 klein을 다시 불러오려고 시도하지 않게 하는 효과도 있다)
        """
        from just_make_it.core import ai_models

        try:
            if self.image_quality == "fast":
                ai_models.get_klein()
            else:
                ai_models.get_flare()
        except Exception as exc:
            self._load_error = str(exc)
            logger.warning("이미지 모델 준비 실패 (%s): %s", self.name, exc)
            return
        self._ready = True
        logger.info("이미지 모델 준비 완료: %s", self.name)

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
                output=spec.output,
                reference_image=spec.reference_image,
                adjustments=spec.adjustments,
                seed=spec.seed,
                image_quality=self.image_quality,
                text_quality=spec.text_quality,
            )
        except ValueError as exc:
            # 입력 오류는 다시 시도하거나 다른 모델로 넘겨도 같은 결과
            raise GeneratorError(str(exc), retryable=False) from exc
        except (ImageGenerationError, TextGenerationError) as exc:
            raise GeneratorError(str(exc)) from exc
        except Exception as exc:  # 예상 못 한 오류도 큐 워커가 죽지 않게 감싼다
            raise GeneratorError(f"{type(exc).__name__}: {exc}") from exc

        combined = spec.output == "combined"
        return GenerationOutput(
            image_bytes=result.image_bytes,
            background_bytes=result.background_bytes if combined else None,
            text_layout=dict(result.text_layout) if combined else None,
            message=result.message,
            model=result.image_model,
            width=result.width,
            height=result.height,
            prompt=result.prompt,
            source=_source_of(result.image_model),
            fallback_reason=result.image_fallback_reason,
            cost_usd=result.cost_usd,
            seed=result.seed,
            text_ms=int(round(result.text_sec * 1000)),
            image_ms=int(round(result.image_sec * 1000)),
            params={
                "image_quality": self.image_quality,
                "text_quality": spec.text_quality,
                "text_model": result.text_model,
                "text_fallback_reason": result.text_fallback_reason,
                "product_source": result.product_source,
                "used_reference": result.used_reference,
                "overlay_ms": int(round(result.overlay_sec * 1000)),
            },
        )
