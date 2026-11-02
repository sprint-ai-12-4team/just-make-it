"""제한 시간이 지나면 core 작업도 실제로 멈추는지 (core/deadline.py + 서빙 연결).

예전에는 서빙이 503을 준 뒤에도 OpenAI 호출(기본 600초 대기, 재시도 2번)과 klein 생성이
뒤에서 끝까지 돌았다. GPU·API 키 없이 가짜 모델로 확인한다.
실행: uv run pytest tests/test_deadline.py
"""

import threading
import time
from types import SimpleNamespace

import pytest
from PIL import Image
from test_serving import (  # noqa: F401 (isolate_env는 fixture)
    BASE_BODY,
    FakeCopyWriter,
    db_rows,
    isolate_env,
    make_client,
)

from just_make_it import config
from just_make_it.core import ai_models, deadline
from just_make_it.core.ai_models.flare import FlareImageModel
from just_make_it.core.ai_models.gemma import GemmaTextModel
from just_make_it.core.ai_models.klein import KleinImageModel
from just_make_it.core.ai_models.luna import LunaTextModel
from just_make_it.core.base import ImageGenerationError, TextGenerationError
from just_make_it.core.deadline import Deadline, use_deadline
from just_make_it.serving.generators import GeneratorError, MockGenerator


# ---------------------------------------------------------------------- 가짜 모델
class FakeOpenAI:
    """OpenAI 클라이언트 자리. with_options로 받은 timeout·재시도 값을 기록한다."""

    def __init__(self, options=None, log=None):
        self.options = options or {}
        self.log = log if log is not None else []
        self.images = SimpleNamespace(generate=self._image, edit=self._image)
        self.responses = SimpleNamespace(create=self._text)

    def with_options(self, **options):
        return FakeOpenAI(options, self.log)

    def _image(self, **request):
        self.log.append(self.options)
        data = SimpleNamespace(b64_json="aGk=")  # "hi"
        return SimpleNamespace(data=[data], usage=None)

    def _text(self, **request):
        self.log.append(self.options)
        return SimpleNamespace(output_text="문구", usage=None)


def flare_with(client) -> FlareImageModel:
    model = object.__new__(FlareImageModel)
    model.model, model.quality, model.client = "flare", "low", client
    return model


def luna_with(client) -> LunaTextModel:
    model = object.__new__(LunaTextModel)
    model.model, model.client = "luna", client
    return model


class SlowPipe:
    """diffusers 파이프라인 자리. 단계마다 callback_on_step_end를 부른다."""

    def __init__(self, steps=200, step_seconds=0.01):
        self.steps, self.step_seconds = steps, step_seconds
        self.done_steps = 0
        self.kwargs = {}

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        callback = kwargs.get("callback_on_step_end")
        for step in range(self.steps):
            time.sleep(self.step_seconds)
            self.done_steps = step + 1
            if callback:
                callback(self, step, None, {})
        return SimpleNamespace(images=[Image.new("RGB", (16, 16))])


def klein_with(pipe) -> KleinImageModel:
    model = object.__new__(KleinImageModel)
    model.model, model.pipe, model.lock = "klein", pipe, threading.Lock()
    generator = SimpleNamespace(manual_seed=lambda seed: None)
    model.torch = SimpleNamespace(
        Generator=lambda device: generator,
        cuda=SimpleNamespace(empty_cache=lambda: None),
    )
    return model


# ---------------------------------------------------------------------- core
def test_without_deadline_models_keep_default_client():
    # 스크립트·평가처럼 서빙 밖에서 부르면 예전과 똑같이 동작한다
    client = FakeOpenAI()
    flare_with(client).generate("a cake", 64, 64)
    luna_with(client).generate("규칙", "입력")
    assert client.log == [{}, {}]


def test_openai_calls_use_remaining_time_and_no_retries():
    client = FakeOpenAI()
    with use_deadline(Deadline(30)):
        flare_with(client).generate("a cake", 64, 64)
        luna_with(client).generate("규칙", "입력")
    for options in client.log:
        assert options["max_retries"] == 0
        assert 29 < options["timeout"] <= 30


