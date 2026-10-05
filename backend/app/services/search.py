from __future__ import annotations

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.metadata.parser import pretty_camera
from app.models import AICritique, Photo, PhotoTag


def build_search_text(session: Session, photo: Photo) -> str:
    """Denormalised text blob behind the full-text index."""
    tags = session.scalars(
        select(PhotoTag).where(PhotoTag.photo_id == photo.id).options(selectinload(PhotoTag.tag))
    ).all()
    critique = session.scalars(
        select(AICritique)
        .where(AICritique.photo_id == photo.id, AICritique.status == "succeeded")
        .order_by(AICritique.created_at.desc())
        .limit(1)
    ).first()
    parts: list[str | None] = [
        photo.base_filename,
        photo.camera_make,
        photo.camera_model,
        pretty_camera(photo.camera_make, photo.camera_model),
        photo.lens_model,
        f"{photo.focal_length:g}mm" if photo.focal_length else None,
        f"f/{photo.aperture:g}" if photo.aperture else None,
        f"iso{photo.iso}" if photo.iso else None,
        photo.picture_control,
        photo.scene,
        photo.notes,
        " ".join(t.tag.name for t in tags),
    ]
    if critique is not None:
        parts += [critique.scene, critique.subject, critique.description, " ".join(critique.tags or [])]
    return " ".join(p for p in parts if p)[:20000]


def refresh_search_text(session: Session, photo: Photo) -> None:
    photo.search_text = build_search_text(session, photo)


def search_condition(session: Session, query: str) -> ColumnElement[bool]:
    q = query.strip()
    like = f"%{q}%"
    if session.get_bind().dialect.name == "postgresql":
        # Expression matches the GIN index ix_photos_search_fts.
        fts = func.to_tsvector("simple", Photo.search_text).op("@@")(func.websearch_to_tsquery("simple", q))
        return or_(fts, Photo.search_text.ilike(like))
    return Photo.search_text.ilike(like)
