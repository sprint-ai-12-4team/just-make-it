"""생성 기록·이미지 저장: 서비스 파트의 DB(`service/db.py`)와 저장소를 서빙에 연결한다.

- 결과 id = `generations` 행 id = 서빙 작업 id (같은 값)
- 생성 이미지: `$DATA_DIR/images/{id}.png`, `/images/{id}.png`로 제공 (service/storage.py)
  글자 없는 원본은 `{id}-bg.png` (`background_url`). 글자를 고치면 최종 이미지 파일 이름이 바뀐다
- 참고 사진: `$DATA_DIR/references/{id}` (공개 URL 없음). "다시 만들기"에서
  프론트가 사진을 다시 보내지 않으면 `parent_id`의 사진을 이어서 쓴다 (api_spec 6장)
"""

import logging
import sqlite3
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
        self.db_path = data_dir / "just_make_it.db"
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
        detail_page_id: str | None = None,
        section_index: int | None = None,
    ) -> str:
        """processing 행을 만들고 id를 돌려준다. input은 GET 응답의 `input`이 된다.

        상세페이지 섹션 이미지는 detail_page_id·section_index를 함께 남긴다.
        """
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
            detail_page_id=detail_page_id,
            section_index=section_index,
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
        """이미지를 저장하고 성공으로 기록. 반환값은 api_spec의 조회 응답 모양.

        시간은 따로 기록한다: queue_ms 대기, output.text_ms 문구, image_ms 그림 모델.
        생성기 호출 전체 시간은 params의 run_ms.
        """
        return db.finish_generation(
            gid,
            output.image_bytes,
            message=output.message,
            width=output.width,
            height=output.height,
            background=output.background_bytes,
            text_layout=output.text_layout,
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

    def background(self, gid: str) -> bytes | None:
        """글자 없는 원본. 성공한 결과가 아니거나 원본이 없는 예전 결과면 None."""
        return db.background(gid)

    def update_text(
        self, gid: str, image: bytes, *, message: str, text_layout: dict | None
    ) -> dict:
        """글자 고치기 결과 저장. 반환값은 조회 응답 모양 (image_url이 새 주소)."""
        return db.update_text(gid, image, message=message, text_layout=text_layout)

    def fail(self, gid: str, error: str) -> None:
        db.fail_generation(gid, error)

    def get(self, gid: str) -> dict | None:
        return db.get_generation(gid)

    def count_today(self, client_id: str) -> int:
        return db.count_today(client_id)

    def cost_today(self) -> float:
        """오늘(한국 시간) 생성 기록의 cost_usd 합계. 서버를 다시 켜도 금액 상한이 이어지게."""
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        try:
            row = conn.execute("""SELECT COALESCE(SUM(cost_usd), 0) FROM generations
                   WHERE created_at >= strftime('%Y-%m-%dT%H:%M:%fZ', 'now',
                         '+9 hours', 'start of day', '-9 hours')""").fetchone()
        finally:
            conn.close()
        return float(row[0] or 0)

    def seed_of(self, gid: str) -> int | None:
        """결과를 만들 때 쓴 시드 (조금 수정하기에서 구도 유지용). 없으면 None.

        service/db.py에 조회 함수가 없어 읽기 전용 연결로 직접 읽는다.
        """
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT seed FROM generations WHERE id=?", (gid,)
            ).fetchone()
        finally:
            conn.close()
        return row[0] if row else None

    # ------------------------------------------------------------------ 상세페이지
    def start_detail_page(self, client_id: str, input: dict) -> str:
        return db.start_detail_page(client_id, input)

    def set_detail_sections(
        self, pid: str, sections: list[dict], text_ms: int | None
    ) -> None:
        db.set_detail_sections(pid, sections, text_ms)

    def fail_detail_page(self, pid: str, error: str) -> None:
        db.fail_detail_page(pid, error)

    def has_running_detail_page(self, client_id: str) -> bool:
        return db.has_running_detail_page(client_id)

    def get_detail_page(self, pid: str) -> dict | None:
        return db.get_detail_page(pid)

    def section_input(self, pid: str, index: int) -> dict | None:
        return db.section_input(pid, index)

    def fail_section(
        self,
        *,
        client_id: str,
        spec: GenerationSpec,
        detail_page_id: str,
        section_index: int,
        backend: Source,
        model: str,
        error: str,
    ) -> None:
        """대기열에 넣지도 못한 섹션(한도 초과 등)을 실패 행으로 남긴다.

        행이 없으면 그 섹션이 계속 processing으로 보이고 페이지가 끝나지 않는다.
        """
        gid = self.start(
            client_id=client_id,
            spec=spec,
            parent_id=None,
            backend=backend,
            model=model,
            detail_page_id=detail_page_id,
            section_index=section_index,
        )
        db.fail_generation(gid, error)

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
