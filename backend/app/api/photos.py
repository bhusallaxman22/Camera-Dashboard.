from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import DB
from app.config import get_settings
from app.image.renditions import best_thumbnail, rendition_for
from app.models import Photo, PhotoFile, Tag
from app.models.enums import JobKind, RenditionKind
from app.schemas.photo import (
    AnalyzeRequest,
    BestPhoto,
    BestPhotos,
    BulkUpdate,
    Facets,
    PhotoDetail,
    PhotoPage,
    PhotoUpdate,
)
from app.services.best import Period, find_best
from app.services.events import publish_after_commit, record_event
from app.services.immich import ImmichClient, ImmichError
from app.services.photos import PhotoFilters, SortKey, get_photo, list_photos, set_tags, to_detail, to_summary
from app.services.search import refresh_search_text
from app.utils.paths import UnsafePathError, resolve_under_roots
from app.workers.queue import enqueue, enqueue_safe

router = APIRouter(prefix="/photos", tags=["photos"])
files_router = APIRouter(prefix="/files", tags=["files"])

IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


def filters_dep(
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    camera: str | None = None,
    lens: str | None = None,
    iso_min: int | None = None,
    iso_max: int | None = None,
    aperture_min: float | None = None,
    aperture_max: float | None = None,
    focal_min: float | None = None,
    focal_max: float | None = None,
    rating_min: Annotated[int | None, Query(ge=0, le=5)] = None,
    favorite: bool | None = None,
    flag: Annotated[str | None, Query(pattern="^(none|pick|reject)$")] = None,
    hide_rejected: bool = False,
    needs_edit: bool | None = None,
    exported: bool | None = None,
    file_kind: Annotated[str | None, Query(pattern="^(pair|raw|jpeg_only|raw_only|video|still)$")] = None,
    scene: str | None = None,
    tag: str | None = None,
    album_id: uuid.UUID | None = None,
    burst_id: uuid.UUID | None = None,
    collapse_bursts: bool = False,
    sharp_min: float | None = None,
    highlights_min: float | None = None,
    has_faces: bool | None = None,
) -> PhotoFilters:
    return PhotoFilters(**{k: v for k, v in locals().items()})


Filters = Annotated[PhotoFilters, Depends(filters_dep)]


def _photo_or_404(db: DB, photo_id: uuid.UUID) -> Photo:
    photo = get_photo(db, photo_id)
    if photo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "photo not found")
    return photo


@router.get("", response_model=PhotoPage)
def list_(
    db: DB,
    filters: Filters,
    sort: SortKey = "newest",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 60,
    thumb: Annotated[int, Query(ge=128, le=1024)] = 512,
) -> PhotoPage:
    items, total = list_photos(db, filters, sort, page, page_size)
    return PhotoPage(
        items=[to_summary(p, thumb) for p in items],
        total=total,
        page=page,
        page_size=page_size,
        has_more=page * page_size < total,
    )


@router.get("/facets", response_model=Facets)
def facets(db: DB) -> Facets:
    def distinct_values(col) -> list[str]:
        return [v for v in db.scalars(select(col).where(col.is_not(None)).distinct().order_by(col)).all() if v]

    iso = db.execute(select(func.min(Photo.iso), func.max(Photo.iso))).one()
    focal = db.execute(select(func.min(Photo.focal_length), func.max(Photo.focal_length))).one()
    ap = db.execute(select(func.min(Photo.aperture), func.max(Photo.aperture))).one()
    dates = db.execute(select(func.min(Photo.capture_time), func.max(Photo.capture_time))).one()
    return Facets(
        cameras=distinct_values(Photo.camera_model),
        lenses=distinct_values(Photo.lens_model),
        scenes=distinct_values(Photo.scene),
        tags=list(db.scalars(select(Tag.name).order_by(Tag.name)).all()),
        iso_range=tuple(iso),
        focal_range=tuple(focal),
        aperture_range=tuple(ap),
        date_range=tuple(dates),
    )


@router.get("/best", response_model=BestPhotos)
def best(
    db: DB,
    period: Period = "today",
    limit: Annotated[int, Query(ge=1, le=48)] = 12,
    thumb: Annotated[int, Query(ge=128, le=1024)] = 512,
) -> BestPhotos:
    """Strongest frames in a period: AI aesthetic estimate blended with measured
    sharpness and eye focus, one frame per burst, rejects excluded."""
    start, candidates, ai_scored, ranked = find_best(db, period, limit)
    return BestPhotos(
        period=period,
        period_start=start,
        candidates=candidates,
        ai_scored=ai_scored,
        items=[
            BestPhoto(
                photo=to_summary(p, thumb),
                score=r.score,
                aesthetic_score=r.aesthetic,
                eye_sharpness=r.eye_sharpness,
            )
            for p, r in ranked
        ],
    )


@router.get("/{photo_id}", response_model=PhotoDetail)
def detail(db: DB, photo_id: uuid.UUID) -> PhotoDetail:
    return to_detail(db, _photo_or_404(db, photo_id))


def _apply_update(db: DB, photo: Photo, body: PhotoUpdate) -> list[str]:
    changes = body.model_dump(exclude_unset=True)
    tags = changes.pop("tags", None)
    for key, value in changes.items():
        setattr(photo, key, value)
    if tags is not None:
        set_tags(db, photo, tags)
        changes["tags"] = tags
    if "notes" in changes or tags is not None:
        db.flush()
        refresh_search_text(db, photo)
    return list(changes)


