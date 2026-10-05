from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, TimestampMixin, UTCDateTime, utcnow

if TYPE_CHECKING:
    from app.models.photo import Photo


class Tag(CreatedAtMixin, Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    color: Mapped[str | None] = mapped_column(String(16))

    photos: Mapped[list[PhotoTag]] = relationship(back_populates="tag", cascade="all, delete-orphan")


class PhotoTag(Base):
    __tablename__ = "photo_tags"

    photo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
    source: Mapped[str] = mapped_column(String(16), default="user", nullable=False)  # user | ai
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    photo: Mapped[Photo] = relationship(back_populates="tags")
    tag: Mapped[Tag] = relationship(back_populates="photos", lazy="joined")

    __table_args__ = (Index("ix_photo_tags_tag_id", "tag_id"),)


class Album(TimestampMixin, Base):
    __tablename__ = "albums"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    cover_photo_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("photos.id", ondelete="SET NULL"))

    photos: Mapped[list[PhotoAlbum]] = relationship(
        back_populates="album", cascade="all, delete-orphan", order_by="PhotoAlbum.position"
    )


class PhotoAlbum(Base):
    __tablename__ = "photo_albums"

    album_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"), primary_key=True)
    photo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    added_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    album: Mapped[Album] = relationship(back_populates="photos")
    photo: Mapped[Photo] = relationship(back_populates="albums")

    __table_args__ = (Index("ix_photo_albums_photo_id", "photo_id"),)
