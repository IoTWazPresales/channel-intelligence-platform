from pathlib import Path

from app.core.config import get_settings
from app.storage.base import StorageBackend


class LocalStorageBackend(StorageBackend):
    def __init__(self, base_path: str | None = None) -> None:
        settings = get_settings()
        self._root = Path(base_path or settings.local_storage_path)
        self._root.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, data: bytes, content_type: str | None = None) -> str:
        safe = key.replace("..", "").lstrip("/\\")
        path = self._root / safe
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return safe

    def read(self, key: str) -> bytes:
        path = self._root / key.replace("..", "").lstrip("/\\")
        return path.read_bytes()


def get_storage_backend() -> StorageBackend:
    settings = get_settings()
    if settings.storage_backend == "local":
        return LocalStorageBackend()
    raise NotImplementedError("S3 adapter not implemented in MVP; set STORAGE_BACKEND=local")
