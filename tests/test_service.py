"""service/ 검사. 실제 API·모델 호출 없음 (임시 폴더의 SQLite만 사용)."""

from pathlib import Path

import pytest

from just_make_it.service import db, storage

SCHEMA = db.SCHEMA if db.SCHEMA.exists() else Path(__file__).parents[1] / "docs" / "schema.sql"
INPUT = {"purpose": "instagram", "product_name": "소금빵", "message": "신메뉴 출시", "style": None, "adjustments": []}


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    db.init(tmp_path, SCHEMA)


def test_generation_flow(tmp_path):
    gid = db.start_generation("c1", {**INPUT, "reference_image_path": "x.png"}, backend="local", model="klein")
    assert db.get_generation(gid)["status"] == "processing"

    g = db.finish_generation(gid, b"png", message="신메뉴!", width=1024, height=1024, backend="openai", image_ms=900)
    assert g["status"] == "success" and g["source"] == "openai" and g["message"] == "신메뉴!"
    assert g["image_url"].endswith(f"/images/{gid}.png") and g["width"] == 1024
    assert "reference_image_path" not in g["input"]  # 내부 경로는 응답에 안 나감
    assert (tmp_path / "images" / f"{gid}.png").read_bytes() == b"png"
    assert db.count_today("c1") == 1 and db.count_today("c2") == 0

    with pytest.raises(TypeError):
        db.finish_generation(gid, b"", message="", width=1, height=1, client_id="hack")
    assert db.get_generation("없음") is None


def test_text_edit_flow(tmp_path):
    gid = db.start_generation("c1", INPUT, backend="local", model="klein")
    assert db.background(gid) is None  # 아직 processing
    layout = {"position": "top", "font": "jua", "size_scale": 1.0}
    g = db.finish_generation(gid, b"txt", message="신메뉴", width=1, height=1, background=b"bg", text_layout=layout)
    assert g["background_url"].endswith(f"/images/{gid}-bg.png") and g["text_layout"] == layout
    assert db.background(gid) == b"bg"

    first = db.update_text(gid, b"txt2", message="고친 문구", text_layout={**layout, "position": "bottom"})
    second = db.update_text(gid, b"txt3", message="또 고침", text_layout=layout)
    assert first["image_url"] != g["image_url"] != second["image_url"]
    assert second["message"] == "또 고침" and db.get_generation(gid)["text_layout"] == layout
    images = tmp_path / "images"
    assert (images / f"{gid}.png").exists()  # 첫 결과는 남김
    assert not (images / first["image_url"].rsplit("/", 1)[1]).exists()  # 중간 결과는 지움
    assert (images / second["image_url"].rsplit("/", 1)[1]).read_bytes() == b"txt3"

    old = db.start_generation("c1", INPUT, backend="local", model="klein")
    assert db.finish_generation(old, b"png", message="", width=1, height=1)["background_url"] is None
    assert db.background(old) is None  # 원본 없는 예전 결과는 글자 고치기 불가


def test_restart_marks_processing_as_error(tmp_path):
    gid = db.start_generation("c1", INPUT, backend="local", model="klein")
    db.init(tmp_path, SCHEMA)
    assert db.get_generation(gid)["status"] == "error"


def test_detail_page_flow():
    pid = db.start_detail_page("c1", {"product_name": "딸기잼", "message": "국산 100%", "features": []})
    assert db.has_running_detail_page("c1")
    assert [s["status"] for s in db.get_detail_page(pid)["sections"]] == ["pending"] * 5

    texts = [{"role": r, "title": f"제목{i}", "body": "본문", "image_prompt": "p"}
             for i, r in enumerate(["hero", "feature", "feature", "feature", "closing"])]
    db.set_detail_sections(pid, texts)
    ids = [db.start_generation("c1", INPUT, backend="local", model="klein", detail_page_id=pid, section_index=i)
           for i in range(5)]
    for gid in ids[:4]:
        db.finish_generation(gid, b"png", message="", width=1024, height=1024)
    page = db.get_detail_page(pid)
    assert page["status"] == "processing" and page["progress"]["done"] == 4

    db.fail_generation(ids[4], "OOM")
    page = db.get_detail_page(pid)
    assert page["status"] == "success" and page["sections"][4]["status"] == "error"
    assert not db.has_running_detail_page("c1")

    # 섹션 다시 만들기: 새 행이 최신 결과가 되고 이전 행은 parent로 남음
    redo = db.section_input(pid, 4)
    assert redo["parent_id"] == ids[4] and redo["section"]["title"] == "제목4"
    new = db.start_generation("c1", INPUT, backend="openai", model="flare", parent_id=redo["parent_id"],
                              detail_page_id=pid, section_index=4)
    assert db.get_detail_page(pid)["sections"][4]["status"] == "processing"
    db.finish_generation(new, b"png", message="", width=1024, height=1024)
    assert db.get_detail_page(pid)["sections"][4]["image_url"].endswith(f"{new}.png")


def test_storage_rejects_path_names():
    for bad in ["../x.png", "a/b.png", ".env"]:
        with pytest.raises(ValueError):
            storage.save(bad, b"")
