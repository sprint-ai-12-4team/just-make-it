"""이미지 저장소: VM 로컬 디스크.

서빙은 app.mount("/images", StaticFiles(directory=storage.image_dir())) 한 줄로 파일을 내보냅니다.
"""

import os
from pathlib import Path

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")

_dir: Path | None = None


def init(data_dir: Path) -> None:
    global _dir
    _dir = data_dir / "images"
    _dir.mkdir(parents=True, exist_ok=True)


def image_dir() -> Path:
    assert _dir, "storage.init()을 먼저 불러야 합니다"
    return _dir


def save(name: str, data: bytes) -> str:
    """name은 서버가 만든 값(uuid + 확장자)만 넘깁니다. 사용자 입력 파일명 금지 (경로 조작 방지)."""
    if "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"잘못된 파일 이름: {name}")
    (image_dir() / name).write_bytes(data)
    return name


def load(name: str) -> bytes:
    return (image_dir() / name).read_bytes()


def remove(name: str) -> None:
    (image_dir() / name).unlink(missing_ok=True)


def url(name: str | None) -> str | None:
    return f"{PUBLIC_BASE_URL}/images/{name}" if name else None
