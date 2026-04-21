from abc import ABC, abstractmethod


class StorageBackend(ABC):
    @abstractmethod
    def save(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """Persist object; return storage key."""

    @abstractmethod
    def read(self, key: str) -> bytes:
        """Read object bytes."""
