"""OpenAI 금액 회로차단기 테스트 (V2). 하루 cost_usd 합계가 상한을 넘으면 OpenAI를 막는다.

실행: uv run pytest tests/test_budget.py
"""

import pytest
from test_serving import (  # noqa: F401 (isolate_env는 fixture)
    BASE_BODY,
    FakeCopyWriter,
    isolate_env,
    make_client,
    route_of,
)

from just_make_it import config
from just_make_it.serving.generators import MockGenerator

DETAILED = {**BASE_BODY, "image_model": "openai-image-2.5-flare"}


class CostlyMock(MockGenerator):
    """OpenAI처럼 비용이 드는 가짜 생성기."""

    def __init__(self, cost, name="mock-premium"):
        super().__init__(0.0, name=name)
        self.cost = cost

    @property
    def source(self):
        return "openai"

    def generate(self, spec):
        output = super().generate(spec)
        output.cost_usd = self.cost
        output.source = "openai"
        return output


@pytest.fixture(autouse=True)
def restore_core_fallback(monkeypatch):
    # 회로가 열리면 core 폴백 설정(프로세스 전체 값)을 끄므로 테스트 뒤 되돌린다
    monkeypatch.setattr(config, "USE_FALLBACK", True)


def test_premium_goes_local_after_budget(tmp_path):
    premium = CostlyMock(0.02)
    with make_client(tmp_path, premium=premium, openai_daily_budget_usd=0.03) as client:
        first = client.post("/generate", json=DETAILED).json()
        second = client.post("/generate", json=DETAILED).json()
        third = client.post("/generate", json=DETAILED).json()
        health = client.get("/health").json()
    assert route_of(tmp_path, first["id"]) == "premium"
    assert route_of(tmp_path, second["id"]) == "premium"  # 합계 0.04 → 여기서 넘음
    assert route_of(tmp_path, third["id"]) == "primary"  # 상한 이후 로컬로
    assert premium.calls == 2
    assert health["openai_blocked"] is True
    assert health["openai_cost_today_usd"] == pytest.approx(0.04)
    assert health["openai_daily_budget_usd"] == 0.03


def test_fallback_waits_instead_of_openai_after_budget(tmp_path):
    fallback = CostlyMock(0.05, name="fb")
    with make_client(
        tmp_path,
        primary=MockGenerator(0.05),
        fallback=fallback,
        premium=CostlyMock(0.05),
        openai_daily_budget_usd=0.01,
        seconds_per_job_init=60.0,
        max_wait_seconds=1.0,
    ) as client:
        client.post("/generate", json=DETAILED)  # 0.05 써서 상한 넘김
        bodies = [client.post("/generate", json=BASE_BODY).json() for _ in range(2)]
    assert fallback.calls == 0
    assert {route_of(tmp_path, b["id"]) for b in bodies} == {"primary"}


def test_budget_survives_restart(tmp_path):
    with make_client(
        tmp_path, premium=CostlyMock(0.05), openai_daily_budget_usd=0.01
    ) as client:
        client.post("/generate", json=DETAILED)
    with make_client(
        tmp_path, premium=CostlyMock(0.05), openai_daily_budget_usd=0.01
    ) as client:
        health = client.get("/health").json()
        body = client.post("/generate", json=DETAILED).json()
    assert health["openai_blocked"] is True
    assert route_of(tmp_path, body["id"]) == "primary"


def test_core_fallback_turns_off_while_blocked(tmp_path):
    with make_client(
        tmp_path, premium=CostlyMock(0.05), openai_daily_budget_usd=0.01
    ) as client:
        assert config.USE_FALLBACK is True
        client.post("/generate", json=DETAILED)
        assert config.USE_FALLBACK is False  # klein→flare, Gemma→luna도 막음


def test_natural_copies_use_gemma_while_blocked(tmp_path):
    writer = FakeCopyWriter()
    with make_client(
        tmp_path,
        premium=CostlyMock(0.05),
        copywriter=writer,
        openai_daily_budget_usd=0.01,
    ) as client:
        client.post("/copies", json={**BASE_BODY, "text_model": "openai-gpt-5.6-luna"})
        before = writer.text_quality
        client.post("/generate", json=DETAILED)
        client.post("/copies", json={**BASE_BODY, "text_model": "openai-gpt-5.6-luna"})
    assert before == "natural"
    assert writer.text_quality == "basic"


def test_zero_budget_means_no_limit(tmp_path):
    premium = CostlyMock(5.0)
    with make_client(tmp_path, premium=premium, openai_daily_budget_usd=0) as client:
        bodies = [client.post("/generate", json=DETAILED).json() for _ in range(2)]
        health = client.get("/health").json()
    assert {route_of(tmp_path, b["id"]) for b in bodies} == {"premium"}
    assert health["openai_blocked"] is False
