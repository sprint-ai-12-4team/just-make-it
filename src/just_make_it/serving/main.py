"""FastAPI 실행 엔트리포인트.

실행 (반드시 워커 프로세스 1개 — RAM 16GB 보호):
    uv run uvicorn just_make_it.serving.main:app --host 0.0.0.0 --port 8000 --workers 1

API 키 없이 개발할 때는 `.env`에 `IMAGE_BACKEND=mock`.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .copywriter import CopyWriter, CoreCopyWriter, MockCopyWriter
from .detail_pages import (
    CoreDetailWriter,
    DetailPageService,
    DetailWriter,
    MockDetailWriter,
)
from .generators import Generators, build_generators
from .queue_manager import QueueManager
from .records import GenerationRecords
from .router import router
from .settings import ServingSettings, get_serving_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def create_app(
    settings: ServingSettings | None = None,
    generators: Generators | None = None,
    copywriter: CopyWriter | None = None,
    detail_writer: DetailWriter | None = None,
) -> FastAPI:
    """앱을 만든다. 테스트에서는 설정·생성기·문구 생성기를 갈아 끼울 수 있다."""
    settings = settings or get_serving_settings()
    primary, fallback, premium = generators or build_generators(settings)
    records = GenerationRecords(settings.data_dir)
    if copywriter is None:
        copywriter = (
            MockCopyWriter() if settings.image_backend == "mock" else CoreCopyWriter()
        )
    if detail_writer is None:
        detail_writer = (
            MockDetailWriter()
            if settings.image_backend == "mock"
            else CoreDetailWriter()
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        manager = QueueManager(settings, primary, fallback, premium, records)
        app.state.manager = manager
        detail_pages = DetailPageService(settings, manager, detail_writer, records)
        app.state.detail_pages = detail_pages
        await manager.start()
        try:
            yield
        finally:
            await detail_pages.stop()
            await manager.stop()

    app = FastAPI(
        title="just-make-it serving API",
        version="0.1.0",
        description="소상공인 광고 이미지 생성 서빙 API",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.copywriter = copywriter
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.records = records
    app.include_router(router)

    # 생성 이미지: /images/{id}.png (service/storage.py). CORS는 위 미들웨어가 함께 적용
    # → 프론트 canvas가 이미지를 읽어 문구를 얹을 수 있다
    app.mount("/images", StaticFiles(directory=records.image_dir()), name="images")
    return app


app = create_app()
