from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UTCDateTime

if TYPE_CHECKING:
    from app.models.photo import Photo


class BurstGroup(TimestampMixin, Base):
    """Consecutive frames from the same camera/setup captured in quick succession."""

    __tablename__ = "burst_groups"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    camera_key: Mapped[str] = mapped_column(String(128), nullable=False)
    start_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    end_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    photo_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Best frame once ranking exists; defaults to the first frame.
    cover_photo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("photos.id", ondelete="SET NULL", use_alter=True)
    )

    photos: Mapped[list[Photo]] = relationship(
        back_populates="burst_group",
        foreign_keys="Photo.burst_group_id",
        order_by="Photo.capture_time",
    )

    __table_args__ = (Index("ix_burst_groups_start_time", "start_time"),)


class IngestSession(TimestampMixin, Base):
    """A contiguous upload session from the camera (gap-separated activity window)."""

    __tablename__ = "ingest_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    camera_model: Mapped[str | None] = mapped_column(String(64))
    photo_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jpeg_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    raw_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    video_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_total: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    # "live" = watcher saw new files; "scan" = bulk import of pre-existing files.
    source: Mapped[str] = mapped_column(String(16), default="live", nullable=False)

    photos: Mapped[list[Photo]] = relationship(back_populates="ingest_session")

    __table_args__ = (Index("ix_ingest_sessions_last_activity", "last_activity_at"),)
