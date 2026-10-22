"""생성 기록·이미지 저장: 서비스 파트의 DB(`service/db.py`)와 저장소를 서빙에 연결한다.

- 결과 id = `generations` 행 id = 서빙 작업 id (같은 값)
- 생성 이미지: `$DATA_DIR/images/{id}.png`, `/images/{id}.png`로 제공 (service/storage.py)
- 참고 사진: `$DATA_DIR/references/{id}` (공개 URL 없음). "다시 만들기"에서
  프론트가 사진을 다시 보내지 않으면 `parent_id`의 사진을 이어서 쓴다 (api_spec 6장)
"""

import logging
from pathlib import Path

# .env를 먼저 읽어야 service/storage.py가 PUBLIC_BASE_URL을 본다 (import 시점에 읽음)
import just_make_it.config  # noqa: F401
from just_make_it.service import db, storage

from .schemas import GenerationOutput, GenerationSpec, Route, Source

logger = logging.getLogger(__name__)


class GenerationRecords:
    """서빙이 쓰는 기록 함수 모음. DB 호출은 로컬 SQLite라 ms 단위로 끝난다."""

    def __init__(self, data_dir: Path) -> None:
        db.init(data_dir)  # 저장소 초기화 + 재시작 전 처리 중이던 행을 실패로 정리
        self.reference_dir = data_dir / "references"
        self.reference_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def image_dir() -> Path:
        return storage.image_dir()

    # ------------------------------------------------------------------ 생성 기록
    def start(
        self,
        *,
        client_id: str,
        spec: GenerationSpec,
        parent_id: str | None,
        backend: Source,
        model: str,
    ) -> str:
        """processing 행을 만들고 id를 돌려준다. input은 GET 응답의 `input`이 된다."""
        if parent_id and db.get_generation(parent_id) is None:
            # parent_id는 외래 키라 없는 값이면 저장이 실패한다. 새 생성으로 취급
            logger.warning("없는 parent_id 무시: %s", parent_id)
            parent_id = None
        return db.start_generation(
            client_id,
            {
                "purpose": spec.purpose,
                "product_name": spec.product_name,
                "message": spec.message,
                "style": spec.style,
                "adjustments": spec.adjustments,
            },
            backend=backend,
            model=model,
            parent_id=parent_id,
        )

    def finish(
        self,
        gid: str,
        output: GenerationOutput,
        *,
        source: Source,
        route: Route,
        queue_ms: int | None,
        image_ms: int | None,
    ) -> dict:
        """이미지를 저장하고 성공으로 기록. 반환값은 api_spec의 조회 응답 모양."""
        return db.finish_generation(
            gid,
            output.image_bytes,
            message=output.message,
            width=output.width,
            height=output.height,
            params={**output.params, "fallback_reason": output.fallback_reason},
            backend=source,
            route=route,
            model=output.model,
            image_prompt=output.prompt,
            seed=output.seed,
            queue_ms=queue_ms,
            text_ms=output.text_ms,
            image_ms=image_ms,
            cost_usd=output.cost_usd,
        )

    def fail(self, gid: str, error: str) -> None:
        db.fail_generation(gid, error)

    def get(self, gid: str) -> dict | None:
        return db.get_generation(gid)

    def count_today(self, client_id: str) -> int:
        return db.count_today(client_id)

    # ------------------------------------------------------------------ 참고 사진
    def _reference_path(self, gid: str) -> Path | None:
        # id는 서버가 만든 uuid지만 parent_id는 사용자 입력이라 경로 조작을 막는다
        if not gid or "/" in gid or "\\" in gid or gid.startswith("."):
            return None
        return self.reference_dir / gid

    def save_reference(self, gid: str, data: bytes) -> None:
        path = self._reference_path(gid)
        if path is not None:
            path.write_bytes(data)

    def load_reference(self, gid: str) -> bytes | None:
        path = self._reference_path(gid)
        if path is None or not path.is_file():
            return None
        return path.read_bytes()
