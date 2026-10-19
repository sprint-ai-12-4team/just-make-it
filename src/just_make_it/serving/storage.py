"""생성 결과 저장.

서비스 파트의 GCS 업로더(`service/gcs_storage.py`)가 준비되면 같은 `save` 규칙을
따르는 클래스를 만들어 `create_app(result_store=...)`에 넘기면 된다.
"""

from pathlib import Path
from typing import Protocol


class ResultStore(Protocol):
    def save(self, job_id: str, image_bytes: bytes) -> str:
        """PNG 바이트를 저장하고 유저가 열 수 있는 URL을 반환한다. (블로킹)"""
        ...


class LocalResultStore:
    """로컬 디스크에 저장하고 `/results/<job_id>.png`로 서빙한다."""

    def __init__(self, directory: Path, public_base_url: str) -> None:
        self.directory = directory
        self.public_base_url = public_base_url.rstrip("/")
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, job_id: str, image_bytes: bytes) -> str:
        path = self.directory / f"{job_id}.png"
        path.write_bytes(image_bytes)
        return f"{self.public_base_url}/results/{path.name}"
