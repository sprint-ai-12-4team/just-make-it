"""서빙 API 테스트. Mock 생성기와 core 가짜 모델을 써서 API 비용 없이 실행된다.

실행: uv run pytest tests/test_serving.py
"""

import io
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from just_make_it import config
from just_make_it.core import registry
from just_make_it.core.base import BaseImageModel, ImageResult
from just_make_it.serving.generators import (
    CoreGenerator,
    GeneratorError,
    MockGenerator,
)
from just_make_it.serving.main import create_app
from just_make_it.serving.schemas import GenerationSpec
from just_make_it.serving.settings import ServingSettings

BASE_BODY = {
    "purpose": "instagram",
    "product_name": "동네빵집",
    "message": "신메뉴 소금빵 출시",
    "style": "따뜻한",
    "generation_mode": "quick",
}


# ---------------------------------------------------------------------- 도우미
class RecordingMock(MockGenerator):
    """받은 spec을 기록하는 Mock."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.specs: list[GenerationSpec] = []

    def generate(self, spec):
        self.specs.append(spec)
        return super().generate(spec)


class InputErrorMock(MockGenerator):
    """입력 오류(재시도 불가)를 내는 Mock."""

    def generate(self, spec):
        self.calls += 1
        raise GeneratorError("bad input", retryable=False)


def png_bytes(size=(64, 64)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 100, 50)).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeCoreModel(BaseImageModel):
    """core registry에 끼워 넣는 가짜 이미지 모델 (실제 PNG를 돌려줌)."""

    name = "fake"
    calls: list[dict] = []

    def generate(self, prompt, width, height, reference_image=None, **options):
        FakeCoreModel.calls.append(
            {"prompt": prompt, "width": width, "height": height, "ref": reference_image}
        )
        return ImageResult(
            image_bytes=png_bytes((width, height)), model="fake-model", elapsed_sec=0.01
        )


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """개인 .env 값이 테스트에 섞이지 않게 서빙 설정 환경 변수를 비운다.

    core의 config.py가 import 시점에 .env를 os.environ에 올리기 때문에,
    ServingSettings(_env_file=None)만으로는 IMAGE_BACKEND 등이 그대로 읽힌다.
    """
    for name in ServingSettings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


@pytest.fixture
def fake_core(monkeypatch):
    FakeCoreModel.calls = []
    monkeypatch.setitem(registry.IMAGE_MODELS, "fake", FakeCoreModel)
    registry.clear_loaded_models()
    yield FakeCoreModel
    registry.clear_loaded_models()


def make_client(tmp_path, primary=None, fallback=None, premium=None, **overrides):
    settings = ServingSettings(
        _env_file=None,
        result_dir=tmp_path,
        public_base_url="http://testserver",
        generate_wait_seconds=5.0,
        **overrides,
    )
    primary = primary or MockGenerator(0.01)
    app = create_app(settings=settings, generators=(primary, fallback, premium))
    return TestClient(app)


def poll(client, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/jobs/{job_id}").json()
        if body["status"] != "processing":
            return body
        time.sleep(0.05)
    raise AssertionError("작업이 제한 시간 안에 끝나지 않았습니다.")


def fetch_image(client, url) -> Image.Image:
    res = client.get(url.replace("http://testserver", ""))
    assert res.status_code == 200
    return Image.open(io.BytesIO(res.content))


# ---------------------------------------------------------------------- 기본 흐름
def test_health(tmp_path):
    with make_client(tmp_path) as client:
        body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["queue_length"] == 0
    assert body["primary_ready"] is True


def test_generate_json_returns_success(tmp_path):
    with make_client(tmp_path) as client:
        res = client.post("/generate", json=BASE_BODY)
        assert res.status_code == 200
        body = res.json()
        image = fetch_image(client, body["image_url"])
    assert body["status"] == "success"
    assert body["route"] == "primary"
    assert body["generation_source"] == "mock"
    assert body["message"] == BASE_BODY["message"]
    assert image.size == (1024, 1024)  # core 기준 instagram 크기


def test_frontend_payload_with_extra_fields_is_accepted(tmp_path):
    # 프론트는 reference_image_url: null을 함께 보낸다
    with make_client(tmp_path) as client:
        res = client.post("/generate", json={**BASE_BODY, "reference_image_url": None})
    assert res.status_code == 200


def test_generate_without_waiting_then_poll(tmp_path):
    with make_client(tmp_path, primary=MockGenerator(0.3)) as client:
        res = client.post("/generate?wait=0", json=BASE_BODY)
        assert res.status_code == 202
        body = res.json()
        assert body["stage"] in ("queued", "running")
        final = poll(client, body["job_id"])
    assert final["status"] == "success"


def test_multipart_with_reference_and_adjustments(tmp_path):
    primary = RecordingMock(0.01)
    with make_client(tmp_path, primary=primary) as client:
        res = client.post(
            "/generate",
            data={**BASE_BODY, "adjustments": ["더 밝게", "배경 단순하게"]},
            files={"reference_image": ("bread.jpg", png_bytes(), "image/jpeg")},
        )
    assert res.status_code == 200, res.text
    spec = primary.specs[0]
    assert spec.reference_image.startswith(b"\x89PNG")  # PNG로 통일
    assert spec.adjustments == ["더 밝게", "배경 단순하게"]
    assert spec.product_name == "동네빵집"


def test_multipart_adjustments_as_json_string(tmp_path):
    primary = RecordingMock(0.01)
    with make_client(tmp_path, primary=primary) as client:
        client.post("/generate", data={**BASE_BODY, "adjustments": '["텍스트 짧게"]'})
    assert primary.specs[0].adjustments == ["텍스트 짧게"]


# ---------------------------------------------------------------------- 입력 검증
@pytest.mark.parametrize(
    "body",
    [
        {**BASE_BODY, "message": "   "},
        {**BASE_BODY, "purpose": "tiktok"},
        {k: v for k, v in BASE_BODY.items() if k != "product_name"},
        {**BASE_BODY, "message": "가" * 201},
        {**BASE_BODY, "generation_mode": "auto"},
    ],
)
def test_invalid_input_returns_422(tmp_path, body):
    with make_client(tmp_path) as client:
        res = client.post("/generate", json=body)
    assert res.status_code == 422
    assert "detail" in res.json()


def test_non_image_upload_rejected(tmp_path):
    with make_client(tmp_path) as client:
        res = client.post(
            "/generate",
            data=BASE_BODY,
            files={"reference_image": ("note.txt", b"hello", "text/plain")},
        )
    assert res.status_code == 422


def test_unknown_job_returns_404(tmp_path):
    with make_client(tmp_path) as client:
        assert client.get("/jobs/nope").status_code == 404


# ---------------------------------------------------------------------- 재시도·실패
def test_retry_then_success_on_primary(tmp_path):
    primary = MockGenerator(0.01, fail_times=1)
    with make_client(tmp_path, primary=primary, retry_count=1) as client:
        body = client.post("/generate", json=BASE_BODY).json()
    assert body["status"] == "success"
    assert body["route"] == "primary"
    assert primary.calls == 2


def test_input_error_is_not_retried_or_fallen_back(tmp_path):
    primary = InputErrorMock(0)
    fallback = RecordingMock(0.01, name="fb")
    with make_client(tmp_path, primary=primary, fallback=fallback) as client:
        res = client.post("/generate", json=BASE_BODY)
    assert res.status_code == 502
    assert "입력" in res.json()["error"]
    assert primary.calls == 1
    assert fallback.specs == []


# ---------------------------------------------------------------------- Fallback
def test_queue_wait_triggers_fallback(tmp_path):
    with make_client(
        tmp_path,
        primary=MockGenerator(0.5),
        fallback=MockGenerator(0.01, name="fb"),
        seconds_per_job_init=10.0,
        max_wait_seconds=15.0,
    ) as client:
        first = client.post("/generate?wait=0", json=BASE_BODY).json()
        second = client.post("/generate?wait=0", json=BASE_BODY).json()
        assert poll(client, first["job_id"])["route"] == "primary"
        assert poll(client, second["job_id"])["route"] == "fallback"


def test_primary_failure_falls_back_after_retry(tmp_path):
    primary = MockGenerator(0.01, fail_times=99)
    with make_client(
        tmp_path,
        primary=primary,
        fallback=MockGenerator(0.01, name="fb"),
        retry_count=1,
    ) as client:
        body = client.post("/generate", json=BASE_BODY).json()
    assert body["status"] == "success"
    assert body["route"] == "fallback"
    assert body["model"] == "fb"
    assert primary.calls == 2


def test_no_fallback_configured_fails_cleanly(tmp_path):
    with make_client(
        tmp_path, primary=MockGenerator(0.01, fail_times=99), retry_count=0
    ) as client:
        res = client.post("/generate", json=BASE_BODY)
    assert res.status_code == 502
    assert res.json()["status"] == "failed"


def test_extra_daily_limit_stops_fallback(tmp_path):
    with make_client(
        tmp_path,
        primary=MockGenerator(0.01, fail_times=99),
        fallback=MockGenerator(0.01, name="fb"),
        retry_count=0,
        extra_daily_limit=1,
    ) as client:
        first = client.post("/generate", json=BASE_BODY)
        second = client.post("/generate", json=BASE_BODY)
        health = client.get("/health").json()
    assert first.json()["route"] == "fallback"
    assert second.status_code == 502
    assert health["extra_calls_today"] == 1


def test_daily_job_limit_returns_429(tmp_path):
    with make_client(tmp_path, daily_job_limit=1) as client:
        assert client.post("/generate", json=BASE_BODY).status_code == 200
        assert client.post("/generate", json=BASE_BODY).status_code == 429


def test_premium_route(tmp_path):
    premium = RecordingMock(0.01, name="premium")
    with make_client(tmp_path, premium=premium) as client:
        body = client.post("/generate", json={**BASE_BODY, "premium": True}).json()
    assert body["route"] == "premium"
    assert len(premium.specs) == 1


def test_premium_without_premium_model_uses_primary(tmp_path):
    with make_client(tmp_path) as client:
        body = client.post("/generate", json={**BASE_BODY, "premium": True}).json()
    assert body["route"] == "primary"


def test_primary_concurrency_runs_jobs_in_parallel(tmp_path):
    with make_client(
        tmp_path, primary=MockGenerator(0.5), primary_concurrency=2
    ) as client:
        started = time.monotonic()
        ids = [
            client.post("/generate?wait=0", json=BASE_BODY).json()["job_id"]
            for _ in range(2)
        ]
        for job_id in ids:
            poll(client, job_id)
        elapsed = time.monotonic() - started
    assert elapsed < 0.9  # 순서대로였다면 1초 이상


# ---------------------------------------------------------------------- core 연동
def test_core_generator_end_to_end(tmp_path, fake_core):
    with make_client(tmp_path, primary=CoreGenerator("fake")) as client:
        res = client.post(
            "/generate",
            data={**BASE_BODY, "purpose": "youtube", "adjustments": "더 밝게"},
            files={"reference_image": ("p.png", png_bytes(), "image/png")},
        )
        body = res.json()
        image = fetch_image(client, body["image_url"])
    assert res.status_code == 200, res.text
    assert body["model"] == "fake-model"
    assert body["generation_source"] == "local"
    call = fake_core.calls[0]
    assert (call["width"], call["height"]) == (1536, 864)
    assert call["ref"] is not None
    assert "brighter" in call["prompt"]  # core가 수정 칩을 프롬프트에 반영
    assert image.size == (1536, 864)


def test_core_input_error_is_not_retryable(fake_core):
    generator = CoreGenerator("fake")
    generator.load()
    with pytest.raises(GeneratorError) as info:
        generator.generate(GenerationSpec(product_name="  ", message="신메뉴"))
    assert info.value.retryable is False


def test_unknown_core_model_is_not_ready_and_falls_back(tmp_path):
    with make_client(
        tmp_path,
        primary=CoreGenerator("no-such-model"),
        fallback=MockGenerator(0.01, name="fb"),
    ) as client:
        health = client.get("/health").json()
        body = client.post("/generate", json=BASE_BODY).json()
    assert health["status"] == "degraded"
    assert body["route"] == "fallback"


def test_app_starts_without_api_key(tmp_path, monkeypatch):
    # 배포 환경에서 키가 빠져도 서버는 떠야 한다 (헬스체크로 원인 확인)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    registry.clear_loaded_models()
    settings = ServingSettings(_env_file=None, result_dir=tmp_path)
    with TestClient(create_app(settings=settings)) as client:
        health = client.get("/health").json()
        res = client.post("/generate", json=BASE_BODY)
    registry.clear_loaded_models()
    assert health["status"] == "degraded"
    assert health["primary_ready"] is False
    assert res.status_code == 502
