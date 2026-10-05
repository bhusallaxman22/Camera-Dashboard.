"""File -> Photo ingestion. Strictly read-only with respect to originals."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import advisory_lock
from app.log import get_logger
from app.metadata.exiftool import ExifDump, ExifToolError, read_metadata
from app.metadata.parser import ParsedMetadata, parse_metadata
from app.models import Photo, PhotoFile
from app.models.enums import FileType, MediaType, ProcessingStatus
from app.services import sessions
from app.services.events import publish_after_commit, record_event
from app.services.pairing import DISPLAY_TYPES, PairingInput, file_role_flags, find_pair
from app.services.search import refresh_search_text
from app.utils.hashing import sha256_file
from app.utils.paths import (
    base_name,
    classify,
    date_from_directory,
    mime_type_for,
    relative_to_root,
    resolve_under_roots,
)
from app.utils.timeutil import ensure_aware, from_timestamp

log = get_logger(__name__)

# Fields where the display file (what the user actually sees) wins over RAW.
DISPLAY_PREFERRED_FIELDS = {"image_width", "image_height"}


class FileNotReadyError(RuntimeError):
    """File is empty or still being written; the job should be retried later."""


@dataclass(slots=True)
class IngestOutcome:
    # created | paired | reupload | updated | unchanged | moved | duplicate | skipped | missing
    status: str
    path: str
    photo_id: uuid.UUID | None = None
    file_id: uuid.UUID | None = None
    file_type: str | None = None
    pair_reason: str | None = None
    warnings: list[str] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def changed(self) -> bool:
        return self.status in {"created", "paired", "reupload", "updated", "moved"}


def apply_metadata(photo: Photo, parsed: ParsedMetadata, file_type: str, is_new: bool) -> None:
    """Merge parsed metadata into the Photo.

    RAW maker notes are the richest source, so a RAW overwrites values that came
    from a JPEG; a JPEG only fills gaps left by a RAW (except display dimensions).
    """
    fields = parsed.as_photo_fields()
    extra = fields.pop("extra") or {}
    is_raw = file_type == FileType.RAW
    is_display = file_type in DISPLAY_TYPES
    for key, value in fields.items():
        if value is None:
            continue
        current = getattr(photo, key)
        if (
            is_new
            or current is None
            or (is_raw and key not in DISPLAY_PREFERRED_FIELDS)
            or (is_display and key in DISPLAY_PREFERRED_FIELDS)
        ):
            setattr(photo, key, value)
    merged = dict(photo.extra or {})
    for k, v in extra.items():
        if is_raw or k not in merged:
            merged[k] = v
    photo.extra = merged


def _read_metadata(path: Path, warnings: list[str]) -> tuple[ExifDump, ParsedMetadata]:
    try:
        dump = read_metadata(path)
        return dump, parse_metadata(dump)
    except ExifToolError as exc:
        warnings.append(f"exiftool: {exc}")
        log.warning("exif_failed", category="EXIF", path=str(path), error=str(exc))
        return ExifDump(), ParsedMetadata()


def _mark_missing(session: Session, pf: PhotoFile) -> None:
    pf.exists = False
    photo = session.get(Photo, pf.photo_id)
    if photo is not None:
        for k, v in file_role_flags(photo.files).items():
            setattr(photo, k, v)


def ingest_path(
    session: Session,
    path: Path | str,
    *,
    source: str = "live",
    force: bool = False,
    now: datetime | None = None,
) -> IngestOutcome:
    started = time.perf_counter()
    settings = get_settings()
    now = now or datetime.now(UTC)

    resolved = resolve_under_roots(path, list(settings.media_roots.values()))
    abs_path = str(resolved)
    outcome = IngestOutcome(status="skipped", path=abs_path)

    file_type = classify(resolved)
    if file_type is None:
        return outcome
    outcome.file_type = file_type.value

    existing = session.scalars(select(PhotoFile).where(PhotoFile.absolute_path == abs_path)).first()
    try:
        st = resolved.stat()
    except FileNotFoundError:
        if existing is not None and existing.exists:
            _mark_missing(session, existing)
            outcome.status, outcome.photo_id, outcome.file_id = "missing", existing.photo_id, existing.id
        return outcome

    size, mtime = st.st_size, from_timestamp(st.st_mtime)
    if size == 0:
        raise FileNotReadyError(f"{abs_path} is empty")
    if (now - mtime).total_seconds() < settings.file_stable_seconds and source == "live":
        raise FileNotReadyError(f"{abs_path} was modified too recently")

    if (
        existing is not None
        and not force
        and existing.exists
        and existing.file_size == size
        and abs((ensure_aware(existing.modification_time) - mtime).total_seconds()) < 1
    ):
        existing.last_seen_at = now
        outcome.status, outcome.photo_id, outcome.file_id = "unchanged", existing.photo_id, existing.id
        return outcome

    checksum = sha256_file(resolved)
    rel_path = relative_to_root(resolved, settings.photo_root)

    if existing is not None:
        dump, parsed = _read_metadata(resolved, outcome.warnings)
        existing.file_size, existing.modification_time, existing.checksum = size, mtime, checksum
        existing.exists, existing.last_seen_at = True, now
        existing.width, existing.height = parsed.image_width, parsed.image_height
        existing.exif = dump.to_json()
        photo = session.get(Photo, existing.photo_id)
        assert photo is not None
        apply_metadata(photo, parsed, file_type, is_new=False)
        for k, v in file_role_flags(photo.files).items():
            setattr(photo, k, v)
        refresh_search_text(session, photo)
        outcome.status, outcome.photo_id, outcome.file_id = "updated", photo.id, existing.id
        return _finish(outcome, started)

    dup = session.scalars(
        select(PhotoFile).where(PhotoFile.checksum == checksum, PhotoFile.duplicate_of_id.is_(None))
    ).first()
    if dup is not None:
        if not Path(dup.absolute_path).exists():
            # Same bytes, old path gone: the file was moved/renamed on the NAS.
            old = dup.absolute_path
            dup.absolute_path, dup.relative_path = abs_path, rel_path
            dup.filename, dup.modification_time = resolved.name, mtime
            dup.exists, dup.last_seen_at = True, now
            photo = session.get(Photo, dup.photo_id)
            if photo is not None:
                for k, v in file_role_flags(photo.files).items():
                    setattr(photo, k, v)
            record_event(
                session,
                "INGEST",
                "file_moved",
                f"{resolved.name} moved",
                photo_id=dup.photo_id,
                data={"from": old, "to": abs_path},
            )
            outcome.status, outcome.photo_id, outcome.file_id = "moved", dup.photo_id, dup.id
            return _finish(outcome, started)

        copy = PhotoFile(
            photo_id=dup.photo_id,
            file_type=file_type.value,
            absolute_path=abs_path,
            relative_path=rel_path,
            filename=resolved.name,
            extension=resolved.suffix.lower().lstrip("."),
            mime_type=mime_type_for(resolved),
            file_size=size,
            checksum=checksum,
            modification_time=mtime,
            width=dup.width,
            height=dup.height,
            duplicate_of_id=dup.id,
            exists=True,
            last_seen_at=now,
            exif={},
        )
        session.add(copy)
        session.flush()
        record_event(
            session,
            "INGEST",
            "duplicate_file",
            f"{resolved.name} is a byte-identical copy of {dup.filename}",
            level="warning",
            photo_id=dup.photo_id,
            data={"path": abs_path, "original": dup.absolute_path},
        )
        outcome.status, outcome.photo_id, outcome.file_id = "duplicate", dup.photo_id, copy.id
        return _finish(outcome, started)

    dump, parsed = _read_metadata(resolved, outcome.warnings)
    base = base_name(resolved)
    base_key = base.lower()

    # Serialise concurrent workers handling DSC_1234.JPG and DSC_1234.NEF.
    advisory_lock(session, f"pair:{base_key}")
    decision = find_pair(
        session,
        PairingInput(
            base_key=base_key,
            file_type=file_type.value,
            capture_time=parsed.capture_time,
            camera_serial=parsed.camera_serial,
            camera_model=parsed.camera_model,
            shutter_count=parsed.shutter_count,
            directory_date=date_from_directory(resolved),
            mtime=mtime,
        ),
        settings.pair_window_seconds,
    )
    is_new = decision.photo is None
    if is_new:
        photo = Photo(
            base_filename=base,
            base_key=base_key,
            media_type=(MediaType.VIDEO if file_type == FileType.VIDEO else MediaType.STILL).value,
            imported_at=now,
            processing_status=ProcessingStatus.PENDING.value,
            extra={},
        )
        session.add(photo)
    else:
        photo = decision.photo
        assert photo is not None

    pf = PhotoFile(
        file_type=file_type.value,
        absolute_path=abs_path,
        relative_path=rel_path,
        filename=resolved.name,
        extension=resolved.suffix.lower().lstrip("."),
        mime_type=mime_type_for(resolved),
        file_size=size,
        checksum=checksum,
        modification_time=mtime,
        width=parsed.image_width,
        height=parsed.image_height,
        exists=True,
        last_seen_at=now,
        exif=dump.to_json(),
    )
    photo.files.append(pf)
    reupload_of = decision.reupload_of
    # Interrupted uploads leave short copies, so the largest copy is the complete one.
    supersedes = reupload_of is not None and size > reupload_of.file_size
    apply_metadata(photo, parsed, file_type, is_new=is_new or (supersedes and not photo.has_raw))
    for k, v in file_role_flags(photo.files).items():
        setattr(photo, k, v)
    if photo.capture_time is None and is_new:
        # Last resort so the photo still sorts sensibly.
        photo.capture_time = mtime

    ingest_session = sessions.current_session(session, source, now)
    sessions.record_file(
        ingest_session,
        file_type.value,
        size,
        new_photo=is_new,
        camera_model=photo.camera_model,
        now=now,
    )
    if is_new:
        photo.ingest_session_id = ingest_session.id
    session.flush()
    refresh_search_text(session, photo)

    outcome.photo_id, outcome.file_id, outcome.pair_reason = photo.id, pf.id, decision.reason
    if reupload_of is not None:
        winner, loser = (pf, reupload_of) if supersedes else (reupload_of, pf)
        for f in photo.files:
            if f.duplicate_of_id == loser.id:
                f.duplicate_of_id = winner.id
        loser.duplicate_of_id = winner.id
        session.flush()
        outcome.status = "reupload"
        record_event(
            session,
            "INGEST",
            "file_reuploaded",
            f"{resolved.name} is a re-upload of {reupload_of.filename}; "
            f"using {winner.filename} ({winner.file_size:,} bytes, other copy {loser.file_size:,})",
            level="warning",
            photo_id=photo.id,
            data={"path": abs_path, "primary": winner.absolute_path, "reason": decision.reason},
            broadcast=source == "live",
        )
        if supersedes:
            publish_after_commit(session, "photo.updated", {"photo_id": photo.id, "reason": "reupload"})
    elif is_new:
        outcome.status = "created"
        record_event(
            session,
            "INGEST",
            "photo_ingested",
            f"New capture {base} ({file_type.value})",
            photo_id=photo.id,
            data={"filename": resolved.name, "file_type": file_type.value, "source": source},
            broadcast=source == "live",
        )
        publish_after_commit(session, "photo.created", {"photo_id": photo.id, "filename": base})
    else:
        outcome.status = "paired"
        record_event(
            session,
            "PAIR",
            "photo_paired",
            f"{resolved.name} paired with {base} ({decision.reason})",
            photo_id=photo.id,
            data={"filename": resolved.name, "reason": decision.reason, "score": decision.score},
            broadcast=source == "live",
        )
        publish_after_commit(session, "photo.updated", {"photo_id": photo.id, "reason": "paired"})
    if decision.reason.startswith("rejected:"):
        log.info("pair_rejected", category="PAIR", path=abs_path, reason=decision.reason)
    return _finish(outcome, started)


def _finish(outcome: IngestOutcome, started: float) -> IngestOutcome:
    outcome.duration_ms = int((time.perf_counter() - started) * 1000)
    log.info(
        "file_ingested",
        category="PAIR" if outcome.status == "paired" else "INGEST",
        status=outcome.status,
        path=outcome.path,
        photo_id=str(outcome.photo_id) if outcome.photo_id else None,
        reason=outcome.pair_reason,
        duration_ms=outcome.duration_ms,
    )
    return outcome
