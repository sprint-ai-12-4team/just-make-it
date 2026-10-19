"""모든 이미지, 텍스트 모델이 따라야 하는 공통 규격.

모델마다 내부 동작은 달라도 입력과 출력을 똑같이 맞춰두면,
새 모델을 추가해도 pipeline.py나 서빙 코드를 고칠 필요가 없음.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ImageGenerationError(Exception):
    """이미지 생성 실패. 서빙 쪽에서 재시도나 다른 모델로 폴백할 때 이 예외로 판단."""


class TextGenerationError(Exception):
    """광고 문구 생성 실패."""


@dataclass
class ImageResult:
    """이미지 모델 공통 결과.

    Args:
        image_bytes: PNG 이미지 바이트
        model: 실제 사용한 모델 이름
        elapsed_sec: 생성에 걸린 시간
    """

    image_bytes: bytes
    model: str
    elapsed_sec: float


class BaseImageModel(ABC):
    """모든 이미지 생성 모델의 부모 클래스."""

    name = "base"

    @abstractmethod
    def generate(self, prompt, width, height, reference_image=None, **options):
        """프롬프트로 이미지를 생성합니다.

        Args:
            prompt: 이미지 프롬프트
            width: 원하는 가로 크기
            height: 원하는 세로 크기
            reference_image: 사용자가 올린 상품 사진 바이트. 없으면 None
            **options: 모델별 추가 옵션 (예: quality, steps)

        Returns:
            ImageResult: 생성 결과

        Raises:
            ImageGenerationError: 생성에 실패했을 때
        """


@dataclass
class TextResult:
    """텍스트 모델 공통 결과.

    Args:
        text: 생성된 글
        model: 실제 사용한 모델 이름
        elapsed_sec: 생성에 걸린 시간
    """

    text: str
    model: str
    elapsed_sec: float


class BaseTextModel(ABC):
    """모든 텍스트 생성 모델의 부모 클래스."""

    name = "base"

    @abstractmethod
    def generate(self, instructions, user_input, **options):
        """지시문과 입력으로 글을 생성합니다.

        Args:
            instructions: 모델이 지켜야 할 규칙
            user_input: 사용자 입력
            **options: 모델별 추가 옵션

        Returns:
            TextResult: 생성 결과

        Raises:
            TextGenerationError: 생성에 실패했을 때
        """