@pytest.mark.parametrize("make", [flare_with, luna_with])
def test_no_openai_call_after_deadline(make):
    client = FakeOpenAI()
    token = Deadline(30)
    token.cancel()
    with (
        use_deadline(token),
        pytest.raises((ImageGenerationError, TextGenerationError)),
    ):
        model = make(client)
        if isinstance(model, FlareImageModel):
            model.generate("a cake", 64, 64)
        else:
            model.generate("규칙", "입력")
    assert client.log == []  # 비용이 드는 호출 자체를 하지 않음


def test_gemma_waits_only_for_remaining_time(monkeypatch):
    seen = {}

    def fake_post(url, json, timeout):
        seen["timeout"] = timeout
        return SimpleNamespace(
            status_code=200,
            text="",
            raise_for_status=lambda: None,
            json=lambda: {"message": {"content": "문구"}},
        )

    monkeypatch.setattr("just_make_it.core.ai_models.gemma.requests.post", fake_post)
    gemma = GemmaTextModel(timeout=120)
    gemma.generate("규칙", "입력")
    assert seen["timeout"] == 120  # Deadline 없으면 원래 값
    with use_deadline(Deadline(10)):
        gemma.generate("규칙", "입력")
    assert 9 < seen["timeout"] <= 10


def test_gemma_skips_call_after_deadline(monkeypatch):
    monkeypatch.setattr(
        "just_make_it.core.ai_models.gemma.requests.post",
        lambda *a, **k: pytest.fail("시간이 지났는데 Ollama를 불렀다"),
    )
    token = Deadline(10)
    token.cancel()
    with use_deadline(token), pytest.raises(TextGenerationError):
        GemmaTextModel().generate("규칙", "입력")


def test_klein_stops_at_next_step_when_cancelled():
    pipe = SlowPipe(steps=200, step_seconds=0.01)  # 끝까지 돌면 2초
    token = Deadline(30)
    threading.Timer(0.1, token.cancel).start()
    started = time.monotonic()
    with use_deadline(token), pytest.raises(ImageGenerationError):
        klein_with(pipe).generate("a cake", 64, 64)
    assert time.monotonic() - started < 0.5
    assert pipe.done_steps < 50  # GPU 작업이 실제로 중간에 멈춤


def test_klein_without_deadline_gets_no_callback():
    pipe = SlowPipe(steps=3, step_seconds=0)
    klein_with(pipe).generate("a cake", 64, 64)
    assert "callback_on_step_end" not in pipe.kwargs


def test_core_does_not_fall_back_after_cancel(monkeypatch):
    # klein이 취소로 멈추면 core 안의 flare 폴백도 새로 시작하지 않는다 (비용 없음)
    from just_make_it.core import generate_ad_image

    client = FakeOpenAI()
    pipe = SlowPipe(steps=200, step_seconds=0.01)
    gemma = SimpleNamespace(
        generate=lambda *a, **k: SimpleNamespace(
            text="PRODUCT: a cake\nSCENE: a table", model="gemma", cost_usd=0.0
        )
    )
    monkeypatch.setattr(ai_models, "get_gemma", lambda: gemma)
    monkeypatch.setattr(ai_models, "get_klein", lambda: klein_with(pipe))
    monkeypatch.setattr(ai_models, "get_flare", lambda: flare_with(client))
    monkeypatch.setattr(config, "USE_FALLBACK", True)
    token = Deadline(30)
    threading.Timer(0.1, token.cancel).start()
    with use_deadline(token), pytest.raises(ImageGenerationError):
        generate_ad_image("케이크", "신메뉴", output="image")
    assert client.log == []


def test_deadline_helpers_without_deadline():
    assert deadline.current() is None
    assert deadline.timeout_for(120) == 120
    deadline.check()  # 아무 일 없음
    assert deadline.step_callback() is None


