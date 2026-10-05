"""Preview + thumbnail generation. Output goes only under DATA_ROOT."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from app.config import get_settings
from app.image.loader import load_image
from app.log import get_logger
from app.models import Photo, PhotoFile, Rendition
from app.models.enums import FileType, RenditionKind
from app.observability.metrics import THUMBNAIL_SECONDS

log = get_logger(__name__)

RENDITION_VERSION = "1"
SOURCE_PRIORITY = {FileType.JPEG: 0, FileType.IMAGE: 1, FileType.RAW: 2, FileType.VIDEO: 3}


@dataclass(slots=True)
class RenderResult:
    generated: bool
    source_file_id: str | None
    source: str | None
    duration_ms: int = 0


def choose_source(photo: Photo) -> PhotoFile | None:
    """Camera JPEG first (exactly what the camera rendered), then embedded RAW preview."""
    live = [f for f in photo.files if f.exists and f.duplicate_of_id is None]
    if not live:
        return None
    return min(live, key=lambda f: SOURCE_PRIORITY.get(FileType(f.file_type), 9))


def fingerprint(source: PhotoFile) -> str:
    s = get_settings()
    sizes = ",".join(str(x) for x in s.thumbnail_sizes)
    ident = source.checksum or f"{source.file_size}-{source.modification_time.timestamp():.0f}"
    descriptor = (
        f"v{RENDITION_VERSION}:{source.id}:{ident}:{s.preview_max_edge}:{s.preview_quality}:"
        f"{sizes}:{s.thumbnail_quality}:{source.photo.orientation or 1}"
    )
    return hashlib.sha256(descriptor.encode()).hexdigest()


def _shard(photo_id: str) -> str:
    return photo_id[:2]


def _atomic_save(img: Image.Image, dest: Path, fmt: str, **params: object) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".tmp-", suffix=dest.suffix)
    try:
        with os.fdopen(fd, "wb") as fh:
            img.save(fh, fmt, **params)
        os.replace(tmp, dest)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return dest.stat().st_size


def _resized(img: Image.Image, max_edge: int) -> Image.Image:
    if max(img.size) <= max_edge:
        return img.copy()
    out = img.copy()
    out.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS, reducing_gap=3.0)
    return out


def renditions_current(photo: Photo) -> bool:
    source = choose_source(photo)
    if source is None:
        return True
    fp = fingerprint(source)
    settings = get_settings()
    expected = {RenditionKind.PREVIEW.value} | {RenditionKind.thumb(s) for s in settings.thumbnail_sizes}
    have = {r.kind: r for r in photo.renditions}
    if set(have) < expected:
        return False
    return all(have[k].source_fingerprint == fp and (settings.data_root / have[k].path).exists() for k in expected)


def render_photo(session: Session, photo: Photo, *, force: bool = False) -> RenderResult:
    """Generate preview + thumbnails if missing or stale."""
    started = time.perf_counter()
    settings = get_settings()
    source = choose_source(photo)
    if source is None:
        return RenderResult(False, None, None)
    if not force and renditions_current(photo):
        return RenderResult(False, str(source.id), None)

    fp = fingerprint(source)
    with THUMBNAIL_SECONDS.time():
        img, how = load_image(
            Path(source.absolute_path),
            source.file_type,
            orientation=photo.orientation,
            target_edge=settings.preview_max_edge,
        )
        pid = str(photo.id)
        existing = {r.kind: r for r in photo.renditions}

        preview = _resized(img, settings.preview_max_edge)
        img.close()
        outputs: list[tuple[str, Image.Image, Path, str, dict]] = [
            (
                RenditionKind.PREVIEW.value,
                preview,
                settings.preview_root / _shard(pid) / f"{pid}.jpg",
                "JPEG",
                {"quality": settings.preview_quality, "optimize": True, "progressive": True},
            )
        ]
        # Thumbnails are derived from the preview (largest first for quality).
        for size in sorted(settings.thumbnail_sizes, reverse=True):
            outputs.append(
                (
                    RenditionKind.thumb(size),
                    _resized(preview, size),
                    settings.thumbnail_root / _shard(pid) / f"{pid}_{size}.webp",
                    "WEBP",
                    {"quality": settings.thumbnail_quality, "method": 4},
                )
            )

        for kind, im, dest, fmt, params in outputs:
            nbytes = _atomic_save(im, dest, fmt, **params)
            rel = dest.relative_to(settings.data_root).as_posix()
            row = existing.get(kind)
            if row is None:
                row = Rendition(photo_id=photo.id, kind=kind)
                photo.renditions.append(row)
            row.path, row.format = rel, fmt.lower()
            row.width, row.height = im.size
            row.file_size, row.source_file_id, row.source_fingerprint = nbytes, source.id, fp
            if im is not preview:
                im.close()
        preview.close()

    duration = int((time.perf_counter() - started) * 1000)
    log.info(
        "renditions_generated",
        category="THUMBNAIL",
        photo_id=pid,
        source=how,
        file=source.filename,
        duration_ms=duration,
    )
    return RenderResult(True, str(source.id), how, duration)


def rendition_for(photo: Photo, kind: str) -> Rendition | None:
    return next((r for r in photo.renditions if r.kind == kind), None)


def best_thumbnail(photo: Photo, size: int) -> Rendition | None:
    """Smallest thumbnail >= size, else the largest available."""
    thumbs = sorted((r for r in photo.renditions if r.kind.startswith("thumb_")), key=lambda r: r.width)
    for r in thumbs:
        if max(r.width, r.height) >= size:
            return r
    return thumbs[-1] if thumbs else rendition_for(photo, RenditionKind.PREVIEW.value)
