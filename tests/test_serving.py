"""서빙 API 테스트. Mock 생성기와 core 가짜 모델을 써서 API 비용 없이 실행된다.

API 계약은 PM API 스펙(`docs/api_spec.md`)을 기준으로 검증한다.
실행: uv run pytest tests/test_serving.py
"""

import io
import json
import logging
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

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
        data_dir=tmp_path,
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


def db_rows(tmp_path, sql="SELECT * FROM generations ORDER BY rowid") -> list[dict]:
    """서빙이 남긴 generations 행 (service/db.py의 SQLite 파일)."""
    conn = sqlite3.connect(tmp_path / "just_make_it.db")
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql)]
    finally:
        conn.close()


def route_of(tmp_path, generation_id) -> str:
    return next(r["route"] for r in db_rows(tmp_path) if r["id"] == generation_id)


def post_parallel(client, n, body=BASE_BODY) -> list:
    """동기 응답이라 동시에 보내려면 스레드를 쓴다."""
    with ThreadPoolExecutor(n) as pool:
        futures = []
        for _ in range(n):
            futures.append(pool.submit(client.post, "/generate", json=body))
            time.sleep(0.05)  # 접수 순서를 고정
        return [f.result() for f in futures]


def fetch_image(client, url):
    res = client.get(urlparse(url).path)
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


def test_get_generation_returns_saved_result(tmp_path):
    with make_client(tmp_path) as client:
        first = client.post("/generate", json=BASE_BODY).json()
        second = client.post(
            "/generate",
            json={**BASE_BODY, "parent_id": first["id"], "adjustments": ["더 밝게"]},
            headers={"X-Client-Id": "client-123"},
        ).json()
        res = client.get(f"/generations/{second['id']}")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert body["parent_id"] == first["id"]
    assert body["image_url"] == second["image_url"]
    assert body["input"]["product_name"] == "동네빵집"
    assert body["input"]["adjustments"] == ["더 밝게"]
    assert body["created_at"].endswith("Z")
    assert body["width"] == 1024
    row = db_rows(tmp_path)[-1]
    assert row["client_id"] == "client-123"
    assert row["route"] == "primary" and row["backend"] == "mock"
    assert row["queue_ms"] is not None and row["image_ms"] is not None


def test_results_survive_restart(tmp_path):
    with make_client(tmp_path) as client:
        body = client.post("/generate", json=BASE_BODY).json()
    with make_client(tmp_path) as client:  # 서버 재시작
        again = client.get(f"/generations/{body['id']}").json()
        image = fetch_image(client, again["image_url"])
    assert again["status"] == "success"
    assert image.size == (1024, 1024)


def test_unknown_parent_id_is_ignored(tmp_path):
    with make_client(tmp_path) as client:
        res = client.post("/generate", json={**BASE_BODY, "parent_id": "no-such-id"})
    assert res.status_code == 200
    assert db_rows(tmp_path)[0]["parent_id"] is None


def test_regenerate_reuses_parent_reference_photo(tmp_path):
    primary = RecordingMock(0.01)
    with make_client(tmp_path, primary=primary) as client:
        first = client.post(
            "/generate",
            data=BASE_BODY,
            files={"reference_image": ("p.png", png_bytes(), "image/png")},
        ).json()
        # 다시 만들기: 프론트는 사진을 다시 보내지 않는다
        client.post("/generate", json={**BASE_BODY, "parent_id": first["id"]})
        client.post("/generate", json=BASE_BODY)  # 새 생성은 사진 없음
    assert primary.specs[1].reference_image == primary.specs[0].reference_image
    assert primary.specs[2].reference_image is None
    # 참고 사진은 공개 URL(/images)이 아닌 references/에 둔다
    assert (tmp_path / "references" / first["id"]).exists()
    assert not list((tmp_path / "images").glob("*ref*"))


def test_image_is_readable_from_frontend_origin(tmp_path):
    # 프론트 canvas가 이미지를 읽으려면 CORS 헤더가 있어야 한다 (api_spec 5장)
    with make_client(tmp_path) as client:
        body = client.post("/generate", json=BASE_BODY).json()
        res = client.get(
            urlparse(body["image_url"]).path,
            headers={"Origin": "http://localhost:3000"},
        )
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://localhost:3000"


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
        {**BASE_BODY, "adjustments": "더 밝게"},
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


def test_failed_generation_is_recorded_as_error(tmp_path):
    with make_client(
        tmp_path, primary=MockGenerator(0.01, fail_times=99), retry_count=0
    ) as client:
        client.post("/generate", json=BASE_BODY)
        row = db_rows(tmp_path)[0]
        res = client.get(f"/generations/{row['id']}")
    assert row["status"] == "error" and row["error"]
    assert res.json()["status"] == "error"


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


