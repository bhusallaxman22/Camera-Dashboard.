from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, deferred, mapped_column, relationship

from app.models.base import Base, JSONType, TimestampMixin, UTCDateTime, utcnow
from app.models.enums import Flag, MediaType, ProcessingStatus

if TYPE_CHECKING:
    from app.models.analysis import AICritique, TechnicalAnalysis
    from app.models.grouping import BurstGroup, IngestSession
    from app.models.organize import PhotoAlbum, PhotoTag


class Photo(TimestampMixin, Base):
    """One logical capture. A JPEG + NEF of the same exposure share one Photo."""

    __tablename__ = "photos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    media_type: Mapped[str] = mapped_column(String(16), default=MediaType.STILL, nullable=False)
    base_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # Lower-cased base filename used for pairing lookups.
    base_key: Mapped[str] = mapped_column(String(255), nullable=False)

    capture_time: Mapped[datetime | None] = mapped_column(UTCDateTime())
    capture_tz_offset: Mapped[str | None] = mapped_column(String(8))
    imported_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    camera_make: Mapped[str | None] = mapped_column(String(64))
    camera_model: Mapped[str | None] = mapped_column(String(64))
    camera_serial: Mapped[str | None] = mapped_column(String(64))
    shutter_count: Mapped[int | None] = mapped_column(Integer)
    firmware: Mapped[str | None] = mapped_column(String(32))

    lens_model: Mapped[str | None] = mapped_column(String(128))
    focal_length: Mapped[float | None] = mapped_column(Float)
    focal_length_35mm: Mapped[float | None] = mapped_column(Float)
    aperture: Mapped[float | None] = mapped_column(Float)
    shutter_speed: Mapped[float | None] = mapped_column(Float)  # seconds
    iso: Mapped[int | None] = mapped_column(Integer)
    exposure_compensation: Mapped[float | None] = mapped_column(Float)
    exposure_program: Mapped[str | None] = mapped_column(String(64))
    metering_mode: Mapped[str | None] = mapped_column(String(64))
    white_balance: Mapped[str | None] = mapped_column(String(64))
    flash: Mapped[str | None] = mapped_column(String(128))
    focus_mode: Mapped[str | None] = mapped_column(String(64))
    af_area_mode: Mapped[str | None] = mapped_column(String(64))
    picture_control: Mapped[str | None] = mapped_column(String(64))
    image_quality: Mapped[str | None] = mapped_column(String(64))

    image_width: Mapped[int | None] = mapped_column(Integer)
    image_height: Mapped[int | None] = mapped_column(Integer)
    orientation: Mapped[int | None] = mapped_column(SmallInteger)
    color_space: Mapped[str | None] = mapped_column(String(32))
    duration_seconds: Mapped[float | None] = mapped_column(Float)

    gps_latitude: Mapped[float | None] = mapped_column(Float)
    gps_longitude: Mapped[float | None] = mapped_column(Float)
    gps_altitude: Mapped[float | None] = mapped_column(Float)

    # Curated Nikon/maker fields that have no dedicated column (VR, AF details...).
    extra: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)

    # Culling state — stored in the DB only, never written to originals.
    rating: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    flag: Mapped[str] = mapped_column(String(16), default=Flag.NONE, nullable=False)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    needs_edit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    exported: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    # Denormalised file presence for fast library filters.
    has_jpeg: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_raw: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_video: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    scene: Mapped[str | None] = mapped_column(String(64))
    processing_status: Mapped[str] = mapped_column(String(16), default=ProcessingStatus.PENDING, nullable=False)
    processing_error: Mapped[str | None] = mapped_column(Text)
    search_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    immich_asset_id: Mapped[str | None] = mapped_column(String(64))

    burst_group_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("burst_groups.id", ondelete="SET NULL"))
    burst_index: Mapped[int | None] = mapped_column(Integer)
    ingest_session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingest_sessions.id", ondelete="SET NULL"))

    files: Mapped[list[PhotoFile]] = relationship(
        back_populates="photo", cascade="all, delete-orphan", order_by="PhotoFile.file_type"
    )
    renditions: Mapped[list[Rendition]] = relationship(back_populates="photo", cascade="all, delete-orphan")
    analysis: Mapped[TechnicalAnalysis | None] = relationship(
        back_populates="photo", cascade="all, delete-orphan", uselist=False
    )
    critiques: Mapped[list[AICritique]] = relationship(
        back_populates="photo", cascade="all, delete-orphan", order_by="AICritique.created_at.desc()"
    )
    tags: Mapped[list[PhotoTag]] = relationship(back_populates="photo", cascade="all, delete-orphan")
    albums: Mapped[list[PhotoAlbum]] = relationship(back_populates="photo", cascade="all, delete-orphan")
    burst_group: Mapped[BurstGroup | None] = relationship(back_populates="photos", foreign_keys=[burst_group_id])
    ingest_session: Mapped[IngestSession | None] = relationship(back_populates="photos")

    __table_args__ = (
        Index("ix_photos_capture_time", "capture_time"),
        Index("ix_photos_imported_at", "imported_at"),
        Index("ix_photos_base_key", "base_key"),
        Index("ix_photos_camera_shutter", "camera_serial", "shutter_count"),
        Index("ix_photos_camera_model", "camera_model"),
        Index("ix_photos_lens_model", "lens_model"),
        Index("ix_photos_rating", "rating"),
        Index("ix_photos_flag", "flag"),
        Index("ix_photos_burst_group_id", "burst_group_id"),
        Index("ix_photos_ingest_session_id", "ingest_session_id"),
    )

    @property
    def rejected(self) -> bool:
        return self.flag == Flag.REJECT

    @property
    def picked(self) -> bool:
        return self.flag == Flag.PICK


class PhotoFile(TimestampMixin, Base):
    """An original file on disk (read-only). Never modified by the app."""

    __tablename__ = "photo_files"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    photo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)
    absolute_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    extension: Mapped[str] = mapped_column(String(16), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(64))
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(64))
    modification_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    exists: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    # Byte-identical copy of another file (e.g. re-uploaded); kept but not primary.
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("photo_files.id", ondelete="SET NULL"))
    # Full ExifTool dump (printed values + numeric where different). Deferred so
    # list queries never pull it.
    exif: Mapped[dict[str, Any]] = deferred(mapped_column(JSONType, default=dict, nullable=False))

    photo: Mapped[Photo] = relationship(back_populates="files")

    __table_args__ = (
        Index("ix_photo_files_photo_id", "photo_id"),
        Index("ix_photo_files_checksum", "checksum"),
        Index("ix_photo_files_file_type", "file_type"),
    )


class Rendition(Base):
    """Generated derivative (thumbnail/preview) stored under DATA_ROOT."""

    __tablename__ = "renditions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    photo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)  # relative to DATA_ROOT
    format: Mapped[str] = mapped_column(String(8), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("photo_files.id", ondelete="SET NULL"))
    # Identity of the source used; renditions are regenerated only if this changes.
    source_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    photo: Mapped[Photo] = relationship(back_populates="renditions")

    __table_args__ = (UniqueConstraint("photo_id", "kind", name="uq_renditions_photo_kind"),)
