"""서빙 API 테스트. Mock 생성기와 core 가짜 모델을 써서 API 비용 없이 실행된다.

API 계약은 PM API 스펙(`docs/api_spec.md`)을 기준으로 검증한다.
실행: uv run pytest tests/test_serving.py
"""

import io
import json
import logging
import os
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from just_make_it import config
from just_make_it.core import registry
from just_make_it.core.base import BaseImageModel, ImageResult
from just_make_it.serving.copywriter import CopyInputError, CopyWriter
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


class FakeCopyWriter(CopyWriter):
    def __init__(self, result=None, error=None, delay=0.0):
        self.result = result or ["문구1", "문구2", "문구3", "문구4"]
        self.error = error
        self.delay = delay

    def suggest(self, product_name, message, style):
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.result


def png_bytes(size=(64, 64), fmt="PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 100, 50)).save(buffer, format=fmt)
    return buffer.getvalue()


def noise_png(size=(200, 200)) -> bytes:
    """압축이 잘 안 되는 이미지 (용량 제한 테스트용)."""
    buffer = io.BytesIO()
    Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3)).save(
        buffer, format="PNG"
    )
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


def make_client(
    tmp_path, primary=None, fallback=None, premium=None, copywriter=None, **overrides
):
    settings = ServingSettings(
        _env_file=None,
        result_dir=tmp_path,
        public_base_url="http://testserver",
        generate_wait_seconds=5.0,
        **overrides,
    )
    primary = primary or MockGenerator(0.01)
    app = create_app(
        settings=settings,
        generators=(primary, fallback, premium),
        copywriter=copywriter or FakeCopyWriter(),
    )
    return TestClient(app)


