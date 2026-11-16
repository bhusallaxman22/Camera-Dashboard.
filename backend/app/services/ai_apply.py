"""Map a successful AI critique onto in-app culling fields (DB only)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.ai.base import AIResult
from app.log import get_logger
from app.models import Photo
from app.services.photos import merge_ai_tags

log = get_logger(__name__)

CONFIDENCE_FLOOR = 0.4


def rating_from_aesthetic(score: float | None) -> int | None:
    """Map 0–10 aesthetic score to 0–5 stars."""
    if score is None:
        return None
    return max(0, min(5, round(float(score) / 2.0)))


def apply_critique_to_photo(session: Session, photo: Photo, result: AIResult) -> dict[str, Any]:
    """Fill empty culling fields from a critique. Never overwrites user rating/flag/favorite."""
    applied: dict[str, Any] = {}
    confident = result.confidence is None or result.confidence >= CONFIDENCE_FLOOR

    if confident and photo.rating == 0:
        stars = rating_from_aesthetic(result.aesthetic_score)
        if stars is not None and stars > 0:
            photo.rating = stars
            applied["rating"] = stars

    if confident and not photo.needs_edit and result.issues:
        photo.needs_edit = True
        applied["needs_edit"] = True

    tag_names = list(result.tags or [])
    if result.scene:
        tag_names.append(result.scene)
    tag_delta = merge_ai_tags(session, photo, tag_names)
    if tag_delta["added"] or tag_delta["removed"]:
        applied["tags_added"] = tag_delta["added"]
        applied["tags_removed"] = tag_delta["removed"]

    if applied:
        log.info(
            "ai_culling_applied",
            category="AI",
            photo_id=str(photo.id),
            applied=applied,
            confidence=result.confidence,
        )
    return applied
