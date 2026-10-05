from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 4 * 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def short_hash(value: str, length: int = 12) -> str:
    return hashlib.sha1(value.encode()).hexdigest()[:length]