@router.patch("/{photo_id}", response_model=PhotoDetail)
def update(db: DB, photo_id: uuid.UUID, body: PhotoUpdate) -> PhotoDetail:
    """Update culling state. Stored in the database only — originals are untouched."""
    photo = _photo_or_404(db, photo_id)
    changed = _apply_update(db, photo, body)
    publish_after_commit(db, "photo.updated", {"photo_id": photo.id, "fields": changed})
    db.commit()
    return to_detail(db, _photo_or_404(db, photo_id))


@router.post("/bulk", response_model=dict)
def bulk_update(db: DB, body: BulkUpdate) -> dict:
    update_body = PhotoUpdate(**body.model_dump(exclude={"ids"}, exclude_unset=True))
    photos = db.scalars(select(Photo).where(Photo.id.in_(body.ids)).options(selectinload(Photo.tags))).all()
    for p in photos:
        _apply_update(db, p, update_body)
    publish_after_commit(db, "photo.updated", {"photo_ids": [p.id for p in photos], "bulk": True})
    db.commit()
    return {"updated": len(photos)}


@router.post("/{photo_id}/analyze", status_code=status.HTTP_202_ACCEPTED)
def analyze(db: DB, photo_id: uuid.UUID, body: AnalyzeRequest | None = None) -> dict:
    body = body or AnalyzeRequest()
    photo = _photo_or_404(db, photo_id)
    pid = str(photo.id)
    jobs = []
    if body.rerender:
        jobs.append(enqueue(JobKind.RENDER, photo_id=pid, payload={"photo_id": pid, "force": True}))
    elif body.technical:
        jobs.append(enqueue(JobKind.ANALYZE, photo_id=pid, payload={"photo_id": pid, "with_ai": False}))
    if body.ai:
        payload = {"photo_id": pid}
        if body.provider:
            payload["provider"] = body.provider
        jobs.append(enqueue(JobKind.AI_CRITIQUE, photo_id=pid, payload=payload))
    return {"queued": [str(j) for j in jobs if j]}


@router.post("/{photo_id}/immich/link", response_model=PhotoDetail)
def link_immich(db: DB, photo_id: uuid.UUID) -> PhotoDetail:
    """Look up the matching Immich asset (read-only) and remember its id."""
    photo = _photo_or_404(db, photo_id)
    client = ImmichClient()
    if not client.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Immich integration is disabled")
    jpeg = next((f for f in photo.files if f.file_type in ("jpeg", "image") and f.exists), None)
    if jpeg is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "photo has no JPEG for Immich to match")
    try:
        asset = client.find_asset(jpeg.filename, photo.capture_time)
    except ImmichError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Immich error: {exc}") from exc
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no matching Immich asset found")
    photo.immich_asset_id = asset
    record_event(db, "INGEST", "immich_linked", f"{photo.base_filename} linked to Immich", photo_id=photo.id)
    db.commit()
    return to_detail(db, _photo_or_404(db, photo_id))


def _serve_rendition(photo_id: uuid.UUID, path_rel: str, media_type: str) -> FileResponse:
    settings = get_settings()
    try:
        path = resolve_under_roots(settings.data_root / path_rel, [settings.data_root])
    except UnsafePathError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found") from exc
    if not path.is_file():
        # Recorded but gone (e.g. /data reset): regenerate from the original in the background.
        pid = str(photo_id)
        enqueue_safe(JobKind.RENDER, dedupe_key=pid, photo_id=pid, payload={"photo_id": pid})
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rendition missing, regenerating")
    return FileResponse(path, media_type=media_type, headers=IMMUTABLE)


@router.get("/{photo_id}/thumbnail", response_class=FileResponse)
def thumbnail(db: DB, photo_id: uuid.UUID, size: Annotated[int, Query(ge=64, le=2560)] = 512) -> FileResponse:
    photo = db.get(Photo, photo_id, options=[selectinload(Photo.renditions)])
    r = best_thumbnail(photo, size) if photo else None
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thumbnail not generated yet")
    return _serve_rendition(photo_id, r.path, "image/webp" if r.format == "webp" else "image/jpeg")


@router.get("/{photo_id}/preview", response_class=FileResponse)
def preview(db: DB, photo_id: uuid.UUID) -> FileResponse:
    photo = db.get(Photo, photo_id, options=[selectinload(Photo.renditions)])
    r = rendition_for(photo, RenditionKind.PREVIEW.value) if photo else None
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "preview not generated yet")
    return _serve_rendition(photo_id, r.path, "image/jpeg")


@files_router.get("/{file_id}/download", response_class=FileResponse)
def download(db: DB, file_id: uuid.UUID, inline: bool = False) -> FileResponse:
    """Stream an original. The path comes from the DB (never from the request)
    and must resolve inside an approved photo root."""
    f = db.get(PhotoFile, file_id)
    if f is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")
    settings = get_settings()
    try:
        path = resolve_under_roots(Path(f.absolute_path), list(settings.media_roots.values()))
    except UnsafePathError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "file is outside approved roots") from exc
    if not path.is_file():
        raise HTTPException(status.HTTP_410_GONE, "original no longer exists on disk")
    return FileResponse(
        path,
        media_type=f.mime_type or "application/octet-stream",
        filename=f.filename,
        content_disposition_type="inline" if inline else "attachment",
    )
