"""생성 기록 DB: VM 로컬 SQLite. 응답 모양은 docs/api_spec.md 그대로 돌려줍니다.

서빙 사용 순서
  단일 이미지: start_generation → (모델) → finish_generation | fail_generation
  상세페이지: start_detail_page → (텍스트) → set_detail_sections | fail_detail_page
             → 섹션마다 start_generation(detail_page_id=, section_index=) → finish | fail
  조회: get_generation, get_detail_page / 제한: count_today, has_running_detail_page

ponytail: 로컬 SQLite·디스크는 ms 단위라 동기 함수. 이벤트 루프가 막히면 서빙에서 asyncio.to_thread로 감싸기
"""

import json
import sqlite3
import threading
import uuid
from pathlib import Path

from just_make_it.service import storage

SCHEMA = Path(__file__).with_name("schema.sql")
SECTION_COUNT = 5  # 대표 · 특징 ×3 · 마무리 (api_spec)

# finish_generation에서 바로 저장할 수 있는 열
_RESULT_COLS = {
    "backend", "route", "model", "model_version", "seed", "image_prompt",
    "queue_ms", "text_ms", "image_ms", "cost_usd",
}

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()


def init(data_dir: Path, schema: Path = SCHEMA) -> None:
    """앱 시작 시 1번. 재시작 전에 처리 중이던 작업은 끝날 수 없으므로 실패로 정리."""
    global _conn
    data_dir.mkdir(parents=True, exist_ok=True)
    storage.init(data_dir)
    _conn = sqlite3.connect(data_dir / "just_make_it.db", check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _conn.executescript(schema.read_text())
    with _conn:
        _conn.execute("UPDATE generations SET status='error', error='서버 재시작' WHERE status='processing'")
        _conn.execute("UPDATE detail_pages SET status='error', error='서버 재시작' WHERE status='processing'")


def _run(sql: str, args: tuple = ()) -> list[sqlite3.Row]:
    assert _conn, "db.init()을 먼저 불러야 합니다"
    with _lock, _conn:
        return _conn.execute(sql, args).fetchall()


# ---------- 단일 이미지 · 섹션 이미지 ----------

def start_generation(
    client_id: str,
    input: dict,
    *,
    backend: str,
    model: str,
    parent_id: str | None = None,
    detail_page_id: str | None = None,
    section_index: int | None = None,
) -> str:
    """input: api_spec의 요청 필드 (+ reference_image_path). 반환값 id = 응답 id = 서빙 job_id."""
    gid = str(uuid.uuid4())
    _run(
        """INSERT INTO generations (id, client_id, parent_id, detail_page_id, section_index,
               purpose, input_json, backend, model, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'processing')""",
        (gid, client_id, parent_id, detail_page_id, section_index,
         input.get("purpose", "commerce"), json.dumps(input, ensure_ascii=False), backend, model),
    )
    return gid


def finish_generation(
    gid: str, image: bytes, *, message: str, width: int, height: int, params: dict | None = None, **result
) -> dict:
    """이미지 저장 + 성공 기록. result: backend(fallback이면 바뀐 값), model, seed, image_ms 등 _RESULT_COLS."""
    if bad := set(result) - _RESULT_COLS:
        raise TypeError(f"모르는 열: {bad}")
    path = storage.save(f"{gid}.png", image)
    params = {**(params or {}), "width": width, "height": height}
    sets = "".join(f", {k}=?" for k in result)
    _run(
        f"""UPDATE generations SET status='success', image_path=?, copy_json=?, params_json=?{sets}
            WHERE id=?""",
        (path, json.dumps({"message": message}, ensure_ascii=False), json.dumps(params), *result.values(), gid),
    )
    _close_detail_page_if_done(gid)
    return get_generation(gid)


def fail_generation(gid: str, error: str) -> None:
    """error는 기록용(내부 메시지 가능). API 응답 detail에는 넣지 않음."""
    _run("UPDATE generations SET status='error', error=? WHERE id=?", (error, gid))
    _close_detail_page_if_done(gid)


def get_generation(gid: str) -> dict | None:
    rows = _run("SELECT * FROM generations WHERE id=?", (gid,))
    if not rows:
        return None
    r = rows[0]
    params = json.loads(r["params_json"] or "{}")
    input = json.loads(r["input_json"])
    input.pop("reference_image_path", None)
    return {
        "id": r["id"],
        "status": r["status"],
        "image_url": storage.url(r["image_path"]),
        "message": json.loads(r["copy_json"])["message"] if r["copy_json"] else input.get("message"),
        "source": r["backend"],
        "width": params.get("width"),
        "height": params.get("height"),
        "parent_id": r["parent_id"],
        "created_at": r["created_at"],
        "input": input,
    }


def count_today(client_id: str) -> int:
    """오늘(한국 시간) 생성 수. 일일 한도 검사용. 섹션 이미지도 1건으로 셈."""
    return _run(
        """SELECT COUNT(*) FROM generations WHERE client_id=?
           AND created_at >= strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '+9 hours', 'start of day', '-9 hours')""",
        (client_id,),
    )[0][0]


# ---------- 상세페이지 ----------

def start_detail_page(client_id: str, input: dict) -> str:
    pid = str(uuid.uuid4())
    _run(
        "INSERT INTO detail_pages (id, client_id, input_json, status) VALUES (?, ?, ?, 'processing')",
        (pid, client_id, json.dumps(input, ensure_ascii=False)),
    )
    return pid


def set_detail_sections(pid: str, sections: list[dict], text_ms: int | None = None) -> None:
    """sections: [{role, title, body, image_prompt}] × SECTION_COUNT. 텍스트 모델 결과."""
    _run(
        "UPDATE detail_pages SET sections_json=?, text_ms=? WHERE id=?",
        (json.dumps(sections, ensure_ascii=False), text_ms, pid),
    )


def fail_detail_page(pid: str, error: str) -> None:
    _run("UPDATE detail_pages SET status='error', error=? WHERE id=?", (error, pid))


def has_running_detail_page(client_id: str) -> bool:
    """사용자당 진행 중 1개 제한 (api_spec 409)."""
    return bool(_run("SELECT 1 FROM detail_pages WHERE client_id=? AND status='processing'", (client_id,)))


def _latest_sections(pid: str) -> dict[int, sqlite3.Row]:
    """섹션별 가장 최근 생성 행. 이전 행은 다시 만들기 전 기록."""
    rows = _run(
        """SELECT * FROM generations WHERE detail_page_id=?
           ORDER BY section_index, created_at, rowid""",
        (pid,),
    )
    return {r["section_index"]: r for r in rows}  # 같은 index면 나중 행이 덮어씀


def _close_detail_page_if_done(gid: str) -> None:
    rows = _run("SELECT detail_page_id FROM generations WHERE id=?", (gid,))
    pid = rows and rows[0]["detail_page_id"]
    if not pid:
        return
    latest = _latest_sections(pid)
    if len(latest) == SECTION_COUNT and all(r["status"] != "processing" for r in latest.values()):
        _run("UPDATE detail_pages SET status='success' WHERE id=? AND status='processing'", (pid,))


def get_detail_page(pid: str) -> dict | None:
    rows = _run("SELECT * FROM detail_pages WHERE id=?", (pid,))
    if not rows:
        return None
    page = rows[0]
    texts = json.loads(page["sections_json"] or "null")
    latest = _latest_sections(pid)
    sections = []
    for i in range(SECTION_COUNT):
        t = texts[i] if texts else {}
        r = latest.get(i)
        if not texts:
            status = "error" if page["status"] == "error" else "pending"
        else:
            status = r["status"] if r else ("error" if page["status"] == "error" else "processing")
        sections.append({
            "index": i,
            "role": t.get("role") or ("hero" if i == 0 else "closing" if i == SECTION_COUNT - 1 else "feature"),
            "status": status,
            "title": t.get("title"),
            "body": t.get("body"),
            "image_url": storage.url(r["image_path"]) if r else None,
            "source": r["backend"] if r and r["status"] == "success" else None,
        })
    return {
        "id": pid,
        "status": page["status"],
        "progress": {"done": sum(s["status"] in ("success", "error") for s in sections), "total": SECTION_COUNT},
        "sections": sections,
        "created_at": page["created_at"],
    }


def section_input(pid: str, index: int) -> dict | None:
    """섹션 다시 만들기용: 저장된 image_prompt와 직전 결과 id(parent_id). 문구는 그대로."""
    rows = _run("SELECT input_json, sections_json, client_id FROM detail_pages WHERE id=?", (pid,))
    if not rows or not rows[0]["sections_json"]:
        return None
    prev = _latest_sections(pid).get(index)
    return {
        "client_id": rows[0]["client_id"],
        "input": json.loads(rows[0]["input_json"]),
        "section": json.loads(rows[0]["sections_json"])[index],
        "parent_id": prev["id"] if prev else None,
    }
