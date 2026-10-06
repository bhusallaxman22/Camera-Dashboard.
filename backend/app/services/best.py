"""Rank the strongest frames in a period: AI aesthetic estimate blended with
measured sharpness and eye focus, one frame per burst, rejects excluded."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AICritique, Photo, TechnicalAnalysis
from app.services.photos import summary_loaders
from app.services.stats import camera_status
from app.utils.timeutil import start_of_local_day

Period = Literal["session", "today", "7d", "all"]

W_AESTHETIC = 0.6
# With a face in frame, eye focus outweighs whole-frame sharpness: shallow depth of
# field is deliberate in portraits. Without one, sharpness takes the whole share.
W_SHARPNESS_WITH_EYES, W_EYES = 0.1, 0.3
W_SHARPNESS_ALONE = 0.4
# Unscored frames sit at a neutral 5/10 so a real AI rating moves a frame up or down;
# dropping the term instead would let any sharp unscored frame outrank every rated one.
AESTHETIC_PRIOR = 50.0


@dataclass(slots=True)
class Candidate:
    photo_id: uuid.UUID
    burst_group_id: uuid.UUID | None
    sharpness: float | None
    sharpness_peak: float | None
    faces: list[dict[str, Any]] | None
    aesthetic: float | None
    rating: int
    flag: str
    favorite: bool


@dataclass(slots=True)
class Ranked:
    photo_id: uuid.UUID
    score: float
    aesthetic: float | None
    eye_sharpness: float | None
    # The 0–100 sharpness score saturates; the raw peak separates frames tied at the top.
    tiebreak: float = 0.0


def best_eye_sharpness(faces: list[dict[str, Any]] | None) -> float | None:
    values = [e["sharpness"] for f in faces or [] for e in f.get("eyes", []) if e.get("sharpness") is not None]
    return max(values) if values else None


def score_candidate(c: Candidate) -> Ranked:
    eyes = best_eye_sharpness(c.faces)
    parts = [
        (W_AESTHETIC, c.aesthetic * 10 if c.aesthetic is not None else AESTHETIC_PRIOR),
        (W_SHARPNESS_WITH_EYES if eyes is not None else W_SHARPNESS_ALONE, c.sharpness),
        (W_EYES, eyes),
    ]
    present = [(w, v) for w, v in parts if v is not None]
    base = sum(w * v for w, v in present) / sum(w for w, _ in present) if present else 0.0

    # The photographer's own culling nudges the order but never outweighs the measurements.
    nudge = 0.0
    if c.flag == "pick":
        nudge += 8
    if c.favorite:
        nudge += 5
    if c.rating:
        nudge += (c.rating - 3) * 3
    score = round(max(0.0, min(100.0, base + nudge)), 1)
    return Ranked(c.photo_id, score, c.aesthetic, eyes, c.sharpness_peak or 0.0)


def _key(r: Ranked) -> tuple[float, float]:
    return (r.score, r.tiebreak)


def rank(candidates: list[Candidate], limit: int) -> list[Ranked]:
    best_by_group: dict[uuid.UUID, tuple[Ranked, Candidate]] = {}
    singles: list[Ranked] = []
    for c in candidates:
        r = score_candidate(c)
        if c.burst_group_id is None:
            singles.append(r)
        elif c.burst_group_id not in best_by_group or _key(r) > _key(best_by_group[c.burst_group_id][0]):
            best_by_group[c.burst_group_id] = (r, c)
    ranked = singles + [r for r, _ in best_by_group.values()]
    ranked.sort(key=_key, reverse=True)
    return ranked[:limit]


def period_start(session: Session, period: Period, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now(UTC)
    match period:
        case "session":
            return camera_status(session, now).session_started_at
        case "today":
            return start_of_local_day(now)
        case "7d":
            return start_of_local_day(now) - timedelta(days=6)
        case _:
            return None


def _latest_aesthetic():
    latest = (
        select(AICritique.photo_id, func.max(AICritique.created_at).label("created_at"))
        .where(AICritique.status == "succeeded", AICritique.aesthetic_score.is_not(None))
        .group_by(AICritique.photo_id)
        .subquery()
    )
    return (
        select(AICritique.photo_id, AICritique.aesthetic_score)
        .join(latest, (latest.c.photo_id == AICritique.photo_id) & (latest.c.created_at == AICritique.created_at))
        .subquery()
    )


def find_best(
    session: Session, period: Period, limit: int, now: datetime | None = None
) -> tuple[datetime | None, int, int, list[tuple[Photo, Ranked]]]:
    """Return (period start, candidates considered, candidates with an AI score, ranked photos)."""
    start = period_start(session, period, now)
    if period == "session" and start is None:
        return None, 0, 0, []

    aesthetic = _latest_aesthetic()
    stmt = (
        select(
            Photo.id,
            Photo.burst_group_id,
            TechnicalAnalysis.sharpness_score,
            TechnicalAnalysis.sharpness_peak,
            TechnicalAnalysis.faces,
            aesthetic.c.aesthetic_score,
            Photo.rating,
            Photo.flag,
            Photo.favorite,
        )
        .join(TechnicalAnalysis, TechnicalAnalysis.photo_id == Photo.id)
        .outerjoin(aesthetic, aesthetic.c.photo_id == Photo.id)
        .where(Photo.media_type == "still", Photo.flag != "reject")
    )
    if start is not None:
        # A session is defined by upload activity; calendar periods by when the frame was taken.
        stmt = stmt.where((Photo.imported_at if period == "session" else Photo.capture_time) >= start)

    candidates = [Candidate(*row) for row in session.execute(stmt).all()]
    ranked = rank(candidates, limit)
    photos = {
        p.id: p
        for p in session.scalars(
            select(Photo).where(Photo.id.in_([r.photo_id for r in ranked])).options(*summary_loaders())
        ).all()
    }
    ai_scored = sum(1 for c in candidates if c.aesthetic is not None)
    return start, len(candidates), ai_scored, [(photos[r.photo_id], r) for r in ranked if r.photo_id in photos]