def poll(client, generation_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/generations/{generation_id}").json()
        if body["status"] != "processing":
            return body
        time.sleep(0.05)
    raise AssertionError("작업이 제한 시간 안에 끝나지 않았습니다.")


def fetch_image(client, url) -> Image.Image:
    res = client.get(url.replace("http://testserver", ""))
    assert res.status_code == 200
    return Image.open(io.BytesIO(res.content))


# ---------------------------------------------------------------------- /health
def test_health(tmp_path):
    with make_client(tmp_path) as client:
        res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.json()["primary_ready"] is True


# ---------------------------------------------------------------------- /generate
def test_generate_success_matches_spec(tmp_path):
    with make_client(tmp_path) as client:
        res = client.post("/generate", json=BASE_BODY)
        body = res.json()
        image = fetch_image(client, body["image_url"])
    assert res.status_code == 200
    # 스펙 3장 응답 필드
    assert set(body) >= {
        "id",
        "status",
        "image_url",
        "message",
        "source",
        "width",
        "height",
    }
    assert body["status"] == "success"
    assert len(body["id"]) == 36  # uuid4 문자열
    assert body["source"] == "mock"
    assert body["message"] == BASE_BODY["message"]
    assert (body["width"], body["height"]) == (1024, 1024)  # 스펙 5장 instagram
    assert image.size == (1024, 1024)


def test_frontend_payload_with_extra_fields_is_accepted(tmp_path):
    with make_client(tmp_path) as client:
        res = client.post("/generate", json={**BASE_BODY, "reference_image_url": None})
    assert res.status_code == 200


def test_processing_then_get_generation(tmp_path):
    with make_client(tmp_path, primary=MockGenerator(0.3)) as client:
        res = client.post(
            "/generate?wait=0",
            json={**BASE_BODY, "parent_id": "p-1"},
            headers={"X-Client-Id": "client-123"},
        )
        assert res.status_code == 202
        body = res.json()
        assert body["status"] == "processing"
        final = poll(client, body["id"])
    assert final["status"] == "success"
    assert final["parent_id"] == "p-1"
    assert final["input"]["product_name"] == "동네빵집"
    assert final["created_at"].endswith("Z")
    assert final["width"] == 1024


def test_get_unknown_generation_returns_404(tmp_path):
    with make_client(tmp_path) as client:
        res = client.get("/generations/nope")
    assert res.status_code == 404
    assert res.json() == {"detail": "결과를 찾을 수 없어요."}


def test_multipart_with_reference_and_adjustments(tmp_path):
    primary = RecordingMock(0.01)
    with make_client(tmp_path, primary=primary) as client:
        res = client.post(
            "/generate",
            data={**BASE_BODY, "adjustments": ["더 밝게", "배경 단순하게"]},
            files={
                "reference_image": ("bread.jpg", png_bytes(fmt="JPEG"), "image/jpeg")
            },
        )
    assert res.status_code == 200, res.text
    spec = primary.specs[0]
    assert spec.reference_image.startswith(b"\x89PNG")  # PNG로 통일
    assert spec.adjustments == ["더 밝게", "배경 단순하게"]


def test_multipart_adjustments_as_json_string(tmp_path):
    primary = RecordingMock(0.01)
    with make_client(tmp_path, primary=primary) as client:
        client.post("/generate", data={**BASE_BODY, "adjustments": '["텍스트 짧게"]'})
    assert primary.specs[0].adjustments == ["텍스트 짧게"]


# ---------------------------------------------------------------------- 에러 코드 (스펙 4장)
@pytest.mark.parametrize(
    "body",
    [
        {**BASE_BODY, "message": "   "},
        {**BASE_BODY, "product_name": ""},
        {k: v for k, v in BASE_BODY.items() if k != "product_name"},
    ],
)
def test_missing_required_text_returns_400(tmp_path, body):
    with make_client(tmp_path) as client:
        res = client.post("/generate", json=body)
    assert res.status_code == 400
    assert res.json() == {"detail": "상품 이름과 핵심 메시지는 꼭 입력해야 합니다."}


@pytest.mark.parametrize(
    "body",
    [
        {**BASE_BODY, "purpose": "tiktok"},
        {**BASE_BODY, "generation_mode": "auto"},
        {**BASE_BODY, "message": "가" * 201},
    ],
)
def test_invalid_values_return_422(tmp_path, body):
    with make_client(tmp_path) as client:
        res = client.post("/generate", json=body)
    assert res.status_code == 422
    assert "detail" in res.json()


def test_photo_over_10mb_returns_413(tmp_path):
    with make_client(tmp_path, max_upload_bytes=1000) as client:
        res = client.post(
            "/generate",
            data=BASE_BODY,
            files={"reference_image": ("big.png", noise_png(), "image/png")},
        )
    assert res.status_code == 413
    assert res.json() == {"detail": "사진은 10MB 이하로 올려 주세요."}


@pytest.mark.parametrize(
    ("filename", "data"),
    [("note.txt", b"hello"), ("photo.gif", png_bytes(fmt="GIF"))],
)
def test_unsupported_photo_returns_415(tmp_path, filename, data):
    with make_client(tmp_path) as client:
        res = client.post(
            "/generate", data=BASE_BODY, files={"reference_image": (filename, data)}
        )
    assert res.status_code == 415


def test_generation_failure_returns_503_with_detail(tmp_path):
    with make_client(
        tmp_path, primary=MockGenerator(0.01, fail_times=99), retry_count=0
    ) as client:
        res = client.post("/generate", json=BASE_BODY)
    assert res.status_code == 503
    assert res.json() == {"detail": "잠시 후 다시 시도해 주세요."}


def test_failed_generation_status_is_error(tmp_path):
    with make_client(
        tmp_path, primary=MockGenerator(0.3, fail_times=99), retry_count=0
    ) as client:
        generation_id = client.post("/generate?wait=0", json=BASE_BODY).json()["id"]
        final = poll(client, generation_id)
    assert final["status"] == "error"
    assert final["error"]


def test_input_error_returns_400_without_retry_or_fallback(tmp_path):
    primary = InputErrorMock(0)
    fallback = RecordingMock(0.01, name="fb")
    with make_client(tmp_path, primary=primary, fallback=fallback) as client:
        res = client.post("/generate", json=BASE_BODY)
    assert res.status_code == 400
    assert primary.calls == 1
    assert fallback.specs == []


def test_daily_job_limit_returns_429(tmp_path):
    with make_client(tmp_path, daily_job_limit=1) as client:
        assert client.post("/generate", json=BASE_BODY).status_code == 200
        res = client.post("/generate", json=BASE_BODY)
    assert res.status_code == 429
    assert res.json() == {"detail": "오늘 만들 수 있는 횟수를 다 썼어요."}


# ---------------------------------------------------------------------- 타임아웃
def test_timeout_fails_without_retry(tmp_path):
    primary = MockGenerator(1.0)
    with make_client(
        tmp_path,
        primary=primary,
        generation_timeout_seconds=0.2,
        retry_count=2,
    ) as client:
        res = client.post("/generate", json=BASE_BODY)
    assert res.status_code == 503
    assert primary.calls == 1  # 시간 초과는 재시도하지 않음


def test_timeout_falls_back(tmp_path):
    with make_client(
        tmp_path,
        primary=MockGenerator(1.0),
        fallback=MockGenerator(0.01, name="fb"),
        generation_timeout_seconds=0.2,
    ) as client:
        body = client.post("/generate", json=BASE_BODY).json()
    assert body["status"] == "success"
    assert body["route"] == "fallback"


# ---------------------------------------------------------------------- 재시도·Fallback
def test_retry_then_success_on_primary(tmp_path):
    primary = MockGenerator(0.01, fail_times=1)
    with make_client(tmp_path, primary=primary, retry_count=1) as client:
        body = client.post("/generate", json=BASE_BODY).json()
    assert body["status"] == "success"
    assert body["route"] == "primary"
    assert primary.calls == 2


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
        assert poll(client, first["id"])["route"] == "primary"
        assert poll(client, second["id"])["route"] == "fallback"


def test_primary_failure_falls_back_after_retry(tmp_path):
    primary = MockGenerator(0.01, fail_times=99)
    with make_client(
        tmp_path,
        primary=primary,
        fallback=MockGenerator(0.01, name="fb"),
        retry_count=1,
    ) as client:
        body = client.post("/generate", json=BASE_BODY).json()
    assert body["route"] == "fallback"
    assert primary.calls == 2


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
    assert second.status_code == 503
    assert health["extra_calls_today"] == 1


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
            client.post("/generate?wait=0", json=BASE_BODY).json()["id"]
            for _ in range(2)
        ]
        for generation_id in ids:
            poll(client, generation_id)
        elapsed = time.monotonic() - started
    assert elapsed < 0.9  # 순서대로였다면 1초 이상


