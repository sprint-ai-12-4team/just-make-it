"""11-09 요청 M1의 서빙 몫: 서버 시작 때 core 웜업(pipeline.warmup)을 부르는 연결.

웜업 함수 자체는 모델 쪽(tests/test_warmup.py)이라 여기서는 가짜로 바꿔 부르는지만 본다.
실행: uv run pytest tests/test_serving_warmup.py
"""

import threading
import time

from test_serving import (  # noqa: F401 (isolate_env는 fixture)
    BASE_BODY,
    isolate_env,
    make_client,
)

from just_make_it.core import pipeline
from just_make_it.serving.generators import MockGenerator
from just_make_it.serving.generators.core_adapter import CoreGenerator


# ---------------------------------------------------------------------- M1 serving warmup
class WarmMock(MockGenerator):
    """웜업을 기록하는 가짜 기본 생성기. 웜업과 생성이 같은 잠금을 씀 (klein처럼)."""

    def __init__(self, warm_seconds=0.0, fail=False):
        super().__init__(0.01)
        self.warm_seconds = warm_seconds
        self.fail = fail
        self.lock = threading.Lock()
        self.events: list[str] = []

    @property
    def source(self):
        return "local"

    def warmup(self):
        with self.lock:
            self.events.append("warmup-start")
            time.sleep(self.warm_seconds)
            if self.fail:
                raise RuntimeError("GPU 메모리 부족")
            self.events.append("warmup-end")
        return self.warm_seconds

    def generate(self, spec):
        with self.lock:
            self.events.append("generate")
            return super().generate(spec)


def test_warmup_runs_on_start_and_shows_in_health(tmp_path):
    primary = WarmMock(0.05)
    with make_client(tmp_path, primary=primary, warmup_on_start=True) as client:
        health = client.get("/health").json()
        client.post("/generate", json=BASE_BODY)
        manager = client.app.state.manager
    assert health["warmup"] == "done" and health["warmup_seconds"] == 0.05
    assert primary.events[:2] == ["warmup-start", "warmup-end"]
    assert "primary" in manager.speeds._warmed  # 웜업했으니 첫 호출도 평균에 넣음


def test_request_during_warmup_waits_and_stays_local(tmp_path):
    primary = WarmMock(0.6)
    fallback = MockGenerator(0.01, name="fallback")
    with make_client(
        tmp_path,
        primary=primary,
        fallback=fallback,
        warmup_on_start=True,
        load_models_in_background=True,
    ) as client:
        for _ in range(50):  # 웜업이 시작될 때까지
            if client.app.state.manager.warmup_state == "running":
                break
            time.sleep(0.01)
        assert client.get("/health").json()["warmup"] == "running"
        res = client.post("/generate", json=BASE_BODY)
        assert res.status_code == 200, res.text
    assert res.json()["source"] == "local"  # OpenAI로 넘기지 않음
    assert primary.events == ["warmup-start", "warmup-end", "generate"]


def test_warmup_failure_keeps_server_working(tmp_path):
    primary = WarmMock(fail=True)
    with make_client(tmp_path, primary=primary, warmup_on_start=True) as client:
        health = client.get("/health").json()
        res = client.post("/generate", json=BASE_BODY)
    assert health["warmup"] == "failed" and health["status"] == "ok"
    assert res.status_code == 200


def test_warmup_skipped_for_mock_and_off_by_setting(tmp_path):
    with make_client(tmp_path / "a", warmup_on_start=True) as client:  # 기본 mock
        assert client.get("/health").json()["warmup"] == "skipped"
    with make_client(tmp_path / "b", warmup_on_start=False) as client:
        assert client.get("/health").json()["warmup"] == "off"


# ---------------------------------------------------------------------- core 연결
def ready_core():
    generator = CoreGenerator(image_quality="fast")
    generator._ready = True  # klein을 실제로 불러오지 않고 준비된 것으로
    return generator


def test_core_adapter_skips_when_core_has_no_warmup(monkeypatch):
    monkeypatch.delattr(pipeline, "warmup", raising=False)
    assert ready_core().warmup() is None


def test_core_adapter_returns_core_warmup_seconds(monkeypatch):
    calls = []

    def warm():
        calls.append("warm")
        return 7.5

    monkeypatch.setattr(pipeline, "warmup", warm, raising=False)
    assert ready_core().warmup() == 7.5 and calls == ["warm"]
    # core가 건너뛰거나 실패하면 None (예외 없음) → skipped
    monkeypatch.setattr(pipeline, "warmup", lambda: None, raising=False)
    assert ready_core().warmup() is None


def test_core_adapter_never_warms_openai_route(monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "warmup", lambda: calls.append("warm"), raising=False)
    detailed = CoreGenerator(image_quality="detailed")
    detailed._ready = True
    assert detailed.warmup() is None and calls == []
