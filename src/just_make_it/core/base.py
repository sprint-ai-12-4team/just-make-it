"""모델들이 돌려주는 결과 형식과 에러."""

from dataclasses import dataclass


class ImageGenerationError(Exception):
    """이미지 생성 실패. 파이프라인이 이 에러를 보고 flare로 폴백합니다."""


class TextGenerationError(Exception):
    """광고 문구 생성 실패."""


@dataclass
class ImageResult:
    """이미지 모델 한 번 호출 결과.

    Args:
        image_bytes: PNG 이미지 바이트
        model: 실제 사용한 모델 이름
        elapsed_sec: 생성에 걸린 시간(초)
        cost_usd: 예상 비용(달러). 로컬 모델은 0
        seed: 실제로 쓴 시드 (klein만, flare는 None)
    """

    image_bytes: bytes
    model: str
    elapsed_sec: float
    cost_usd: float = 0.0
    seed: int | None = None


@dataclass
class TextResult:
    """텍스트 모델 한 번 호출 결과.

    Args:
        text: 생성된 글
        model: 실제 사용한 모델 이름
        elapsed_sec: 생성에 걸린 시간(초)
        cost_usd: 예상 비용(달러). 로컬 모델은 0
    """

    text: str
    model: str
    elapsed_sec: float
    cost_usd: float = 0.0
