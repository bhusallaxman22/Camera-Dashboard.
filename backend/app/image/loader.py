"""Decode originals into oriented RGB images without ever writing to them."""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

from PIL import Image, ImageCms, ImageOps

from app.config import get_settings
from app.log import get_logger
from app.metadata.exiftool import ExifToolError, extract_embedded_preview
from app.models.enums import FileType

log = get_logger(__name__)

Image.MAX_IMAGE_PIXELS = 400_000_000

try:  # HEIF (.HIF from the Z6III's HLG mode)
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

_SRGB = ImageCms.createProfile("sRGB")

# EXIF orientation -> PIL transpose ops (embedded RAW previews carry no tag).
_ORIENT_OPS: dict[int, list[Image.Transpose]] = {
    2: [Image.Transpose.FLIP_LEFT_RIGHT],
    3: [Image.Transpose.ROTATE_180],
    4: [Image.Transpose.FLIP_TOP_BOTTOM],
    5: [Image.Transpose.TRANSPOSE],
    6: [Image.Transpose.ROTATE_270],
    7: [Image.Transpose.TRANSVERSE],
    8: [Image.Transpose.ROTATE_90],
}


class DecodeError(RuntimeError):
    pass


def apply_orientation(img: Image.Image, orientation: int | None) -> Image.Image:
    for op in _ORIENT_OPS.get(orientation or 1, []):
        img = img.transpose(op)
    return img


def _to_srgb(img: Image.Image) -> Image.Image:
    icc = img.info.get("icc_profile")
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            img = ImageCms.profileToProfile(img.convert("RGB"), src, _SRGB, outputMode="RGB")
        except (ImageCms.PyCMSError, OSError, ValueError):
            pass
    return img.convert("RGB") if img.mode != "RGB" else img


def _open_display(path: Path, target_edge: int) -> Image.Image:
    img = Image.open(path)
    if img.format == "JPEG":
        # DCT-domain downscale: decodes a 24MP JPEG ~4x faster.
        img.draft("RGB", (target_edge, target_edge))
    img = ImageOps.exif_transpose(img)
    img.load()
    return _to_srgb(img)


def _open_raw(path: Path, orientation: int | None, target_edge: int) -> tuple[Image.Image, str]:
    try:
        data = extract_embedded_preview(path)
    except ExifToolError as exc:
        log.warning("raw_preview_exiftool_failed", category="THUMBNAIL", path=str(path), error=str(exc))
        data = None
    if data:
        img = Image.open(io.BytesIO(data))
        img.draft("RGB", (target_edge, target_edge))
        img.load()
        return apply_orientation(_to_srgb(img), orientation), "raw_embedded"

    # Fallback: LibRaw. Note it cannot decode Nikon High Efficiency NEFs.
    try:
        import rawpy

        with rawpy.imread(str(path)) as raw:
            try:
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    img = Image.open(io.BytesIO(thumb.data))
                    img.load()
                    return apply_orientation(_to_srgb(img), orientation), "raw_thumb"
            except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
                pass
            rgb = raw.postprocess(half_size=True, use_camera_wb=True, no_auto_bright=False)
            # rawpy already applies the sensor orientation.
            return Image.fromarray(rgb), "raw_decoded"
    except Exception as exc:
        raise DecodeError(f"cannot decode RAW {path.name}: {exc}") from exc


def _open_video(path: Path) -> Image.Image:
    ffmpeg = get_settings().ffmpeg_path
    for seek in ("1", "0"):
        try:
            proc = subprocess.run(
                [
                    ffmpeg,
                    "-v",
                    "error",
                    "-ss",
                    seek,
                    "-i",
                    str(path),
                    "-frames:v",
                    "1",
                    "-f",
                    "image2pipe",
                    "-vcodec",
                    "mjpeg",
                    "-q:v",
                    "3",
                    "-",
                ],
                capture_output=True,
                timeout=60,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise DecodeError(f"ffmpeg unavailable or timed out: {exc}") from exc
        if proc.stdout:
            img = Image.open(io.BytesIO(proc.stdout))
            img.load()
            return img.convert("RGB")
    raise DecodeError(f"no video frame could be extracted from {path.name}")


def load_image(
    path: Path, file_type: str, *, orientation: int | None = None, target_edge: int = 2560
) -> tuple[Image.Image, str]:
    """Return (oriented sRGB image, source description)."""
    try:
        if file_type in (FileType.JPEG, FileType.IMAGE):
            return _open_display(path, target_edge), file_type
        if file_type == FileType.RAW:
            return _open_raw(path, orientation, target_edge)
        if file_type == FileType.VIDEO:
            return _open_video(path), "video_frame"
    except DecodeError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise DecodeError(f"cannot decode {path.name}: {exc}") from exc
    raise DecodeError(f"unsupported file type {file_type}")
