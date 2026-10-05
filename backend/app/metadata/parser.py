from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from app.metadata.exiftool import ExifDump
from app.utils.timeutil import local_tz

_DT_RE = re.compile(r"^(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?\s*(Z|[+-]\d{2}:?\d{2})?")

# Maker-note tags worth surfacing that have no dedicated column.
CURATED_TAGS: dict[str, tuple[str, ...]] = {
    "vibration_reduction": ("MakerNotes:VibrationReduction",),
    "vr_mode": ("MakerNotes:VRMode",),
    "shutter_mode": ("MakerNotes:ShutterMode",),
    "release_mode": ("MakerNotes:ReleaseMode", "MakerNotes:ShootingMode"),
    "subject_detection": ("MakerNotes:SubjectDetection",),
    "nef_compression": ("MakerNotes:NEFCompression",),
    "nef_bit_depth": ("MakerNotes:NEFBitDepth",),
    "image_area": ("MakerNotes:ImageAreaFormat", "MakerNotes:PhotoShootingMenuBankImageArea"),
    "active_d_lighting": ("MakerNotes:ActiveD-Lighting",),
    "high_iso_nr": ("MakerNotes:HighISONoiseReduction",),
    "auto_iso": ("MakerNotes:AutoISO",),
    "focus_distance": ("MakerNotes:FocusDistance",),
    "af_points_used": ("MakerNotes:AFPointsUsed",),
    "lens_spec": ("Composite:LensSpec",),
    "lens_firmware": ("MakerNotes:LensFirmwareVersion",),
    "dof": ("Composite:DOF",),
    "light_value": ("Composite:LightValue",),
    "megapixels": ("Composite:Megapixels",),
    "tone_mode": ("MakerNotes:ToneMode", "MakerNotes:HDR"),
    "video_frame_rate": ("QuickTime:VideoFrameRate",),
    "video_codec": ("QuickTime:CompressorName", "QuickTime:CompressorID"),
}


