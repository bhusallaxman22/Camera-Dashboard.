"""High-level processing steps shared by RQ tasks and the inline CLI.

filesystem event -> ingest (EXIF + pairing) -> render (preview/thumbs) + burst
-> technical analysis -> optional AI critique. Each step commits on its own so
a failure later in the chain never loses earlier work.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import session_scope
from app.image.loader import DecodeError
from app.image.renditions import render_photo
from app.log import get_logger
from app.models import Photo
from app.models.enums import ProcessingStatus
from app.observability import metrics
from app.services.analysis import (
    AnalysisUnavailableError,
    preview_path,
    run_ai_critique,
    run_technical_analysis,
)
from app.services.bursts import assign_burst
from app.services.events import publish_after_commit, record_event
from app.services.ingest import IngestOutcome, ingest_path

log = get_logger(__name__)


@dataclass(slots=True)
class StepResult:
    photo_id: str | None = None
    status: str = "ok"
    details: dict[str, Any] = field(default_factory=dict)
    needs_analysis: bool = False


def _load(session, photo_id: uuid.UUID | str) -> Photo | None:
    return session.get(
        Photo,
        uuid.UUID(str(photo_id)),
        options=[selectinload(Photo.files), selectinload(Photo.renditions)],
    )


def ingest_step(path: str | Path, source: str = "live", force: bool = False) -> IngestOutcome:
    with metrics.INGEST_SECONDS.time(), session_scope() as s:
        outcome = ingest_path(s, path, source=source, force=force)
    metrics.inc("ingest_jobs", status=outcome.status)
    return outcome


def render_step(photo_id: uuid.UUID | str, force: bool = False) -> StepResult:
    """Generate renditions, assign burst, mark the photo ready."""
    with session_scope() as s:
        photo = _load(s, photo_id)
        if photo is None:
            return StepResult(str(photo_id), "missing_photo")
        try:
            res = render_photo(s, photo, force=force)
        except DecodeError as exc:
            photo.processing_status = ProcessingStatus.ERROR.value
            photo.processing_error = str(exc)
            record_event(
                s,
                "THUMBNAIL",
                "render_failed",
                f"Could not render {photo.base_filename}: {exc}",
                level="error",
                photo_id=photo.id,
            )
            publish_after_commit(s, "photo.updated", {"photo_id": photo.id, "reason": "error"})
            # Corrupt originals will not heal on retry; surface it and stop.
            return StepResult(str(photo.id), "render_failed", {"error": str(exc)})
        assign_burst(s, photo)
        photo.processing_status = ProcessingStatus.READY.value
        photo.processing_error = None
        if res.generated:
            publish_after_commit(s, "photo.updated", {"photo_id": photo.id, "reason": "rendered"})
        needs = res.generated or photo.analysis is None
        return StepResult(
            str(photo.id),
            "rendered" if res.generated else "current",
            {"source": res.source, "duration_ms": res.duration_ms},
            needs_analysis=needs,
        )


def _ensure_preview(photo_id: uuid.UUID | str) -> str | None:
    """Re-render a preview that is recorded but gone from disk (e.g. /data was reset or moved
    while the database kept its rows). Returns why it is still unavailable, or None."""
    with session_scope() as s:
        photo = _load(s, photo_id)
        if photo is None:
            return "photo not found"
        try:
            preview_path(photo)
            return None
        except AnalysisUnavailableError:
            pass
    render = render_step(photo_id)
    if render.status == "render_failed":
        return render.details.get("error", "render failed")
    with session_scope() as s:
        photo = _load(s, photo_id)
        try:
            preview_path(photo)
        except AnalysisUnavailableError as exc:
            return str(exc)
    log.info("preview_regenerated", category="THUMBNAIL", photo_id=str(photo_id))
    return None


def analyze_step(photo_id: uuid.UUID | str, with_ai: bool | None = None) -> StepResult:
    """Technical analysis; runs the local critique inline when configured."""
    settings = get_settings()
    if err := _ensure_preview(photo_id):
        return StepResult(str(photo_id), "no_preview", {"error": err})
    with session_scope() as s:
        photo = _load(s, photo_id)
        if photo is None:
            return StepResult(str(photo_id), "missing_photo")
        try:
            a = run_technical_analysis(s, photo)
        except AnalysisUnavailableError as exc:
            return StepResult(str(photo.id), "no_preview", {"error": str(exc)})
        details = {"sharpness": a.sharpness_score, "faces": a.face_count}

    run_ai = settings.ai_auto_analyze if with_ai is None else with_ai
    remote = settings.ai_provider not in ("local", "none")
    if run_ai and settings.ai_provider == "local":
        ai_step(photo_id)
    return StepResult(str(photo_id), "analyzed", details, needs_analysis=run_ai and remote)


def ai_step(photo_id: uuid.UUID | str, provider: str | None = None) -> StepResult:
    if err := _ensure_preview(photo_id):
        log.warning("ai_skipped_no_preview", category="AI", photo_id=str(photo_id), error=err)
        return StepResult(str(photo_id), "no_preview", {"error": err})
    with session_scope() as s:
        photo = _load(s, photo_id)
        if photo is None:
            return StepResult(str(photo_id), "missing_photo")
        critique = run_ai_critique(s, photo, provider)
        if critique is None:
            return StepResult(str(photo.id), "ai_disabled")
        return StepResult(str(photo.id), critique.status, {"provider": critique.provider, "error": critique.error})


def process_file_inline(path: str | Path, source: str = "scan", force: bool = False) -> IngestOutcome:
    """Synchronous full pipeline (CLI --inline, tests)."""
    outcome = ingest_step(path, source=source, force=force)
    if outcome.photo_id and outcome.status not in ("skipped", "missing"):
        r = render_step(outcome.photo_id)
        if r.needs_analysis:
            a = analyze_step(outcome.photo_id)
            if a.needs_analysis:
                ai_step(outcome.photo_id)
    return outcome
