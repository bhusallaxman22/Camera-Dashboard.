"""Synthetic Nikon-like sample files for development, demos and tests.

Generates JPEGs with realistic EXIF (and fake `.NEF` companions that embed the
JPEG as a preview) in a sorter-style YYYY/MM/DD layout. Never point this at the
real camera library.
"""

from __future__ import annotations

import io
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

EXIF_TAGS = {
    "Make": 0x010F,
    "Model": 0x0110,
    "Orientation": 0x0112,
    "Software": 0x0131,
    "DateTime": 0x0132,
}
EXIF_IFD = {
    "ExposureTime": 0x829A,
    "FNumber": 0x829D,
    "ISO": 0x8827,
    "DateTimeOriginal": 0x9003,
    "OffsetTimeOriginal": 0x9011,
    "ExposureBias": 0x9204,
    "MeteringMode": 0x9207,
    "FocalLength": 0x920A,
    "SubSecTimeOriginal": 0x9291,
    "FocalLength35": 0xA405,
    "BodySerial": 0xA431,
    "LensModel": 0xA434,
}


def synthetic_image(width: int, height: int, seed: int, *, blur: float = 0.0, brightness: float = 1.0) -> Image.Image:
    rng = random.Random(seed)
    y, x = np.mgrid[0:height, 0:width]
    base = np.stack(
        [
            128 + 90 * np.sin(x / (width / (2 + rng.random() * 3)) + rng.random() * 6),
            128 + 90 * np.cos(y / (height / (2 + rng.random() * 3))),
            128 + 60 * np.sin((x + y) / (width / 4)),
        ],
        axis=-1,
    )
    img = Image.fromarray(np.clip(base * brightness, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(img)
    for _ in range(25):
        x0, y0 = rng.randrange(width), rng.randrange(height)
        r = rng.randrange(10, max(11, width // 8))
        color = tuple(rng.randrange(256) for _ in range(3))
        draw.ellipse((x0 - r, y0 - r, x0 + r, y0 + r), outline=color, width=3)
        draw.line((x0, y0, x0 + r * math.cos(r), y0 + r * math.sin(r)), fill=color, width=2)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    return img


def jpeg_bytes(
    img: Image.Image,
    capture: datetime,
    *,
    model: str = "NIKON Z6_3",
    serial: str = "7000123",
    lens: str = "NIKKOR Z 50mm f/1.4",
    focal: float = 50.0,
    fnumber: float = 1.4,
    exposure: float = 1 / 500,
    iso: int = 400,
    bias: float = -0.3,
    orientation: int = 1,
    offset: str = "-05:00",
) -> bytes:
    exif = Image.Exif()
    exif[EXIF_TAGS["Make"]] = "NIKON CORPORATION"
    exif[EXIF_TAGS["Model"]] = model
    exif[EXIF_TAGS["Orientation"]] = orientation
    exif[EXIF_TAGS["Software"]] = "Ver.01.10"
    exif[EXIF_TAGS["DateTime"]] = capture.strftime("%Y:%m:%d %H:%M:%S")
    ifd = exif.get_ifd(0x8769)
    ifd[EXIF_IFD["ExposureTime"]] = exposure
    ifd[EXIF_IFD["FNumber"]] = fnumber
    ifd[EXIF_IFD["ISO"]] = iso
    ifd[EXIF_IFD["DateTimeOriginal"]] = capture.strftime("%Y:%m:%d %H:%M:%S")
    ifd[EXIF_IFD["SubSecTimeOriginal"]] = f"{capture.microsecond // 10000:02d}"
    ifd[EXIF_IFD["OffsetTimeOriginal"]] = offset
    ifd[EXIF_IFD["ExposureBias"]] = bias
    ifd[EXIF_IFD["MeteringMode"]] = 5
    ifd[EXIF_IFD["FocalLength"]] = focal
    ifd[EXIF_IFD["FocalLength35"]] = int(focal)
    ifd[EXIF_IFD["BodySerial"]] = serial
    ifd[EXIF_IFD["LensModel"]] = lens
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90, exif=exif.tobytes())
    return buf.getvalue()


def fake_nef_bytes(jpeg: bytes) -> bytes:
    """A TIFF container (like a NEF) whose payload includes the JPEG preview.

    Real NEFs are TIFF-based; ExifTool reads EXIF from this and the app's RAW
    path falls back to JPEG-from-RAW extraction. Content differs from the JPEG
    so checksums never collide.
    """
    img = Image.open(io.BytesIO(jpeg))
    exif = img.getexif()
    buf = io.BytesIO()
    img.convert("RGB").resize((max(1, img.width // 8), max(1, img.height // 8))).save(buf, "TIFF", exif=exif.tobytes())
    return buf.getvalue() + b"NEF-SAMPLE" + jpeg


def generate_library(
    root: Path,
    *,
    count: int = 12,
    start: datetime | None = None,
    with_raw: bool = True,
    burst_every: int = 4,
    size: tuple[int, int] = (1200, 800),
    start_index: int = 1000,
) -> list[Path]:
    """Write `count` captures into root/immich-jpeg and root/raw (sorter layout)."""
    start = start or datetime.now().replace(microsecond=0) - timedelta(minutes=count)
    written: list[Path] = []
    t = start
    for i in range(count):
        in_burst = burst_every and i % burst_every in (1, 2)
        t = t + (timedelta(milliseconds=200) if in_burst else timedelta(seconds=37))
        name = f"DSC_{(start_index + i) % 10000:04d}"
        day = t.strftime("%Y/%m/%d")
        img = synthetic_image(*size, seed=i, blur=4.0 if i % 5 == 4 else 0.0, brightness=1.4 if i % 7 == 6 else 1.0)
        data = jpeg_bytes(img, t, iso=[100, 400, 1600, 6400][i % 4], fnumber=[1.4, 2.8, 5.6, 8][i % 4])
        jpg = root / "immich-jpeg" / day / f"{name}.JPG"
        jpg.parent.mkdir(parents=True, exist_ok=True)
        jpg.write_bytes(data)
        written.append(jpg)
        if with_raw:
            nef = root / "raw" / day / f"{name}.NEF"
            nef.parent.mkdir(parents=True, exist_ok=True)
            nef.write_bytes(fake_nef_bytes(data))
            written.append(nef)
    return written