# ---------------------------------------------------------------------- 생성 로그
def test_generation_log_uses_db_column_names(tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="just_make_it.serving.generations")
    with make_client(tmp_path) as client:
        client.post(
            "/generate", json=BASE_BODY, headers={"X-Client-Id": "client-abc"}
        ).json()
    records = [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.name == "just_make_it.serving.generations"
    ]
    assert len(records) == 1
    log = records[0]
    for column in (
        "id",
        "client_id",
        "purpose",
        "backend",
        "route",
        "model",
        "status",
        "queue_ms",
        "image_ms",
        "image_prompt",
    ):
        assert column in log
    assert log["client_id"] == "client-abc"
    assert log["status"] == "success"
    assert log["backend"] == "mock"


# ---------------------------------------------------------------------- /copies
def test_copies_returns_at_most_three(tmp_path):
    with make_client(tmp_path) as client:
        res = client.post(
            "/copies",
            json={
                "product_name": "동네꽃집",
                "message": "주말 20% 할인",
                "style": None,
            },
        )
    assert res.status_code == 200
    assert res.json() == {"copies": ["문구1", "문구2", "문구3"]}


def test_copies_missing_required_returns_400(tmp_path):
    with make_client(tmp_path) as client:
        res = client.post("/copies", json={"product_name": "꽃집", "message": " "})
    assert res.status_code == 400


def test_copies_model_failure_returns_503(tmp_path):
    writer = FakeCopyWriter(error=GeneratorError("down"))
    with make_client(tmp_path, copywriter=writer) as client:
        res = client.post("/copies", json={"product_name": "꽃집", "message": "할인"})
    assert res.status_code == 503


def test_copies_input_error_returns_400(tmp_path):
    writer = FakeCopyWriter(error=CopyInputError("empty"))
    with make_client(tmp_path, copywriter=writer) as client:
        res = client.post("/copies", json={"product_name": "꽃집", "message": "할인"})
    assert res.status_code == 400


def test_copies_timeout_returns_503(tmp_path):
    writer = FakeCopyWriter(delay=1.0)
    with make_client(tmp_path, copywriter=writer, copy_timeout_seconds=0.2) as client:
        res = client.post("/copies", json={"product_name": "꽃집", "message": "할인"})
    assert res.status_code == 503


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
    assert body["source"] == "local"
    assert (body["width"], body["height"]) == (1536, 864)  # 스펙 5장 youtube
    call = fake_core.calls[0]
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
        health = client.get("/health")
        res = client.post("/generate", json=BASE_BODY)
    registry.clear_loaded_models()
    assert health.status_code == 200
    assert health.json()["primary_ready"] is False
    assert res.status_code == 503
