"""Local storage for uploaded files.

Files are stored under random server-generated names in a flat directory, so
nothing in a user-supplied filename can influence the path.
"""

from __future__ import annotations

import secrets
from pathlib import Path


class FileStore:
    def __init__(self, base: Path) -> None:
        self.base = base.resolve()
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not key.isalnum():
            raise ValueError("invalid storage key")
        path = (self.base / key).resolve()
        if path.parent != self.base:
            raise ValueError("invalid storage key")
        return path

    def save(self, data: bytes) -> str:
        key = secrets.token_hex(16)
        path = self._path(key)
        with path.open("xb") as f:
            f.write(data)
        path.chmod(0o600)
        return key

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str | None) -> None:
        if key:
            self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).exists()
