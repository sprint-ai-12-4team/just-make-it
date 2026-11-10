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
                **({"image_model": spec.image_model} if spec.image_model else {}),
                **({"consult_id": spec.consult_id} if spec.consult_id else {}),
                **({"keep_product": True} if spec.keep_product else {}),
                **(
                    {"reference_source": spec.reference_source}
                    if spec.reference_source
                    else {}
                ),
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
        product: bytes | None = None,
    ) -> dict:
        """이미지를 저장하고 성공으로 기록. 반환값은 api_spec의 조회 응답 모양.

        product: keep_product일 때 받은 투명 상품 사진 (`{id}-product.png`, `product_url`)

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
            product=product,
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
        # 상담·문구 변환에 쓴 금액도 같은 하루 상한에 들어감
        return float(row[0] or 0) + db.text_cost_today()

    def text_cost_today(self) -> float:
        """오늘 상담·문구 변환에 쓴 OpenAI 금액 (텍스트 몫 상한용)."""
        return db.text_cost_today()

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

    def _read(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        """읽기 전용 연결로 조회 (service/db.py에 없는 조회용)."""
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, args).fetchall()
        finally:
            conn.close()

    # ------------------------------------------------------------------ 같은 원본·고친 그림·사용 기록
    def family(self, gid: str, limit: int = 50) -> list[dict] | None:
        """같은 원본에서 만든 성공 결과 (만든 순서). 없는 id·상세페이지 섹션이면 None."""
        return db.family(gid, limit)

    def replace_image(
        self,
        gid: str,
        image: bytes,
        *,
        background: bytes | None = None,
        message: str | None = None,
    ) -> dict:
        """브라우저에서 고친 그림 저장. 반환값은 조회 응답 모양 (image_url 새 주소, edited=True)."""
        return db.replace_image(gid, image, background=background, message=message)

    def add_event(
        self, gid: str, client_id: str, event_type: str, detail: dict | None
    ) -> None:
        """사용 기록 1건. 모르는 type·없는 결과 id·4KB 넘는 detail이면 ValueError."""
        db.add_event(client_id, gid, event_type, detail)

    def adoption_stats(self, days: int) -> list[dict]:
        """최근 days일(한국 날짜) 단일 이미지 결과의 사용 지표. 날짜 오름차순.

        - generated: 성공한 결과 수 (상세페이지 칸 제외)
        - downloaded: 그중 다운로드 또는 링크 복사된 결과 수
        - edited: 그중 글자 직접 고치기·배경 지우기를 했거나 고친 그림을 저장한 결과 수
        - remade: 그중 다시 만들기·조금 수정하기의 원본이 된 결과 수 (parent_id 기준)
        """
        rows = self._read(
            """SELECT date(g.created_at, '+9 hours') AS day,
                      COUNT(*) AS generated,
                      SUM(EXISTS(SELECT 1 FROM events e WHERE e.generation_id = g.id
                                 AND e.type IN ('download', 'copy_link'))) AS downloaded,
                      SUM(EXISTS(SELECT 1 FROM events e WHERE e.generation_id = g.id
                                 AND e.type IN ('edit_text', 'cutout'))
                          OR COALESCE(json_extract(g.params_json, '$.edited'), 0))
                          AS edited,
                      SUM(EXISTS(SELECT 1 FROM generations c
                                 WHERE c.parent_id = g.id)) AS remade
                 FROM generations g
                WHERE g.status = 'success' AND g.detail_page_id IS NULL
                  AND g.created_at >= strftime('%Y-%m-%dT%H:%M:%fZ', 'now',
                        '+9 hours', 'start of day', ?, '-9 hours')
                GROUP BY day ORDER BY day""",
            (f"-{max(0, days - 1)} days",),
        )
        return [dict(row) for row in rows]

    def eval_rows(self, days: int) -> list[dict]:
        """정량평가 칸용 결과 1건씩 (GET /stats). 최근 days일, 단일 이미지, 끝난 것(success·error)만.

        mock 결과는 뺌. 각 행: day, status, backend, seconds(대기+문구+이미지),
        cost_usd, reference(upload·stock·none), downloaded, remade
        """
        rows = self._read(
            """SELECT date(g.created_at, '+9 hours') AS day, g.status, g.backend,
                      (COALESCE(g.queue_ms, 0) + COALESCE(g.text_ms, 0)
                       + COALESCE(g.image_ms, 0)) / 1000.0 AS seconds,
                      g.image_ms IS NOT NULL AS timed,
                      g.cost_usd,
                      COALESCE(json_extract(g.input_json, '$.reference_source'), 'none')
                          AS reference,
                      EXISTS(SELECT 1 FROM events e WHERE e.generation_id = g.id
                             AND e.type IN ('download', 'copy_link')) AS downloaded,
                      EXISTS(SELECT 1 FROM generations c WHERE c.parent_id = g.id)
                          AS remade
                 FROM generations g
                WHERE g.status IN ('success', 'error') AND g.detail_page_id IS NULL
                  AND g.backend != 'mock'
                  AND g.created_at >= strftime('%Y-%m-%dT%H:%M:%fZ', 'now',
                        '+9 hours', 'start of day', ?, '-9 hours')
                ORDER BY g.created_at""",
            (f"-{max(0, days - 1)} days",),
        )
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------ 상담·텍스트 호출
    def start_consult(
        self, client_id: str, ip: str | None, start: dict, first_message: dict
    ) -> str:
        return db.start_consult(client_id, ip, start, first_message)

    def get_consult(self, cid: str) -> dict | None:
        return db.get_consult(cid)

    def save_consult(self, consult: dict) -> None:
        db.save_consult(consult)

    def start_advice(
        self, client_id: str, ip: str | None, consult_id: str | None, advice: dict
    ) -> str:
        return db.start_advice(client_id, ip, consult_id, advice)

    def get_advice(self, aid: str) -> dict | None:
        return db.get_advice(aid)

    def save_advice(self, advice: dict) -> None:
        db.save_advice(advice)

    def add_text_call(
        self,
        kind: str,
        client_id: str,
        ip: str | None,
        *,
        model: str | None = None,
        source: str | None = None,
        cost_usd: float | None = None,
    ) -> None:
        db.add_text_call(
            kind, client_id, ip, model=model, source=source, cost_usd=cost_usd
        )

    def count_text_calls(
        self, kind: str, *, client_id: str | None = None, ip: str | None = None
    ) -> int:
        return db.count_text_calls(kind, client_id=client_id, ip=ip)

    def add_flag(
        self,
        reason: str,
        client_id: str,
        ip: str | None,
        *,
        consult_id: str | None = None,
    ) -> None:
        db.add_flag(reason, client_id, ip, consult_id=consult_id)

    def count_flags(
        self, *, client_id: str | None = None, ip: str | None = None
    ) -> int:
        return db.count_flags(client_id=client_id, ip=ip)

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

    def reference_source(self, gid: str) -> str | None:
        """원본 결과의 참고 사진 출처 (다시 만들기에서 이어 씀). 없으면 None."""
        row = db.get_generation(gid)
        return ((row or {}).get("input") or {}).get("reference_source")

    def load_reference(self, gid: str) -> bytes | None:
        path = self._reference_path(gid)
        if path is None or not path.is_file():
            return None
        return path.read_bytes()
