from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.image.renditions import best_thumbnail, rendition_for
from app.metadata.parser import pretty_camera
from app.models import (
    AICritique,
    Album,
    BurstGroup,
    Photo,
    PhotoAlbum,
    PhotoFile,
    PhotoTag,
    Tag,
    TechnicalAnalysis,
)
from app.models.enums import RenditionKind
from app.schemas.photo import (
    AnalysisOut,
    BurstOut,
    CritiqueOut,
    PhotoDetail,
    PhotoFileOut,
    PhotoSummary,
    TagOut,
)
from app.services.immich import ImmichClient, immich_asset_url
from app.services.search import search_condition
from app.utils.timeutil import local_tz

SortKey = Literal["newest", "oldest", "rating", "filename", "imported", "sharpness"]


def summary_loaders() -> list[Any]:
    """Eager loads needed by to_summary(), avoiding N+1 queries on lists."""
    return [selectinload(Photo.renditions), selectinload(Photo.analysis), selectinload(Photo.burst_group)]


@dataclass(slots=True)
class PhotoFilters:
    q: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    camera: str | None = None
    lens: str | None = None
    iso_min: int | None = None
    iso_max: int | None = None
    aperture_min: float | None = None
    aperture_max: float | None = None
    focal_min: float | None = None
    focal_max: float | None = None
    rating_min: int | None = None
    favorite: bool | None = None
    flag: str | None = None
    hide_rejected: bool = False
    needs_edit: bool | None = None
    exported: bool | None = None
    file_kind: str | None = None  # pair | raw | jpeg_only | raw_only | video
    scene: str | None = None
    tag: str | None = None
    album_id: uuid.UUID | None = None
    burst_id: uuid.UUID | None = None
    collapse_bursts: bool = False
    sharp_min: float | None = None
    highlights_min: float | None = None
    has_faces: bool | None = None


def _local_day_bounds(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=local_tz())


def apply_filters(session: Session, stmt: Select, f: PhotoFilters) -> Select:
    conds: list[Any] = []
    if f.q:
        conds.append(search_condition(session, f.q))
    if f.date_from:
        conds.append(Photo.capture_time >= _local_day_bounds(f.date_from))
    if f.date_to:
        conds.append(Photo.capture_time < _local_day_bounds(f.date_to + timedelta(days=1)))
    if f.camera:
        conds.append(Photo.camera_model == f.camera)
    if f.lens:
        conds.append(Photo.lens_model == f.lens)
    for col, lo, hi in (
        (Photo.iso, f.iso_min, f.iso_max),
        (Photo.aperture, f.aperture_min, f.aperture_max),
        (Photo.focal_length, f.focal_min, f.focal_max),
    ):
        if lo is not None:
            conds.append(col >= lo)
        if hi is not None:
            conds.append(col <= hi)
    if f.rating_min:
        conds.append(Photo.rating >= f.rating_min)
    if f.favorite is not None:
        conds.append(Photo.favorite.is_(f.favorite))
    if f.flag:
        conds.append(Photo.flag == f.flag)
    if f.hide_rejected:
        conds.append(Photo.flag != "reject")
    if f.needs_edit is not None:
        conds.append(Photo.needs_edit.is_(f.needs_edit))
    if f.exported is not None:
        conds.append(Photo.exported.is_(f.exported))
    match f.file_kind:
        case "pair":
            conds += [Photo.has_raw.is_(True), Photo.has_jpeg.is_(True)]
        case "raw":
            conds.append(Photo.has_raw.is_(True))
        case "jpeg_only":
            conds += [Photo.has_jpeg.is_(True), Photo.has_raw.is_(False)]
        case "raw_only":
            conds += [Photo.has_raw.is_(True), Photo.has_jpeg.is_(False)]
        case "video":
            conds.append(Photo.media_type == "video")
        case "still":
            conds.append(Photo.media_type == "still")
    if f.scene:
        conds.append(Photo.scene == f.scene)
    if f.tag:
        conds.append(Photo.id.in_(select(PhotoTag.photo_id).join(Tag).where(Tag.name == f.tag.lower())))
    if f.album_id:
        conds.append(Photo.id.in_(select(PhotoAlbum.photo_id).where(PhotoAlbum.album_id == f.album_id)))
    if f.burst_id:
        conds.append(Photo.burst_group_id == f.burst_id)
    if f.collapse_bursts:
        conds.append(
            or_(
                Photo.burst_group_id.is_(None),
                Photo.id.in_(select(BurstGroup.cover_photo_id)),
            )
        )
    needs_analysis_join = f.sharp_min is not None or f.highlights_min is not None or f.has_faces is not None
    if needs_analysis_join:
        stmt = stmt.join(TechnicalAnalysis, TechnicalAnalysis.photo_id == Photo.id)
        if f.sharp_min is not None:
            conds.append(TechnicalAnalysis.sharpness_score >= f.sharp_min)
        if f.highlights_min is not None:
            conds.append(TechnicalAnalysis.highlight_clipping_percent >= f.highlights_min)
        if f.has_faces is not None:
            conds.append(TechnicalAnalysis.face_count > 0 if f.has_faces else TechnicalAnalysis.face_count == 0)
    return stmt.where(and_(*conds)) if conds else stmt


