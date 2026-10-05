from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import IngestSession
from app.models.enums import FileType
from app.utils.timeutil import ensure_aware


def current_session(session: Session, source: str, now: datetime | None = None) -> IngestSession:
    """Return the open upload session, starting a new one after an idle gap."""
    now = now or datetime.now(UTC)
    gap = timedelta(minutes=get_settings().ingest_session_gap_minutes)
    latest = session.scalars(
        select(IngestSession)
        .where(IngestSession.source == source)
        .order_by(IngestSession.last_activity_at.desc())
        .limit(1)
    ).first()
    if latest is not None and now - ensure_aware(latest.last_activity_at) <= gap:
        return latest
    new = IngestSession(started_at=now, last_activity_at=now, source=source)
    session.add(new)
    session.flush()
    return new


def record_file(
    ingest: IngestSession,
    file_type: str,
    size: int,
    *,
    new_photo: bool,
    camera_model: str | None,
    now: datetime | None = None,
) -> None:
    ingest.last_activity_at = now or datetime.now(UTC)
    ingest.file_count += 1
    ingest.bytes_total += size
    if new_photo:
        ingest.photo_count += 1
    if file_type in (FileType.JPEG, FileType.IMAGE):
        ingest.jpeg_count += 1
    elif file_type == FileType.RAW:
        ingest.raw_count += 1
    elif file_type == FileType.VIDEO:
        ingest.video_count += 1
    if camera_model and not ingest.camera_model:
        ingest.camera_model = camera_model
