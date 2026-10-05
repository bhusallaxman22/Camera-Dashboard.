"""Albums, tags and search."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import DB
from app.models import Album, Photo, PhotoAlbum, PhotoTag, Tag
from app.schemas.photo import PhotoPage, TagOut
from app.schemas.system import AlbumIn, AlbumOut, AlbumPhotosIn, TagIn
from app.services.photos import PhotoFilters, SortKey, album_summary, list_photos, to_summary

router = APIRouter(tags=["library"])


@router.get("/albums", response_model=list[AlbumOut])
def list_albums(db: DB) -> list[dict[str, Any]]:
    return [album_summary(db, a) for a in db.scalars(select(Album).order_by(Album.updated_at.desc())).all()]


def _add_photos(db: DB, album: Album, photo_ids: list[uuid.UUID]) -> None:
    existing = set(db.scalars(select(PhotoAlbum.photo_id).where(PhotoAlbum.album_id == album.id)).all())
    pos = db.scalar(select(func.coalesce(func.max(PhotoAlbum.position), 0)).where(PhotoAlbum.album_id == album.id)) or 0
    valid = set(db.scalars(select(Photo.id).where(Photo.id.in_(photo_ids))).all())
    for pid in photo_ids:
        if pid in valid and pid not in existing:
            pos += 1
            db.add(PhotoAlbum(album_id=album.id, photo_id=pid, position=pos))
            existing.add(pid)


@router.post("/albums", response_model=AlbumOut, status_code=status.HTTP_201_CREATED)
def create_album(db: DB, body: AlbumIn) -> dict[str, Any]:
    album = Album(name=body.name.strip(), description=body.description)
    db.add(album)
    db.flush()
    _add_photos(db, album, body.photo_ids)
    db.commit()
    return album_summary(db, album)


@router.get("/albums/{album_id}", response_model=AlbumOut)
def get_album(db: DB, album_id: uuid.UUID) -> dict[str, Any]:
    album = db.get(Album, album_id)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "album not found")
    return album_summary(db, album)


@router.post("/albums/{album_id}/photos", response_model=AlbumOut)
def add_to_album(db: DB, album_id: uuid.UUID, body: AlbumPhotosIn) -> dict[str, Any]:
    album = db.get(Album, album_id)
    if album is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "album not found")
    _add_photos(db, album, body.photo_ids)
    db.commit()
    return album_summary(db, album)


@router.delete("/albums/{album_id}/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_album(db: DB, album_id: uuid.UUID, photo_id: uuid.UUID) -> None:
    link = db.get(PhotoAlbum, (album_id, photo_id))
    if link is not None:
        db.delete(link)
        db.commit()


@router.delete("/albums/{album_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_album(db: DB, album_id: uuid.UUID) -> None:
    """Deletes the album grouping only; photos and originals are untouched."""
    album = db.get(Album, album_id)
    if album is not None:
        db.delete(album)
        db.commit()


@router.get("/tags", response_model=list[TagOut])
def list_tags(db: DB) -> list[TagOut]:
    rows = db.execute(
        select(Tag, func.count(PhotoTag.photo_id))
        .outerjoin(PhotoTag, PhotoTag.tag_id == Tag.id)
        .group_by(Tag.id)
        .order_by(Tag.name)
    ).all()
    return [TagOut(id=t.id, name=t.name, color=t.color, count=c) for t, c in rows]


@router.post("/tags", response_model=TagOut, status_code=status.HTTP_201_CREATED)
def create_tag(db: DB, body: TagIn) -> TagOut:
    name = body.name.strip().lower()
    tag = db.scalars(select(Tag).where(Tag.name == name)).first()
    if tag is None:
        tag = Tag(name=name, color=body.color)
        db.add(tag)
        db.commit()
    return TagOut(id=tag.id, name=tag.name, color=tag.color, count=None)


@router.get("/search", response_model=PhotoPage)
def search(
    db: DB,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    sort: SortKey = "newest",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 60,
) -> PhotoPage:
    """Full-text search over filename, camera, lens, tags, notes, scene and AI description."""
    items, total = list_photos(db, PhotoFilters(q=q), sort, page, page_size)
    return PhotoPage(
        items=[to_summary(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
        has_more=page * page_size < total,
    )