# ---------------------------------------------------------------------- 서빙
class CooperativeMock(MockGenerator):
    """core 모델처럼 Deadline을 확인하며 오래 도는 생성기. 언제 멈췄는지 기록한다."""

    def __init__(self, seconds=3.0):
        super().__init__(0.0)
        self.seconds = seconds
        self.stopped_after: list[float] = []
        self.started = threading.Event()

    def generate(self, spec):
        self.calls += 1
        self.started.set()
        start = time.monotonic()
        try:
            while time.monotonic() - start < self.seconds:
                deadline.check("mock")
                time.sleep(0.01)
        except deadline.DeadlineExceeded as exc:
            self.stopped_after.append(time.monotonic() - start)
            raise GeneratorError(str(exc)) from exc
        self.stopped_after.append(time.monotonic() - start)
        return super().generate(spec)


def wait_until(predicate, timeout=3.0):
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end
        time.sleep(0.01)


def test_generation_timeout_stops_core_work(tmp_path):
    primary = CooperativeMock(seconds=3.0)
    with make_client(
        tmp_path, primary=primary, generation_timeout_seconds=0.3, retry_count=1
    ) as client:
        res = client.post("/generate", json=BASE_BODY)
        wait_until(lambda: primary.stopped_after)
    assert res.status_code == 503
    assert primary.stopped_after[0] < 1.0  # 3초를 다 돌지 않고 멈춤
    assert primary.calls == 1  # 시간 초과는 재시도하지 않음


def test_generate_wait_timeout_cancels_running_job(tmp_path):
    primary = CooperativeMock(seconds=3.0)
    with make_client(tmp_path, primary=primary, generate_wait_seconds=0.3) as client:
        res = client.post("/generate", json=BASE_BODY)
        wait_until(lambda: primary.stopped_after)
        time.sleep(0.1)
        row = db_rows(tmp_path)[0]
    assert res.status_code == 503
    assert primary.stopped_after[0] < 1.0
    assert primary.calls == 1  # 취소된 작업은 다시 시도하지 않음
    assert row["status"] == "error" and "cancelled" in row["error"]


def test_generate_wait_timeout_skips_queued_job(tmp_path):
    # 앞 작업이 GPU를 쓰는 동안 기다리던 작업은 포기하면 아예 실행하지 않는다
    class StubbornFirst(CooperativeMock):
        """첫 호출은 취소 신호를 보지 않고 1초 동안 GPU를 붙잡는다."""

        def generate(self, spec):
            if not self.started.is_set():
                self.started.set()
                time.sleep(1.0)
                return MockGenerator.generate(self, spec)  # calls += 1
            return super().generate(spec)

    primary = StubbornFirst()
    with make_client(tmp_path, primary=primary, generate_wait_seconds=0.3) as client:
        first = threading.Thread(
            target=lambda: client.post("/generate", json=BASE_BODY)
        )
        first.start()
        primary.started.wait(2)
        second = client.post("/generate", json=BASE_BODY)
        first.join()
        time.sleep(1.2)  # 첫 작업이 끝나고 워커가 다음 작업을 꺼낼 시간
        rows = db_rows(tmp_path)
    assert second.status_code == 503
    assert primary.calls == 1  # 두 번째 작업은 생성기를 부르지 않음
    assert rows[1]["status"] == "error" and "cancelled" in rows[1]["error"]


def test_copies_timeout_stops_text_model(tmp_path):
    stopped = []

    class CooperativeWriter(FakeCopyWriter):
        def suggest(self, product_name, message, style, text_quality="basic"):
            start = time.monotonic()
            try:
                while time.monotonic() - start < 3:
                    deadline.check("copies")
                    time.sleep(0.01)
            except deadline.DeadlineExceeded as exc:
                stopped.append(time.monotonic() - start)
                raise GeneratorError(str(exc)) from exc
            return ["문구"]

    with make_client(
        tmp_path, copywriter=CooperativeWriter(), copy_timeout_seconds=0.2
    ) as client:
        res = client.post("/copies", json=BASE_BODY)
        wait_until(lambda: stopped)
    assert res.status_code == 503
    assert stopped[0] < 1.0


def test_configured_openai_cap_still_applies():
    # core 설정의 호출 상한(OPENAI_IMAGE_TIMEOUT 등)보다 오래 기다리지 않는다
    client = FakeOpenAI()
    client.timeout = 75.0
    with use_deadline(Deadline(300)):
        flare_with(client).generate("a cake", 64, 64)
    assert client.log[-1] == {"timeout": 75.0, "max_retries": 0}
