"""작업 제한 시간과 취소 신호. 서빙이 정하고, 모델 호출이 지킵니다.

서빙은 생성 1건에 제한 시간을 두는데, 파이썬은 실행 중인 스레드를 밖에서 멈출 수 없습니다.
그래서 서빙이 제한 시간을 넘겨 포기한 뒤에도 OpenAI 호출(기본 대기 600초, 재시도 2번)이나
klein 생성이 뒤에서 끝까지 돌아 비용과 GPU를 씁니다.

이 모듈은 서빙이 작업마다 `Deadline`을 걸어 두면, 모델이 그 안에서만 일하게 합니다.
- OpenAI(luna·flare): 남은 시간을 요청 timeout으로 쓰고 재시도하지 않음
- Gemma(Ollama): 남은 시간을 HTTP timeout으로 씀
- klein: 매 단계(step)마다 확인해서 시간이 다 됐거나 취소됐으면 바로 멈춤
- 남은 시간이 없으면 호출 자체를 하지 않음 (폴백 모델도 마찬가지)

서빙이 Deadline을 걸지 않았으면(스크립트·테스트) 아무것도 바뀌지 않습니다.

사용 (서빙):
    token = Deadline(90)
    with use_deadline(token):      # 생성을 돌리는 스레드 안에서
        generate_ad_image(...)
    token.cancel()                 # 다른 곳에서 포기했을 때 (klein이 다음 단계에서 멈춤)
"""

import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar


class DeadlineExceeded(Exception):
    """제한 시간이 지났거나 서빙이 작업을 취소했을 때."""


class Deadline:
    """작업 1건의 제한 시간과 취소 신호. 여러 스레드에서 같이 봐도 안전합니다.

    Args:
        seconds: 지금부터 쓸 수 있는 시간(초)
    """

    def __init__(self, seconds: float) -> None:
        self.expires_at = time.monotonic() + seconds
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def remaining(self) -> float:
        """남은 시간(초). 취소됐으면 0."""
        if self.cancelled:
            return 0.0
        return max(0.0, self.expires_at - time.monotonic())

    def check(self, what: str = "작업") -> None:
        """시간이 다 됐거나 취소됐으면 DeadlineExceeded."""
        if self.cancelled:
            raise DeadlineExceeded(f"{what} 취소됨 (서빙이 포기함)")
        if self.remaining() <= 0:
            raise DeadlineExceeded(f"{what} 제한 시간 초과")


_current: ContextVar[Deadline | None] = ContextVar(
    "just_make_it_deadline", default=None
)


@contextmanager
def use_deadline(deadline: Deadline | None):
    """이 블록 안의 모델 호출이 deadline을 지키게 합니다 (None이면 제한 없음)."""
    reset = _current.set(deadline)
    try:
        yield deadline
    finally:
        _current.reset(reset)


def current() -> Deadline | None:
    """지금 걸려 있는 Deadline. 없으면 None."""
    return _current.get()


def timeout_for(default: float, what: str = "작업") -> float:
    """한 번의 외부 호출에 줄 timeout(초): 원래 값과 남은 시간 중 짧은 쪽.

    Raises:
        DeadlineExceeded: 이미 시간이 다 됐거나 취소됐을 때 (호출하지 말 것)
    """
    deadline = current()
    if deadline is None:
        return default
    deadline.check(what)
    return min(default, deadline.remaining())


def check(what: str = "작업") -> None:
    """Deadline이 걸려 있으면 확인합니다. 없으면 아무것도 하지 않습니다."""
    deadline = current()
    if deadline is not None:
        deadline.check(what)


def openai_client(client, what: str = "OpenAI"):
    """Deadline이 걸려 있으면 남은 시간만 기다리고 재시도하지 않는 OpenAI 클라이언트.

    OpenAI SDK 기본값은 응답을 600초까지 기다리고 실패하면 2번 다시 시도해서,
    서빙이 포기한 뒤에도 몇 분씩 호출이 이어지고 비용이 나갑니다.

    Raises:
        DeadlineExceeded: 이미 시간이 다 됐거나 취소됐을 때
    """
    if current() is None:
        return client
    return client.with_options(timeout=timeout_for(600.0, what), max_retries=0)


def step_callback(what: str = "이미지 생성"):
    """diffusers `callback_on_step_end`용 함수. Deadline이 없으면 None.

    매 단계 끝에 확인해서 시간이 다 됐거나 취소됐으면 예외로 생성을 멈춥니다 (GPU를 바로 놓아줌).
    """
    deadline = current()
    if deadline is None:
        return None

    def callback(pipe, step, timestep, callback_kwargs):
        deadline.check(what)
        return callback_kwargs

    return callback
