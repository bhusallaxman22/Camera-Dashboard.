from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.metadata.exiftool import ExifDump, extract_embedded_preview, read_metadata
from app.metadata.parser import parse_exif_datetime, parse_metadata, pretty_camera
from app.utils.format import format_ev, format_shutter
from tests.conftest import requires_exiftool, requires_z8, write_capture

NIKON_LONG_JSON = {
    "SourceFile": "/photos/raw/2026/09/30/DSC_1234.NEF",
    "EXIF:Make": {"desc": "Make", "val": "NIKON CORPORATION"},
    "EXIF:Model": {"desc": "Camera Model Name", "val": "NIKON Z6_3"},
    "MakerNotes:SerialNumber": {"desc": "Serial Number", "val": 7012345},
    "MakerNotes:ShutterCount": {"desc": "Shutter Count", "val": 4821},
    "EXIF:ExposureTime": {"desc": "Exposure Time", "num": 0.002, "val": "1/500"},
    "EXIF:FNumber": {"desc": "F Number", "val": 1.4},
    "EXIF:ISO": {"desc": "ISO", "val": 400},
    "EXIF:ExposureCompensation": {"desc": "Exposure Compensation", "num": -0.3333333, "val": "-1/3"},
    "EXIF:FocalLength": {"desc": "Focal Length", "num": 50, "val": "50.0 mm"},
    "EXIF:FocalLengthIn35mmFormat": {"desc": "Focal Length 35", "num": 50, "val": "50 mm"},
    "EXIF:MeteringMode": {"desc": "Metering Mode", "num": 5, "val": "Multi-segment"},
    "EXIF:ExposureProgram": {"desc": "Exposure Program", "num": 3, "val": "Aperture-priority AE"},
    "EXIF:Orientation": {"desc": "Orientation", "num": 6, "val": "Rotate 90 CW"},
    "EXIF:OffsetTimeOriginal": {"desc": "Offset", "val": "-05:00"},
    "Composite:SubSecDateTimeOriginal": {"desc": "Date", "val": "2026:09:30 14:22:05.37-05:00"},
    "Composite:LensID": {"desc": "Lens ID", "val": "NIKKOR Z 50mm f/1.4"},
    "Composite:ImageSize": {"desc": "Image Size", "num": "6048 4032", "val": "6048x4032"},
    "MakerNotes:FocusMode": {"desc": "Focus Mode", "num": "AF-C  ", "val": "AF-C"},
    "MakerNotes:AFAreaMode": {"desc": "AF Area Mode", "val": "Auto (People)"},
    "MakerNotes:PictureControlName": {"desc": "PC", "val": "Standard"},
    "MakerNotes:WhiteBalance": {"desc": "WB", "val": "Auto1"},
    "MakerNotes:Quality": {"desc": "Quality", "val": "RAW + Fine"},
    "MakerNotes:VibrationReduction": {"desc": "VR", "val": "On"},
    "MakerNotes:NEFCompression": {"desc": "NEF", "val": "High Efficiency*"},
    "MakerNotes:SomethingNew": {"desc": "New", "val": "kept"},
    "Composite:GPSLatitude": {"desc": "Lat", "num": 41.8781, "val": "41 deg 52' 41.16\" N"},
    "Composite:GPSLongitude": {"desc": "Lon", "num": -87.6298, "val": "87 deg 37' 47.28\" W"},
}


def test_from_long_json_splits_printed_and_numeric() -> None:
    d = ExifDump.from_long_json(NIKON_LONG_JSON)
    assert d.printed["EXIF:ExposureTime"] == "1/500"
    assert d.numeric["EXIF:ExposureTime"] == 0.002
    assert "EXIF:FNumber" not in d.numeric  # identical values aren't duplicated
    assert d.get("EXIF:ExposureTime", numeric=True) == 0.002
    assert d.printed["MakerNotes:SomethingNew"] == "kept"  # unknown tags preserved