def apply_sort(stmt: Select, sort: SortKey) -> Select:
    nulls_last_desc = Photo.capture_time.desc().nulls_last()
    match sort:
        case "oldest":
            return stmt.order_by(Photo.capture_time.asc().nulls_last(), Photo.base_filename)
        case "rating":
            return stmt.order_by(Photo.rating.desc(), nulls_last_desc, Photo.id)
        case "filename":
            return stmt.order_by(Photo.base_filename.asc(), Photo.id)
        case "imported":
            return stmt.order_by(Photo.imported_at.desc(), Photo.id)
        case "sharpness":
            return stmt.outerjoin(TechnicalAnalysis, TechnicalAnalysis.photo_id == Photo.id).order_by(
                TechnicalAnalysis.sharpness_score.desc().nulls_last(), nulls_last_desc
            )
        case _:
            return stmt.order_by(nulls_last_desc, Photo.base_filename.desc(), Photo.id)


def list_photos(session: Session, f: PhotoFilters, sort: SortKey, page: int, page_size: int) -> tuple[list[Photo], int]:
    base = apply_filters(session, select(Photo), f)
    total = session.scalar(select(func.count()).select_from(base.with_only_columns(Photo.id).subquery())) or 0
    stmt = apply_sort(base, sort).offset((page - 1) * page_size).limit(page_size)
    stmt = stmt.options(*summary_loaders())
    return list(session.scalars(stmt).unique().all()), total


def _ts(dt: datetime | None) -> int:
    return int(dt.timestamp()) if dt else 0


def thumb_url(photo: Photo, size: int = 512) -> tuple[str | None, int | None, int | None]:
    r = best_thumbnail(photo, size)
    if r is None:
        return None, None, None
    return f"/api/v1/photos/{photo.id}/thumbnail?size={size}&v={_ts(r.created_at)}", r.width, r.height


def to_summary(photo: Photo, thumb_size: int = 512) -> PhotoSummary:
    url, w, h = thumb_url(photo, thumb_size)
    a = photo.analysis
    return PhotoSummary(
        id=photo.id,
        base_filename=photo.base_filename,
        media_type=photo.media_type,
        capture_time=photo.capture_time,
        imported_at=photo.imported_at,
        camera=pretty_camera(photo.camera_make, photo.camera_model),
        lens_model=photo.lens_model,
        focal_length=photo.focal_length,
        aperture=photo.aperture,
        shutter_speed=photo.shutter_speed,
        iso=photo.iso,
        exposure_compensation=photo.exposure_compensation,
        rating=photo.rating,
        flag=photo.flag,
        rejected=photo.rejected,
        picked=photo.picked,
        favorite=photo.favorite,
        needs_edit=photo.needs_edit,
        exported=photo.exported,
        has_jpeg=photo.has_jpeg,
        has_raw=photo.has_raw,
        has_video=photo.has_video,
        processing_status=photo.processing_status,
        scene=photo.scene,
        burst_group_id=photo.burst_group_id,
        burst_index=photo.burst_index,
        burst_size=photo.burst_group.photo_count if photo.burst_group else None,
        thumb_url=url,
        thumb_width=w,
        thumb_height=h,
        sharpness_score=a.sharpness_score if a else None,
        exposure_label=a.exposure_label if a else None,
        face_count=a.face_count if a else None,
    )


def file_out(f: PhotoFile) -> PhotoFileOut:
    s = get_settings()
    return PhotoFileOut(
        id=f.id,
        file_type=f.file_type,
        filename=f.filename,
        extension=f.extension,
        mime_type=f.mime_type,
        file_size=f.file_size,
        checksum=f.checksum,
        modification_time=f.modification_time,
        width=f.width,
        height=f.height,
        exists=f.exists,
        is_duplicate=f.duplicate_of_id is not None,
        container_path=f.absolute_path,
        nas_path=s.display_path(f.absolute_path),
        smb_path=s.smb_path(f.absolute_path),
        relative_path=f.relative_path,
        download_url=f"/api/v1/files/{f.id}/download",
    )


