from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from app.ai.base import AIProviderError, PhotoContext
from app.ai.registry import get_provider
from app.config import get_settings
from app.image.analysis import ALGORITHM_VERSION, analyze_image
from app.image.renditions import choose_source, rendition_for
from app.log import get_logger
from app.metadata.parser import pretty_camera
from app.models import AICritique, Photo, TechnicalAnalysis
from app.models.enums import RenditionKind
from app.observability import metrics
from app.services.events import publish_after_commit, record_event
from app.services.search import refresh_search_text
from app.utils.timeutil import ensure_aware

log = get_logger(__name__)


class AnalysisUnavailableError(RuntimeError):
    """No preview exists yet (render must run first)."""


def preview_path(photo: Photo) -> Path:
    r = rendition_for(photo, RenditionKind.PREVIEW.value)
    if r is None:
        raise AnalysisUnavailableError(f"photo {photo.id} has no preview yet")
    path = get_settings().data_root / r.path
    if not path.exists():
        raise AnalysisUnavailableError(f"preview missing on disk: {path}")
    return path


def run_technical_analysis(session: Session, photo: Photo) -> TechnicalAnalysis:
    started = time.perf_counter()
    path = preview_path(photo)
    with metrics.ANALYSIS_SECONDS.time(), Image.open(path) as img:
        result = analyze_image(img)
    row = photo.analysis or TechnicalAnalysis(photo_id=photo.id, algorithm_version=ALGORITHM_VERSION)
    for key, value in result.as_dict().items():
        setattr(row, key, value)
    source = choose_source(photo)
    row.source = source.file_type if source else None
    row.algorithm_version = ALGORITHM_VERSION
    row.duration_ms = int((time.perf_counter() - started) * 1000)
    row.analyzed_at = datetime.now(UTC)
    if photo.analysis is None:
        photo.analysis = row
    metrics.inc("analysis_runs")
    publish_after_commit(session, "photo.analyzed", {"photo_id": photo.id})
    log.info(
        "photo_analyzed",
        category="ANALYSIS",
        photo_id=str(photo.id),
        sharpness=result.sharpness_score,
        faces=result.face_count,
        duration_ms=row.duration_ms,
    )
    return row


def build_context(photo: Photo) -> PhotoContext:
    extra = photo.extra or {}
    a = photo.analysis
    technical = {}
    if a is not None:
        technical = {
            k: getattr(a, k)
            for k in (
                "sharpness_score",
                "sharpness_label",
                "brightness",
                "contrast",
                "highlight_clipping_percent",
                "shadow_clipping_percent",
                "exposure_label",
                "exposure_assessment",
                "face_count",
                "eye_count",
                "faces",
                "dynamic_range_ev",
            )
        }
    ct = ensure_aware(photo.capture_time)
    return PhotoContext(
        photo_id=str(photo.id),
        filename=photo.base_filename,
        camera=pretty_camera(photo.camera_make, photo.camera_model),
        lens=photo.lens_model,
        focal_length=photo.focal_length,
        focal_length_35mm=photo.focal_length_35mm,
        aperture=photo.aperture,
        shutter_speed=photo.shutter_speed,
        iso=photo.iso,
        exposure_compensation=photo.exposure_compensation,
        exposure_program=photo.exposure_program,
        focus_mode=photo.focus_mode,
        af_area_mode=photo.af_area_mode,
        vibration_reduction=extra.get("vibration_reduction"),
        subject_detection=extra.get("subject_detection"),
        focus_distance=extra.get("focus_distance"),
        capture_time=ct.isoformat() if ct else None,
        technical=technical,
    )


def run_ai_critique(session: Session, photo: Photo, provider_name: str | None = None) -> AICritique | None:
    provider = get_provider(provider_name)
    if provider is None:
        return None
    started = time.perf_counter()
    critique = AICritique(photo_id=photo.id, provider=provider.name)
    try:
        with metrics.AI_SECONDS.time():
            result = provider.analyze_photo(build_context(photo), preview_path(photo))
        for key in (
            "scene",
            "subject",
            "description",
            "composition",
            "technical",
            "issues",
            "suggestions",
            "tags",
            "aesthetic_score",
            "confidence",
            "model_name",
            "model_version",
        ):
            setattr(critique, key, getattr(result, key))
        critique.status = "succeeded"
        if result.scene:
            photo.scene = result.scene[:64]
        metrics.inc("ai_runs", provider=provider.name, status="succeeded")
    except AIProviderError as exc:
        critique.status, critique.error = "failed", str(exc)
        metrics.inc("ai_runs", provider=provider.name, status="failed")
        record_event(
            session,
            "AI",
            "ai_failed",
            f"AI critique failed for {photo.base_filename}: {exc}",
            level="error",
            photo_id=photo.id,
        )
        log.warning("ai_failed", category="AI", photo_id=str(photo.id), error=str(exc))
    critique.duration_ms = int((time.perf_counter() - started) * 1000)
    session.add(critique)
    session.flush()
    refresh_search_text(session, photo)
    publish_after_commit(session, "photo.analyzed", {"photo_id": photo.id, "ai": True})
    return critique
