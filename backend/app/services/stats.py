from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.metadata.parser import pretty_camera
from app.models import IngestSession, Photo, PhotoFile
from app.schemas.system import CameraStatus, StatsOut, TodayStats, TotalStats
from app.services.photos import summary_loaders, to_summary
from app.utils.timeutil import ensure_aware, start_of_local_day


def camera_status(session: Session, now: datetime | None = None) -> CameraStatus:
    now = now or datetime.now(UTC)
    s = get_settings()
    last = session.scalars(
        select(IngestSession)
        .where(IngestSession.source == "live")
        .order_by(IngestSession.last_activity_at.desc())
        .limit(1)
    ).first()
    if last is None:
        return CameraStatus(
            state="never",
            last_upload_at=None,
            session_started_at=None,
            session_files=0,
            session_photos=0,
            session_bytes=0,
            camera=None,
        )
    last_at = ensure_aware(last.last_activity_at)
    state = "receiving" if now - last_at <= timedelta(minutes=s.camera_online_minutes) else "idle"
    return CameraStatus(
        state=state,
        last_upload_at=last_at,
        session_started_at=ensure_aware(last.started_at),
        session_files=last.file_count,
        session_photos=last.photo_count,
        session_bytes=last.bytes_total,
        camera=pretty_camera(None, last.camera_model),
    )


def compute_stats(session: Session, recent_limit: int = 24) -> StatsOut:
    day_start = start_of_local_day()

    def file_counts(*where) -> dict[str, tuple[int, int]]:
        rows = session.execute(
            select(PhotoFile.file_type, func.count(PhotoFile.id), func.coalesce(func.sum(PhotoFile.file_size), 0))
            .join(Photo, Photo.id == PhotoFile.photo_id)
            .where(PhotoFile.exists.is_(True), PhotoFile.duplicate_of_id.is_(None), *where)
            .group_by(PhotoFile.file_type)
        ).all()
        return {t: (int(c), int(b)) for t, c, b in rows}

    today_files = file_counts(Photo.capture_time >= day_start)
    today_photo_row = session.execute(
        select(
            func.count(Photo.id),
            func.coalesce(func.sum(case((Photo.flag == "pick", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Photo.flag == "reject", 1), else_=0)), 0),
        ).where(Photo.capture_time >= day_start, Photo.media_type == "still")
    ).one()
    all_files = file_counts()
    totals_row = session.execute(
        select(
            func.count(Photo.id),
            func.coalesce(func.sum(case((Photo.favorite.is_(True), 1), else_=0)), 0),
            func.coalesce(func.sum(case((Photo.flag == "reject", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Photo.processing_status == "pending", 1), else_=0)), 0),
            func.coalesce(func.sum(case((Photo.processing_status == "error", 1), else_=0)), 0),
        )
    ).one()

    def n(d: dict[str, tuple[int, int]], *types: str) -> int:
        return sum(d.get(t, (0, 0))[0] for t in types)

    def b(d: dict[str, tuple[int, int]]) -> int:
        return sum(v[1] for v in d.values())

    recent = session.scalars(
        select(Photo)
        .order_by(Photo.capture_time.desc().nulls_last(), Photo.base_filename.desc())
        .limit(recent_limit)
        .options(*summary_loaders())
    ).all()

    return StatsOut(
        camera=camera_status(session),
        today=TodayStats(
            photos=int(today_photo_row[0]),
            raw_files=n(today_files, "raw"),
            jpeg_files=n(today_files, "jpeg", "image"),
            videos=n(today_files, "video"),
            bytes=b(today_files),
            picks=int(today_photo_row[1]),
            rejects=int(today_photo_row[2]),
        ),
        totals=TotalStats(
            photos=int(totals_row[0]),
            raw_files=n(all_files, "raw"),
            jpeg_files=n(all_files, "jpeg", "image"),
            videos=n(all_files, "video"),
            bytes=b(all_files),
            favorites=int(totals_row[1]),
            rejected=int(totals_row[2]),
            pending=int(totals_row[3]),
            errors=int(totals_row[4]),
        ),
        latest_photo_id=recent[0].id if recent else None,
        recent=[to_summary(p, 512) for p in recent],
    )
