"""홍보 문구 추천 (POST /copies).

core의 `suggest_ad_copies()`를 감싸고, Mock 모드에서는 API 호출 없이 가짜 문구를 돌려준다.
"""

from abc import ABC, abstractmethod

from .generators import GeneratorError


class CopyInputError(ValueError):
    """입력이 비어 있는 등 다시 시도해도 소용없는 오류."""


class CopyWriter(ABC):
    @abstractmethod
    def suggest(self, product_name: str, message: str, style: str | None) -> list[str]:
        """문구 후보를 최대 3개 돌려준다. 실패 시 CopyInputError 또는 GeneratorError."""


class CoreCopyWriter(CopyWriter):
    def suggest(self, product_name: str, message: str, style: str | None) -> list[str]:
        from just_make_it.core import TextGenerationError, suggest_ad_copies

        try:
            return suggest_ad_copies(product_name, message, style=style, n=3)
        except ValueError as exc:
            raise CopyInputError(str(exc)) from exc
        except TextGenerationError as exc:
            raise GeneratorError(str(exc)) from exc
        except Exception as exc:  # API 키 누락 등도 503으로 처리
            raise GeneratorError(f"{type(exc).__name__}: {exc}") from exc


class MockCopyWriter(CopyWriter):
    def suggest(self, product_name: str, message: str, style: str | None) -> list[str]:
        return [
            f"{product_name}, {message}",
            f"지금 {product_name}에서 {message}",
            f"{message}! {product_name}에서 만나요",
        ]
