from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class _Pending:
    size: int
    mtime: float
    stable_since: float
    deleted: bool = False


class StabilityTracker:
    """Debounce filesystem events until a file stops changing.

    A path is "ready" once its size and mtime are unchanged for
    `stable_seconds`. Repeated events for the same path simply reset its timer,
    so a multi-second FTP upload or cross-dataset copy produces one job.
    """

    def __init__(self, stable_seconds: float, clock=time.monotonic) -> None:
        self.stable_seconds = stable_seconds
        self._clock = clock
        self._pending: dict[str, _Pending] = {}
        self._lock = threading.Lock()

    def touch(self, path: str) -> None:
        now = self._clock()
        with self._lock:
            self._pending[path] = _Pending(size=-1, mtime=-1.0, stable_since=now)

    def deleted(self, path: str) -> None:
        with self._lock:
            self._pending[path] = _Pending(size=-1, mtime=-1.0, stable_since=self._clock(), deleted=True)

    def __len__(self) -> int:
        with self._lock:
            return len(self._pending)

    def poll(self) -> tuple[list[str], list[str]]:
        """Return (ready_paths, deleted_paths) and drop them from tracking."""
        now = self._clock()
        ready: list[str] = []
        gone: list[str] = []
        with self._lock:
            for path, p in list(self._pending.items()):
                try:
                    st = Path(path).stat()
                except FileNotFoundError:
                    # Moved away again or deleted before becoming stable.
                    if p.deleted or now - p.stable_since >= self.stable_seconds:
                        gone.append(path)
                        del self._pending[path]
                    continue
                except OSError:
                    continue
                if p.deleted:
                    p.deleted = False
                if st.st_size != p.size or st.st_mtime != p.mtime:
                    p.size, p.mtime, p.stable_since = st.st_size, st.st_mtime, now
                    continue
                if st.st_size > 0 and now - p.stable_since >= self.stable_seconds:
                    ready.append(path)
                    del self._pending[path]
        return ready, gone

    def requeue(self, paths: list[str]) -> None:
        for p in paths:
            self.touch(p)
