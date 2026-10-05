"""Decide which logical Photo a newly discovered file belongs to.

A Nikon RAW+JPEG capture produces `DSC_1234.NEF` and `DSC_1234.JPG` that the
FTP sorter places in different trees, possibly seconds apart and in any order.
Filename alone is not trustworthy (the 4-digit counter rolls over every 10k
frames, and a second body would reuse names), so a candidate Photo sharing the
base filename must also agree on:

1. camera identity (serial, else model) when both sides know it,
2. shutter count when both sides know it (exact per-exposure identity),
3. capture time within PAIR_WINDOW_SECONDS, or — when a side lacks EXIF — the
   sorter's YYYY/MM/DD directory date plus file mtimes within a few minutes,
4. a free slot: a Photo holds at most one live display file and one live RAW.

When the slot is already filled by a file that agrees on 1-3, the new file is a
re-upload of the same exposure (the camera retried an interrupted FTP transfer,
which usually leaves a truncated first copy behind). It joins that Photo as an
alternate copy instead of becoming a second Photo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Photo, PhotoFile
from app.models.enums import FileType, MediaType
from app.utils.paths import date_from_directory
from app.utils.timeutil import ensure_aware

DISPLAY_TYPES = {FileType.JPEG.value, FileType.IMAGE.value}
MTIME_FALLBACK_SECONDS = 600


@dataclass(slots=True)
class PairingInput:
    base_key: str
    file_type: str
    capture_time: datetime | None
    camera_serial: str | None
    camera_model: str | None
    shutter_count: int | None
    directory_date: date | None
    mtime: datetime


@dataclass(slots=True)
class PairingDecision:
    photo: Photo | None
    score: float
    reason: str
    # Set when the new file is another copy of a file the Photo already has.
    reupload_of: PhotoFile | None = None


def slot_holder(photo: Photo, file_type: str) -> PhotoFile | None:
    """The live primary file occupying the slot `file_type` would fill."""
    for f in photo.files:
        if not f.exists or f.duplicate_of_id is not None:
            continue
        if f.file_type == file_type or (file_type in DISPLAY_TYPES and f.file_type in DISPLAY_TYPES):
            return f
    return None


def _has_exif_identity(photo: Photo) -> bool:
    return bool(photo.camera_serial or photo.camera_model) or photo.shutter_count is not None


def score_candidate(
    photo: Photo, item: PairingInput, window_seconds: float, *, ignore_slot: bool = False
) -> tuple[float, str]:
    """Return (score, reason). Score <= 0 means "not the same capture"."""
    if not ignore_slot and slot_holder(photo, item.file_type) is not None:
        return 0.0, "slot_taken"

    if item.camera_serial and photo.camera_serial and item.camera_serial != photo.camera_serial:
        return 0.0, "serial_mismatch"
    if item.camera_model and photo.camera_model and item.camera_model != photo.camera_model:
        return 0.0, "model_mismatch"

    if item.shutter_count is not None and photo.shutter_count is not None:
        if item.shutter_count != photo.shutter_count:
            return 0.0, "shutter_count_mismatch"
        shutter_match = True
    else:
        shutter_match = False

    # Without EXIF the stored capture time is only the file mtime.
    photo_time = ensure_aware(photo.capture_time) if _has_exif_identity(photo) else None
    if item.capture_time and photo_time:
        delta = abs((item.capture_time - photo_time).total_seconds())
        if delta > window_seconds:
            return 0.0, f"time_mismatch:{delta:.1f}s"
        score = 80.0 - min(delta, window_seconds) * 10
        if shutter_match:
            score += 20
        return score, "capture_time" + ("+shutter_count" if shutter_match else "")

    if shutter_match:
        return 90.0, "shutter_count"

    # No usable EXIF time on one side: fall back to sorter date + file mtimes.
    photo_dates = {date_from_directory(f.absolute_path) for f in photo.files}
    if item.directory_date is None or item.directory_date not in photo_dates:
        return 0.0, "directory_date_mismatch"
    mtimes = [ensure_aware(f.modification_time) for f in photo.files]
    if not any(m and abs((item.mtime - m).total_seconds()) <= MTIME_FALLBACK_SECONDS for m in mtimes):
        return 0.0, "mtime_mismatch"
    return 10.0, "directory_date+mtime"


def find_pair(session: Session, item: PairingInput, window_seconds: float) -> PairingDecision:
    if item.file_type == FileType.VIDEO.value:
        return PairingDecision(None, 0.0, "video_never_pairs")
    candidates = session.scalars(
        select(Photo)
        .where(Photo.base_key == item.base_key, Photo.media_type == MediaType.STILL.value)
        .options(selectinload(Photo.files))
    ).all()
    best: PairingDecision = PairingDecision(None, 0.0, "no_candidates" if not candidates else "")
    reasons: list[str] = []
    for photo in candidates:
        score, reason = score_candidate(photo, item, window_seconds)
        reasons.append(reason)
        if score > best.score:
            best = PairingDecision(photo, score, reason)
    if best.photo is not None or not candidates:
        return best

    for photo in candidates:
        holder = slot_holder(photo, item.file_type)
        if holder is None:
            continue
        score, reason = score_candidate(photo, item, window_seconds, ignore_slot=True)
        if score > best.score:
            best = PairingDecision(photo, score, f"reupload:{reason}", reupload_of=holder)
    if best.photo is None:
        best.reason = "rejected:" + ",".join(sorted(set(reasons)))
    return best


def file_role_flags(files: list[PhotoFile]) -> dict[str, bool]:
    live = [f for f in files if f.exists]
    return {
        "has_jpeg": any(f.file_type in DISPLAY_TYPES for f in live),
        "has_raw": any(f.file_type == FileType.RAW.value for f in live),
        "has_video": any(f.file_type == FileType.VIDEO.value for f in live),
    }
