"""API 키·GPU 없이 개발하기 위한 더미 생성기."""

import hashlib
import io
import time

from PIL import Image, ImageDraw

from just_make_it.core.prompt_builder import get_image_size

from ..schemas import GenerationOutput, GenerationSource, GenerationSpec
from .base import GeneratorError, ImageGenerator


class MockGenerator(ImageGenerator):
    """잠깐 기다린 뒤 목적별 크기의 그라데이션 PNG를 돌려준다.

    Args:
        delay_seconds: 생성 시간 흉내 (실제처럼 대기열이 생기게 함).
        fail_times: 앞의 N번 호출을 일부러 실패시킨다 (재시도·Fallback 테스트용).
        name: 로그·헬스체크·응답 model 값.
    """

    def __init__(
        self, delay_seconds: float = 2.0, fail_times: int = 0, name: str = "mock"
    ) -> None:
        self.delay_seconds = delay_seconds
        self.fail_times = fail_times
        self.name = name
        self.calls = 0

    @property
    def source(self) -> GenerationSource:
        return "mock"

    def generate(self, spec: GenerationSpec) -> GenerationOutput:
        self.calls += 1
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        if self.calls <= self.fail_times:
            raise GeneratorError(f"mock failure #{self.calls}")

        width, height = get_image_size(spec.purpose)
        digest = hashlib.md5(f"{spec.product_name}{spec.message}".encode()).digest()
        top, bottom = digest[:3], bytes(255 - b // 2 for b in digest[3:6])

        image = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(image)
        for y in range(height):
            t = y / max(1, height - 1)
            color = tuple(
                int(a + (b - a) * t) for a, b in zip(top, bottom, strict=True)
            )
            draw.line([(0, y), (width, y)], fill=color)
        label = f"MOCK {width}x{height} [{spec.purpose}]"
        draw.rectangle([(20, 20), (40 + 8 * len(label), 56)], fill=(0, 0, 0))
        draw.text((30, 30), label, fill=(255, 255, 255))

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return GenerationOutput(
            image_bytes=buffer.getvalue(), message=spec.message, model=self.name
        )
