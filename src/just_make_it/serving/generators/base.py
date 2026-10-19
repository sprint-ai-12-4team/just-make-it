"""서빙이 쓰는 생성기 공통 인터페이스.

서빙은 어떤 생성기가 꽂혀 있든 `generate(spec) -> GenerationOutput` 하나만 호출한다.
생성 호출은 블로킹 함수이며, 큐 매니저가 별도 스레드에서 실행한다.
"""

from abc import ABC, abstractmethod

from ..schemas import GenerationOutput, GenerationSource, GenerationSpec


class GeneratorError(RuntimeError):
    """생성 실패. 메시지는 로그용이며 유저에게 그대로 노출하지 않는다.

    Args:
        message: 로그용 메시지.
        retryable: False면 재시도·Fallback해도 소용없는 오류 (입력 오류 등).
    """

    def __init__(self, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class ImageGenerator(ABC):
    #: 로그·헬스체크용 이름
    name: str

    @property
    def source(self) -> GenerationSource:
        """실제로 이미지를 만드는 곳 (응답의 generation_source)."""
        return "local"

    def load(self) -> None:  # noqa: B027 - 선택 구현 훅
        """무거운 준비 작업. 서버 시작 시 한 번 호출된다 (기본은 할 일 없음)."""

    @property
    def is_ready(self) -> bool:
        return True

    @abstractmethod
    def generate(self, spec: GenerationSpec) -> GenerationOutput:
        """spec에 맞는 이미지를 만든다. 실패 시 GeneratorError."""