def test_client_daily_limit_is_per_user(tmp_path):
    with make_client(tmp_path, client_daily_limit=1) as client:
        a1 = client.post("/generate", json=BASE_BODY, headers={"X-Client-Id": "a"})
        a2 = client.post("/generate", json=BASE_BODY, headers={"X-Client-Id": "a"})
        b1 = client.post("/generate", json=BASE_BODY, headers={"X-Client-Id": "b"})
    assert (a1.status_code, a2.status_code, b1.status_code) == (200, 429, 200)


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
    assert route_of(tmp_path, body["id"]) == "fallback"
    assert body["source"] == "mock"


# ---------------------------------------------------------------------- 재시도·Fallback
def test_retry_then_success_on_primary(tmp_path):
    primary = MockGenerator(0.01, fail_times=1)
    with make_client(tmp_path, primary=primary, retry_count=1) as client:
        body = client.post("/generate", json=BASE_BODY).json()
    assert body["status"] == "success"
    assert route_of(tmp_path, body["id"]) == "primary"
    assert primary.calls == 2


def test_queue_wait_triggers_fallback(tmp_path):
    with make_client(
        tmp_path,
        primary=MockGenerator(0.5),
        fallback=MockGenerator(0.01, name="fb"),
        seconds_per_job_init=10.0,
        max_wait_seconds=15.0,
    ) as client:
        first, second = (r.json() for r in post_parallel(client, 2))
    assert route_of(tmp_path, first["id"]) == "primary"
    assert route_of(tmp_path, second["id"]) == "fallback"
    # DB에는 Fallback 이유 대신 경로만 남고, 이유는 생성 로그에 남는다


def test_primary_failure_falls_back_after_retry(tmp_path):
    primary = MockGenerator(0.01, fail_times=99)
    with make_client(
        tmp_path,
        primary=primary,
        fallback=MockGenerator(0.01, name="fb"),
        retry_count=1,
    ) as client:
        body = client.post("/generate", json=BASE_BODY).json()
    assert route_of(tmp_path, body["id"]) == "fallback"
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
    assert route_of(tmp_path, first.json()["id"]) == "fallback"
    assert second.status_code == 503
    assert health["extra_calls_today"] == 1


def test_premium_route(tmp_path):
    premium = RecordingMock(0.01, name="premium")
    with make_client(tmp_path, premium=premium) as client:
        body = client.post("/generate", json={**BASE_BODY, "premium": True}).json()
    assert route_of(tmp_path, body["id"]) == "premium"
    assert len(premium.specs) == 1


def test_premium_without_premium_model_uses_primary(tmp_path):
    with make_client(tmp_path) as client:
        body = client.post("/generate", json={**BASE_BODY, "premium": True}).json()
    assert route_of(tmp_path, body["id"]) == "primary"


def test_primary_concurrency_runs_jobs_in_parallel(tmp_path):
    with make_client(
        tmp_path, primary=MockGenerator(0.5), primary_concurrency=2
    ) as client:
        started = time.monotonic()
        results = post_parallel(client, 2)
        elapsed = time.monotonic() - started
    assert all(r.status_code == 200 for r in results)
    assert elapsed < 0.95  # 순서대로였다면 1초 이상


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
    # 글자는 프론트가 얹으므로 이미지 프롬프트에 문구를 그리라는 지시가 없어야 한다
    assert "Include this Korean headline" not in call["prompt"]
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
    assert route_of(tmp_path, body["id"]) == "fallback"


def test_app_starts_without_api_key(tmp_path, monkeypatch):
    # 배포 환경에서 키가 빠져도 서버는 떠야 한다 (헬스체크로 원인 확인)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    registry.clear_loaded_models()
    settings = ServingSettings(_env_file=None, data_dir=tmp_path)
    with TestClient(create_app(settings=settings)) as client:
        health = client.get("/health")
        res = client.post("/generate", json=BASE_BODY)
    registry.clear_loaded_models()
    assert health.status_code == 200
    assert health.json()["primary_ready"] is False
    assert res.status_code == 503


# ---------------------------------------------------------------------- Swagger 문서
def test_docs_show_request_body_inputs(tmp_path):
    # 본문을 직접 읽어도 /docs에 입력 칸이 보여야 한다
    with make_client(tmp_path) as client:
        spec = client.get("/openapi.json").json()
    copies = spec["paths"]["/copies"]["post"]["requestBody"]["content"]
    generate = spec["paths"]["/generate"]["post"]["requestBody"]["content"]
    assert "application/json" in copies
    assert {"application/json", "multipart/form-data"} <= set(generate)
    form = generate["multipart/form-data"]["schema"]["properties"]
    assert form["reference_image"]["format"] == "binary"