def test_parse_nikon_metadata() -> None:
    pm = parse_metadata(ExifDump.from_long_json(NIKON_LONG_JSON))
    assert pm.camera_model == "NIKON Z6_3"
    assert pm.camera_serial == "7012345"
    assert pm.shutter_count == 4821
    assert pm.lens_model == "NIKKOR Z 50mm f/1.4"
    assert pm.focal_length == 50
    assert pm.aperture == 1.4
    assert pm.shutter_speed == pytest.approx(1 / 500)
    assert pm.iso == 400
    assert pm.exposure_compensation == pytest.approx(-1 / 3, abs=1e-3)
    assert pm.metering_mode == "Multi-segment"
    assert pm.focus_mode == "AF-C"
    assert pm.af_area_mode == "Auto (People)"
    assert pm.orientation == 6
    assert (pm.image_width, pm.image_height) == (6048, 4032)
    assert pm.capture_time == datetime(2026, 9, 30, 19, 22, 5, 370000, tzinfo=UTC)
    assert pm.capture_tz_offset == "-05:00"
    assert pm.gps_latitude == pytest.approx(41.8781)
    assert pm.extra["vibration_reduction"] == "On"
    assert pm.extra["nef_compression"] == "High Efficiency*"


def test_parse_missing_exif_is_empty_not_error() -> None:
    pm = parse_metadata(ExifDump())
    assert pm.capture_time is None and pm.camera_model is None and pm.extra == {}


@pytest.mark.parametrize(
    ("raw", "offset", "expected_utc"),
    [
        ("2026:09:30 14:22:05", "-05:00", datetime(2026, 9, 30, 19, 22, 5, tzinfo=UTC)),
        ("2026:09:30 14:22:05.5+02:00", None, datetime(2026, 9, 30, 12, 22, 5, 500000, tzinfo=UTC)),
        ("2026:09:30 14:22:05Z", None, datetime(2026, 9, 30, 14, 22, 5, tzinfo=UTC)),
    ],
)
def test_parse_exif_datetime(raw: str, offset: str | None, expected_utc: datetime) -> None:
    dt, _ = parse_exif_datetime(raw, offset)
    assert dt == expected_utc


def test_parse_exif_datetime_naive_uses_local_tz() -> None:
    dt, off = parse_exif_datetime("2026:01:15 10:00:00")
    assert off is None
    assert dt is not None and dt.utcoffset() == timedelta(hours=-6)  # America/Chicago (CST)


@pytest.mark.parametrize("bad", ["0000:00:00 00:00:00", "garbage", None, "2026:02:30 10:00:00"])
def test_parse_exif_datetime_invalid(bad: str | None) -> None:
    assert parse_exif_datetime(bad) == (None, None)


def test_pretty_camera() -> None:
    assert pretty_camera("NIKON CORPORATION", "NIKON Z6_3") == "Nikon Z6III"
    assert pretty_camera("NIKON CORPORATION", "NIKON Z 6_2") == "Nikon Z 6II"
    assert pretty_camera("NIKON CORPORATION", "NIKON Z 8") == "Nikon Z 8"
    assert pretty_camera("Canon", "Canon EOS R5") == "Canon EOS R5"


def test_formatters() -> None:
    assert format_shutter(1 / 500) == "1/500"
    assert format_shutter(2.0) == '2"'
    assert format_ev(1 / 3) == "+1/3 EV"
    assert format_ev(-2 / 3) == "-2/3 EV"
    assert format_ev(-1.3333) == "-1 1/3 EV"
    assert format_ev(0) == "0 EV"


@requires_exiftool
def test_exiftool_reads_generated_jpeg(env) -> None:
    files = write_capture(env["photos"], "DSC_0001", datetime(2026, 9, 30, 9, 0, 0, 250000), raw=False)
    pm = parse_metadata(read_metadata(files["jpeg"]))
    assert pm.camera_model == "NIKON Z6_3"
    assert pm.lens_model == "NIKKOR Z 50mm f/1.4"
    assert pm.aperture == 1.4
    assert pm.capture_time == datetime(2026, 9, 30, 9, 0, 0, 250000, tzinfo=timezone(timedelta(hours=-5)))


@requires_z8
def test_real_nikon_nef(env) -> None:
    from tests.conftest import Z8_NEF

    pm = parse_metadata(read_metadata(Path(Z8_NEF)))
    assert pm.camera_model == "NIKON Z 8"
    assert pm.shutter_count == 2567
    assert pm.lens_model == "NIKKOR Z 14-24mm f/2.8 S"
    assert pm.extra["nef_compression"] == "High Efficiency"
    preview = extract_embedded_preview(Path(Z8_NEF))
    assert preview is not None and preview[:2] == b"\xff\xd8" and len(preview) > 1_000_000
