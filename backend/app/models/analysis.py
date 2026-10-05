from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, UTCDateTime, utcnow

if TYPE_CHECKING:
    from app.models.photo import Photo


class TechnicalAnalysis(Base):
    """Deterministic, local image metrics (one row per photo, replaced on re-run).

    These are measurements of the rendered JPEG/preview, not objective judgements
    of photographic quality; labels are phrased as estimates.
    """

    __tablename__ = "technical_analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    photo_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    sharpness_score: Mapped[float | None] = mapped_column(Float)  # 0-100, peak region
    sharpness_label: Mapped[str | None] = mapped_column(String(32))
    sharpness_global: Mapped[float | None] = mapped_column(Float)  # raw Laplacian var
    sharpness_peak: Mapped[float | None] = mapped_column(Float)
    blur_score: Mapped[float | None] = mapped_column(Float)  # 0 (crisp) .. 1 (blurry)
    is_blurry: Mapped[bool | None] = mapped_column(Boolean)

    brightness: Mapped[float | None] = mapped_column(Float)  # mean luminance 0-1
    contrast: Mapped[float | None] = mapped_column(Float)  # RMS contrast 0-1
    saturation: Mapped[float | None] = mapped_column(Float)  # mean HSV S 0-1
    dynamic_range_ev: Mapped[float | None] = mapped_column(Float)
    highlight_clipping_percent: Mapped[float | None] = mapped_column(Float)
    shadow_clipping_percent: Mapped[float | None] = mapped_column(Float)
    exposure_label: Mapped[str | None] = mapped_column(String(32))
    exposure_assessment: Mapped[str | None] = mapped_column(Text)

    histogram: Mapped[dict[str, list[int]]] = mapped_column(JSONType, default=dict)
    dominant_colors: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)

    face_count: Mapped[int | None] = mapped_column(Integer)
    eye_count: Mapped[int | None] = mapped_column(Integer)
    faces: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    subject_detected: Mapped[bool | None] = mapped_column(Boolean)
    warnings: Mapped[list[str]] = mapped_column(JSONType, default=list)

    source: Mapped[str | None] = mapped_column(String(32))  # preview source file type
    analyzed_width: Mapped[int | None] = mapped_column(Integer)
    analyzed_height: Mapped[int | None] = mapped_column(Integer)
    algorithm_version: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    analyzed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    photo: Mapped[Photo] = relationship(back_populates="analysis")


class AICritique(Base):
    """Structured output of an AI provider. History is kept (one row per run)."""

    __tablename__ = "ai_critiques"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    photo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(128))
    model_version: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="succeeded")

    scene: Mapped[str | None] = mapped_column(String(64))
    subject: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    composition: Mapped[list[str]] = mapped_column(JSONType, default=list)
    technical: Mapped[list[str]] = mapped_column(JSONType, default=list)
    issues: Mapped[list[str]] = mapped_column(JSONType, default=list)
    suggestions: Mapped[list[str]] = mapped_column(JSONType, default=list)
    tags: Mapped[list[str]] = mapped_column(JSONType, default=list)
    aesthetic_score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    photo: Mapped[Photo] = relationship(back_populates="critiques")

    __table_args__ = (Index("ix_ai_critiques_photo_created", "photo_id", "created_at"),)
