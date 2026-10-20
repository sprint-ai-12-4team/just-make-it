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
from .generators import Generators, build_generators
from .queue_manager import QueueManager
from .router import router
from .settings import ServingSettings, get_serving_settings
from .storage import LocalResultStore, ResultStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def create_app(
    settings: ServingSettings | None = None,
    generators: Generators | None = None,
    result_store: ResultStore | None = None,
    copywriter: CopyWriter | None = None,
) -> FastAPI:
    """앱을 만든다. 테스트에서는 설정·생성기·저장소·문구 생성기를 갈아 끼울 수 있다."""
    settings = settings or get_serving_settings()
    primary, fallback, premium = generators or build_generators(settings)
    store = result_store or LocalResultStore(
        settings.result_dir, settings.public_base_url
    )
    if copywriter is None:
        copywriter = (
            MockCopyWriter() if settings.image_backend == "mock" else CoreCopyWriter()
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        manager = QueueManager(settings, primary, fallback, premium, store)
        app.state.manager = manager
        await manager.start()
        try:
            yield
        finally:
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
    app.include_router(router)

    settings.result_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/results", StaticFiles(directory=settings.result_dir), name="results")
    return app


app = create_app()