def _neighbours(session: Session, photo: Photo) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """prev = newer, next = older (matches the default newest-first grid)."""
    if photo.capture_time is None:
        return None, None
    key = (Photo.capture_time, Photo.base_filename)
    newer = session.scalar(
        select(Photo.id)
        .where(
            or_(
                key[0] > photo.capture_time,
                and_(key[0] == photo.capture_time, key[1] > photo.base_filename),
            )
        )
        .order_by(key[0].asc(), key[1].asc())
        .limit(1)
    )
    older = session.scalar(
        select(Photo.id)
        .where(
            or_(
                key[0] < photo.capture_time,
                and_(key[0] == photo.capture_time, key[1] < photo.base_filename),
            )
        )
        .order_by(key[0].desc(), key[1].desc())
        .limit(1)
    )
    return newer, older


def get_photo(session: Session, photo_id: uuid.UUID) -> Photo | None:
    return session.get(
        Photo,
        photo_id,
        options=[
            *summary_loaders(),
            selectinload(Photo.files),
            selectinload(Photo.tags).selectinload(PhotoTag.tag),
            selectinload(Photo.albums).selectinload(PhotoAlbum.album),
        ],
    )


def to_detail(session: Session, photo: Photo) -> PhotoDetail:
    summary = to_summary(photo, 512).model_dump()
    preview = rendition_for(photo, RenditionKind.PREVIEW.value)
    critique = session.scalars(
        select(AICritique).where(AICritique.photo_id == photo.id).order_by(AICritique.created_at.desc()).limit(1)
    ).first()
    critique_count = session.scalar(select(func.count(AICritique.id)).where(AICritique.photo_id == photo.id)) or 0

    burst = None
    if photo.burst_group_id:
        group = session.get(BurstGroup, photo.burst_group_id)
        if group is not None:
            members = session.scalars(
                select(Photo)
                .where(Photo.burst_group_id == group.id)
                .order_by(Photo.burst_index)
                .options(*summary_loaders())
            ).all()
            burst = BurstOut(
                id=group.id,
                photo_count=group.photo_count,
                start_time=group.start_time,
                end_time=group.end_time,
                cover_photo_id=group.cover_photo_id,
                members=[to_summary(m, 256) for m in members],
            )

    prev_id, next_id = _neighbours(session, photo)
    files = sorted(photo.files, key=lambda f: (f.duplicate_of_id is not None, f.file_type))
    detail_fields = {
        k: getattr(photo, k)
        for k in PhotoDetail.model_fields
        if k not in summary and hasattr(Photo, k) and k not in {"files", "analysis", "tags", "albums"}
    }
    return PhotoDetail(
        **summary,
        **detail_fields,
        preview_url=(f"/api/v1/photos/{photo.id}/preview?v={_ts(preview.created_at)}" if preview else None),
        preview_width=preview.width if preview else None,
        preview_height=preview.height if preview else None,
        files=[file_out(f) for f in files],
        analysis=AnalysisOut.model_validate(photo.analysis) if photo.analysis else None,
        critique=CritiqueOut.model_validate(critique) if critique else None,
        critique_history=critique_count,
        tags=[TagOut(id=t.tag.id, name=t.tag.name, color=t.tag.color) for t in photo.tags],
        albums=[{"id": str(a.album.id), "name": a.album.name} for a in photo.albums],
        burst=burst,
        immich_url=immich_asset_url(photo.immich_asset_id),
        immich_enabled=ImmichClient().enabled,
        prev_id=prev_id,
        next_id=next_id,
    )


def set_tags(session: Session, photo: Photo, names: list[str]) -> None:
    wanted = {n.strip().lower()[:64] for n in names if n and n.strip()}
    current = {pt.tag.name: pt for pt in photo.tags}
    for name, pt in current.items():
        if name not in wanted:
            photo.tags.remove(pt)
    for name in wanted - set(current):
        tag = session.scalars(select(Tag).where(Tag.name == name)).first()
        if tag is None:
            tag = Tag(name=name)
            session.add(tag)
            session.flush()
        photo.tags.append(PhotoTag(photo_id=photo.id, tag_id=tag.id, tag=tag))


def album_summary(session: Session, album: Album) -> dict[str, Any]:
    count = session.scalar(select(func.count()).where(PhotoAlbum.album_id == album.id)) or 0
    cover_id = album.cover_photo_id or session.scalar(
        select(PhotoAlbum.photo_id).where(PhotoAlbum.album_id == album.id).order_by(PhotoAlbum.position).limit(1)
    )
    cover_url = None
    if cover_id:
        cover = session.get(Photo, cover_id, options=[selectinload(Photo.renditions)])
        if cover is not None:
            cover_url = thumb_url(cover, 512)[0]
    return {
        "id": album.id,
        "name": album.name,
        "description": album.description,
        "photo_count": count,
        "cover_thumb_url": cover_url,
        "created_at": album.created_at,
        "updated_at": album.updated_at,
    }
