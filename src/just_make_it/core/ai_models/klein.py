"""기본 이미지 모델: FLUX.2 [klein] 4B. VM GPU에서 diffusers로 돌립니다.

torch, diffusers는 GPU 서버에만 설치되어 있을 수 있어서 이 파일 안에서만 불러옵니다.
"""

import gc
import io
import random
import threading
import time

from PIL import Image, ImageOps

from just_make_it import config
from just_make_it.core.base import ImageGenerationError, ImageResult

STEPS = 4
GUIDANCE = 1.0


class KleinImageModel:
    """FLUX.2 [klein] 4B. 참고 사진 기능을 지원합니다."""

    def __init__(self, repo=config.KLEIN_MODEL, cpu_offload=config.KLEIN_CPU_OFFLOAD):
        """모델을 내려받아 GPU에 올립니다.

        Args:
            repo: Hugging Face 모델 저장소
            cpu_offload: True면 GPU 메모리를 아끼는 대신 느려짐

        Raises:
            ImageGenerationError: GPU가 없거나 모델을 불러오지 못했을 때
        """
        self.model = "FLUX.2 [klein] 4B"
        self.lock = threading.Lock()
        try:
            import torch
            from diffusers import Flux2KleinPipeline

            if not torch.cuda.is_available():
                raise RuntimeError("GPU를 찾을 수 없습니다.")
            self.torch = torch
            self.pipe = Flux2KleinPipeline.from_pretrained(
                repo, torch_dtype=torch.bfloat16
            )
            if cpu_offload:
                self.pipe.enable_model_cpu_offload()
            else:
                self.pipe.to("cuda")
        except Exception as e:
            raise ImageGenerationError(f"{self.model} 불러오기 실패: {e}") from e

    def generate(self, prompt, width, height, reference_image=None, seed=None):
        """프롬프트로 이미지를 만듭니다. 참고 사진이 있으면 사진 속 상품을 살려서 만듭니다.

        Args:
            prompt: 영어 이미지 프롬프트
            width: 가로 크기 (16의 배수로 맞춤)
            height: 세로 크기 (16의 배수로 맞춤)
            reference_image: 참고 사진 PNG 바이트. 없으면 None
            seed: 시드. 비우면 매번 랜덤

        Returns:
            ImageResult: 생성 결과

        Raises:
            ImageGenerationError: 생성 실패 (GPU 메모리 부족 등)
        """
        width, height = width // 16 * 16, height // 16 * 16
        extra = {}
        if reference_image is not None:
            reference = Image.open(io.BytesIO(reference_image)).convert("RGB")
            extra["image"] = [ImageOps.fit(reference, (width, height))]

        if seed is None:
            seed = random.randint(0, 2**32 - 1)
        start = time.perf_counter()
        try:
            with self.lock:
                image = self.pipe(
                    prompt=prompt,
                    width=width,
                    height=height,
                    num_inference_steps=STEPS,
                    guidance_scale=GUIDANCE,
                    generator=self.torch.Generator("cuda").manual_seed(seed),
                    **extra,
                ).images[0]
        except Exception as e:
            raise ImageGenerationError(f"{self.model} 이미지 생성 실패: {e}") from e

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return ImageResult(
            image_bytes=buffer.getvalue(),
            model=self.model,
            elapsed_sec=round(time.perf_counter() - start, 2),
            seed=seed,
        )

    def close(self):
        """GPU 메모리를 비웁니다."""
        del self.pipe
        gc.collect()
        self.torch.cuda.empty_cache()