@dataclass(slots=True)
class ParsedMetadata:
    capture_time: datetime | None = None
    capture_tz_offset: str | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    camera_serial: str | None = None
    shutter_count: int | None = None
    firmware: str | None = None
    lens_model: str | None = None
    focal_length: float | None = None
    focal_length_35mm: float | None = None
    aperture: float | None = None
    shutter_speed: float | None = None
    iso: int | None = None
    exposure_compensation: float | None = None
    exposure_program: str | None = None
    metering_mode: str | None = None
    white_balance: str | None = None
    flash: str | None = None
    focus_mode: str | None = None
    af_area_mode: str | None = None
    picture_control: str | None = None
    image_quality: str | None = None
    image_width: int | None = None
    image_height: int | None = None
    orientation: int | None = None
    color_space: str | None = None
    duration_seconds: float | None = None
    gps_latitude: float | None = None
    gps_longitude: float | None = None
    gps_altitude: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_photo_fields(self) -> dict[str, Any]:
        return asdict(self)


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip().strip("\x00").strip()
    if not s or s.lower() in {"unknown", "n/a", "none", "0000"}:
        return None
    return s


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    s = str(value).strip()
    m = re.match(r"^([+-]?\d+)/(\d+)", s)
    if m and int(m.group(2)):
        return int(m.group(1)) / int(m.group(2))
    m = re.match(r"^[+-]?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def _to_int(value: Any) -> int | None:
    f = _to_float(value)
    return round(f) if f is not None else None


def parse_exif_datetime(value: Any, offset: str | None = None) -> tuple[datetime | None, str | None]:
    """Parse `YYYY:MM:DD HH:MM:SS[.ss][+HH:MM]`. Naive times use the local TZ."""
    if value is None:
        return None, None
    m = _DT_RE.match(str(value).strip())
    if not m:
        return None, None
    y, mo, d, h, mi, s, frac, tz = m.groups()
    if y == "0000":
        return None, None
    try:
        micro = int((frac or "0")[:6].ljust(6, "0"))
        dt = datetime(int(y), int(mo), int(d), int(h), int(mi), int(s), micro)
    except ValueError:
        return None, None
    tz = tz or (offset.strip() if offset else None)
    if tz:
        if tz == "Z":
            return dt.replace(tzinfo=UTC), "+00:00"
        sign = 1 if tz[0] == "+" else -1
        digits = tz[1:].replace(":", "")
        try:
            delta = timedelta(hours=int(digits[:2]), minutes=int(digits[2:4] or 0))
        except ValueError:
            delta = None
        if delta is not None:
            norm = f"{tz[0]}{digits[:2]}:{digits[2:4] or '00'}"
            return dt.replace(tzinfo=timezone(sign * delta)), norm
    return dt.replace(tzinfo=local_tz()), None


def _capture_time(d: ExifDump) -> tuple[datetime | None, str | None]:
    offset = _clean_str(d.get("EXIF:OffsetTimeOriginal", "EXIF:OffsetTime"))
    for key in (
        "Composite:SubSecDateTimeOriginal",
        "EXIF:DateTimeOriginal",
        "XMP:DateTimeOriginal",
        "QuickTime:DateTimeOriginal",
        "Keys:CreationDate",
        "UserData:DateTimeOriginal",
        "Composite:SubSecCreateDate",
        "EXIF:CreateDate",
        "QuickTime:CreateDate",
    ):
        raw = d.get(key)
        if raw is None:
            continue
        if key == "EXIF:DateTimeOriginal":
            sub = _clean_str(d.get("EXIF:SubSecTimeOriginal"))
            if sub and sub.isdigit() and "." not in str(raw):
                raw = f"{raw}.{sub}"
        dt, off = parse_exif_datetime(raw, offset)
        if dt is not None:
            return dt, off
    return None, None


def _dimensions(d: ExifDump) -> tuple[int | None, int | None]:
    size = d.get("Composite:ImageSize", numeric=True)
    if size:
        parts = re.split(r"[x\s]+", str(size).strip())
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            return int(parts[0]), int(parts[1])
    for wk, hk in (
        ("File:ImageWidth", "File:ImageHeight"),
        ("EXIF:ExifImageWidth", "EXIF:ExifImageHeight"),
        ("QuickTime:ImageWidth", "QuickTime:ImageHeight"),
        ("PNG:ImageWidth", "PNG:ImageHeight"),
    ):
        w, h = _to_int(d.get(wk, numeric=True)), _to_int(d.get(hk, numeric=True))
        if w and h:
            return w, h
    return None, None


def _lens(d: ExifDump) -> str | None:
    lens_id = _clean_str(d.get("Composite:LensID"))
    # LensID falls back to a hex/numeric id when the lens is not in the database.
    if lens_id and not re.fullmatch(r"[0-9A-Fa-f ]+", lens_id) and "Unknown" not in lens_id:
        return lens_id
    return _clean_str(d.get("EXIF:LensModel", "MakerNotes:Lens", "Composite:LensSpec"))


def _color_space(d: ExifDump) -> str | None:
    interop = _clean_str(d.get("InteropIFD:InteropIndex", "EXIF:InteropIndex"))
    if interop and interop.upper().startswith("R03"):
        return "Adobe RGB"
    cs = _clean_str(d.get("MakerNotes:ColorSpace", "EXIF:ColorSpace", "ICC_Profile:ProfileDescription"))
    return cs


def parse_metadata(d: ExifDump) -> ParsedMetadata:
    capture_time, tz_offset = _capture_time(d)
    width, height = _dimensions(d)
    serial = _clean_str(d.get("MakerNotes:SerialNumber", "EXIF:SerialNumber", "EXIF:BodySerialNumber"))
    pm = ParsedMetadata(
        capture_time=capture_time,
        capture_tz_offset=tz_offset,
        camera_make=_clean_str(d.get("EXIF:Make", "QuickTime:Make", "Nikon:Make")),
        camera_model=_clean_str(d.get("EXIF:Model", "QuickTime:Model", "UserData:Model")),
        camera_serial=serial,
        shutter_count=_to_int(d.get("MakerNotes:ShutterCount", numeric=True)),
        firmware=_clean_str(d.get("EXIF:Software", "MakerNotes:FirmwareVersion")),
        lens_model=_lens(d),
        focal_length=_to_float(d.get("EXIF:FocalLength", numeric=True)),
        focal_length_35mm=_to_float(d.get("EXIF:FocalLengthIn35mmFormat", numeric=True)),
        aperture=_to_float(d.get("EXIF:FNumber", "Composite:Aperture", numeric=True)),
        shutter_speed=_to_float(d.get("EXIF:ExposureTime", "Composite:ShutterSpeed", numeric=True)),
        iso=_to_int(d.get("EXIF:ISO", "MakerNotes:ISO", numeric=True)),
        exposure_compensation=_to_float(d.get("EXIF:ExposureCompensation", numeric=True)),
        exposure_program=_clean_str(d.get("EXIF:ExposureProgram")),
        metering_mode=_clean_str(d.get("EXIF:MeteringMode")),
        white_balance=_clean_str(d.get("MakerNotes:WhiteBalance", "EXIF:WhiteBalance")),
        flash=_clean_str(d.get("EXIF:Flash")),
        focus_mode=_clean_str(d.get("MakerNotes:FocusMode")),
        af_area_mode=_clean_str(d.get("MakerNotes:AFAreaMode")),
        picture_control=_clean_str(d.get("MakerNotes:PictureControlName")),
        image_quality=_clean_str(d.get("MakerNotes:Quality")),
        image_width=width,
        image_height=height,
        orientation=_to_int(d.get("EXIF:Orientation", numeric=True)),
        color_space=_color_space(d),
        duration_seconds=_to_float(d.get("QuickTime:Duration", "Composite:Duration", numeric=True)),
        gps_latitude=_to_float(d.get("Composite:GPSLatitude", numeric=True)),
        gps_longitude=_to_float(d.get("Composite:GPSLongitude", numeric=True)),
        gps_altitude=_to_float(d.get("Composite:GPSAltitude", numeric=True)),
    )
    extra: dict[str, Any] = {}
    for name, keys in CURATED_TAGS.items():
        val = _clean_str(d.get(*keys))
        if val is not None:
            extra[name] = val
    pm.extra = extra
    return pm


def pretty_camera(make: str | None, model: str | None) -> str | None:
    """`NIKON Z6_3` -> `Nikon Z6III`; leaves other brands mostly untouched."""
    if not model:
        return make
    name = model.strip()
    if name.upper().startswith("NIKON "):
        name = "Nikon " + name[6:]
    elif make and make.upper().startswith("NIKON"):
        name = "Nikon " + name
    name = re.sub(r"_3\b", "III", name)
    name = re.sub(r"_2\b", "II", name)
    return name
