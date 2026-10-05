from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from app.models.enums import FileType

JPEG_EXTENSIONS = {".jpg", ".jpeg"}
# .hif is Nikon's HEIF extension (HLG tone mode).
IMAGE_EXTENSIONS = {".heic", ".heif", ".hif", ".png", ".tif", ".tiff"}
RAW_EXTENSIONS = {".nef", ".nrw", ".dng", ".cr2", ".cr3", ".arw", ".raf", ".orf", ".rw2"}
# .nev is Nikon N-RAW video.
VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".nev", ".avi", ".mts"}

# Partial uploads / OS junk that must never be ingested.
_IGNORED_SUFFIXES = (".part", ".filepart", ".tmp", ".crdownload", ".partial", "~")
_IGNORED_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".hif": "image/heif",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".nef": "image/x-nikon-nef",
    ".nrw": "image/x-nikon-nrw",
    ".dng": "image/x-adobe-dng",
    ".mov": "video/quicktime",
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
}

_DATE_DIR_RE = re.compile(r"(?:^|/)(\d{4})/(\d{2})/(\d{2})(?:/|$)")


class UnsafePathError(ValueError):
    """Raised when a path escapes the approved roots."""


def classify(path: Path | str) -> FileType | None:
    name = Path(path).name
    lower = name.lower()
    if lower.startswith(".") or lower.startswith("._") or lower in _IGNORED_NAMES:
        return None
    if lower.endswith(_IGNORED_SUFFIXES):
        return None
    ext = Path(lower).suffix
    if ext in JPEG_EXTENSIONS:
        return FileType.JPEG
    if ext in IMAGE_EXTENSIONS:
        return FileType.IMAGE
    if ext in RAW_EXTENSIONS:
        return FileType.RAW
    if ext in VIDEO_EXTENSIONS:
        return FileType.VIDEO
    return None


def mime_type_for(path: Path | str) -> str | None:
    return MIME_TYPES.get(Path(path).suffix.lower())


# Re-uploads of one capture get renamed: the camera's FTP client appends `-N`
# when retrying an interrupted transfer (`DSC_0117-1.JPG`) and the sorter
# appends the upload time on a name clash (`DSC_0111_072752.JPG`). Only strip
# these from standard Nikon names so arbitrary filenames are left alone.
_REUPLOAD_SUFFIX_RE = re.compile(r"^((?:[A-Za-z0-9]{3}_|_[A-Za-z0-9]{3})\d{4})(?:-\d{1,3})?(?:_\d{6})?$")


def base_name(path: Path | str) -> str:
    """`DSC_1234.JPG`, `DSC_1234-1.JPG`, `DSC_1234_072752.JPG` -> `DSC_1234`."""
    stem = Path(path).stem
    m = _REUPLOAD_SUFFIX_RE.match(stem)
    return m.group(1) if m else stem


def date_from_directory(path: Path | str) -> date | None:
    """Extract the YYYY/MM/DD date the FTP sorter encodes in the path."""
    m = _DATE_DIR_RE.search(Path(path).as_posix())
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_under_roots(candidate: Path | str, roots: list[Path]) -> Path:
    """Resolve `candidate` (following symlinks) and require it to live under a root.

    Used for every filesystem access driven by external input (watcher events,
    API downloads). Raises UnsafePathError for traversal/symlink escapes.
    """
    p = Path(candidate)
    if "\x00" in str(p):
        raise UnsafePathError("NUL byte in path")
    resolved = p.resolve(strict=False)
    for root in roots:
        root_resolved = root.resolve(strict=False)
        if is_within(resolved, root_resolved):
            return resolved
    raise UnsafePathError(f"path is outside approved roots: {candidate}")


def relative_to_root(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name
