"""Filesystem scanning / reconciliation (read-only walk of the media roots)."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.log import get_logger
from app.models import Photo, PhotoFile
from app.services.pairing import file_role_flags
from app.utils.paths import classify, is_within
from app.utils.timeutil import ensure_aware

log = get_logger(__name__)


@dataclass(slots=True)
class ScanPlan:
    to_ingest: list[Path] = field(default_factory=list)
    unchanged: int = 0
    missing: list[str] = field(default_factory=list)
    skipped_recent: int = 0
    roots_unavailable: list[str] = field(default_factory=list)
    total_seen: int = 0


def iter_media_files(root: Path) -> Iterator[Path]:
    """Recursive walk; skips hidden directories and never follows symlinks."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith((".", "@")))
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if classify(p) is not None:
                yield p


def plan_scan(session: Session, roots: list[Path] | None = None, *, now: float | None = None) -> ScanPlan:
    """Compare disk with the DB and list files that need (re)ingesting.

    Unchanged files (same path, size, mtime) are not re-queued, so repeated
    scans are cheap and never duplicate records.
    """
    settings = get_settings()
    roots = roots or list(settings.media_roots.values())
    now = now or time.time()
    plan = ScanPlan()

    known: dict[str, tuple[int, float, bool]] = {
        path: (size, ensure_aware(mtime).timestamp(), exists)
        for path, size, mtime, exists in session.execute(
            select(
                PhotoFile.absolute_path,
                PhotoFile.file_size,
                PhotoFile.modification_time,
                PhotoFile.exists,
            )
        )
    }
    seen: set[str] = set()
    available_roots: list[Path] = []
    for root in roots:
        if not root.is_dir():
            plan.roots_unavailable.append(str(root))
            log.warning("scan_root_unavailable", category="INGEST", root=str(root))
            continue
        root = root.resolve()
        available_roots.append(root)
        for path in iter_media_files(root):
            plan.total_seen += 1
            resolved = str(path.resolve())
            seen.add(resolved)
            try:
                st = path.stat()
            except OSError:
                continue
            if now - st.st_mtime < settings.file_stable_seconds:
                plan.skipped_recent += 1  # the watcher will pick it up once stable
                continue
            k = known.get(resolved)
            if k and k[2] and k[0] == st.st_size and abs(k[1] - st.st_mtime) < 1:
                plan.unchanged += 1
            else:
                plan.to_ingest.append(path)

    # Only flag files missing if their root was readable (an unmounted share
    # must not mark the whole library missing).
    for path, (_, _, exists) in known.items():
        if exists and path not in seen and any(is_within(Path(path), r) for r in available_roots):
            plan.missing.append(path)
    return plan


def mark_missing(session: Session, paths: list[str]) -> int:
    if not paths:
        return 0
    files = session.scalars(select(PhotoFile).where(PhotoFile.absolute_path.in_(paths))).all()
    photo_ids = set()
    for f in files:
        f.exists = False
        photo_ids.add(f.photo_id)
    session.flush()
    for photo in session.scalars(select(Photo).where(Photo.id.in_(photo_ids))).all():
        for k, v in file_role_flags(photo.files).items():
            setattr(photo, k, v)
    return len(files)


def verify_files(session: Session) -> dict[str, int]:
    """Re-check existence of every tracked file (marks missing / restored)."""
    missing = restored = 0
    now = datetime.now(UTC)
    for f in session.scalars(select(PhotoFile)).all():
        present = Path(f.absolute_path).is_file()
        if present:
            f.last_seen_at = now
        if present != f.exists:
            f.exists = present
            missing += not present
            restored += present
            photo = session.get(Photo, f.photo_id)
            if photo is not None:
                session.flush()
                for k, v in file_role_flags(photo.files).items():
                    setattr(photo, k, v)
    return {"missing": missing, "restored": restored}
