"""Writes streaming WS binary frames to disk with size cap."""
from __future__ import annotations

from pathlib import Path


class MaxSizeExceeded(Exception):
    pass


class UploadWriter:
    def __init__(self, target: Path, *, max_bytes: int):
        self.target = target
        self.max_bytes = max_bytes
        self.total_bytes = 0
        target.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(target, "wb")

    def write(self, chunk: bytes) -> None:
        if self.total_bytes + len(chunk) > self.max_bytes:
            raise MaxSizeExceeded(
                f"upload exceeds {self.max_bytes} bytes"
            )
        self._fh.write(chunk)
        self.total_bytes += len(chunk)

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()
