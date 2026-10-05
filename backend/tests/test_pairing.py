from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models import Photo, PhotoFile
from app.services.ingest import ingest_path
from app.services.pairing import PairingInput, score_candidate
from tests.conftest import requires_exiftool, requires_z8, write_capture

T0 = datetime(2026, 9, 30, 14, 0, 0, 120000)

pytestmark = requires_exiftool


def _photos(db) -> list[Photo]:
    return list(db.scalars(select(Photo)).all())


def test_jpeg_first_then_raw_creates_one_photo(env, db) -> None:
    f = write_capture(env["photos"], "DSC_1234", T0)
    a = ingest_path(db, f["jpeg"], source="scan")
    db.commit()
    b = ingest_path(db, f["raw"], source="scan")
    db.commit()
    assert a.status == "created" and b.status == "paired"
    assert a.photo_id == b.photo_id
    photos = _photos(db)
    assert len(photos) == 1
    p = photos[0]
    assert p.base_filename == "DSC_1234"
    assert p.has_jpeg and p.has_raw
    assert sorted(f.file_type for f in p.files) == ["jpeg", "raw"]
    assert "capture_time" in b.pair_reason


def test_raw_first_then_jpeg_creates_one_photo(env, db) -> None:
    f = write_capture(env["photos"], "DSC_2000", T0)
    a = ingest_path(db, f["raw"], source="scan")
    db.commit()
    b = ingest_path(db, f["jpeg"], source="scan")
    db.commit()
    assert (a.status, b.status) == ("created", "paired")
    p = _photos(db)[0]
    # Display file wins for dimensions; fake NEF has a tiny embedded image.
    assert (p.image_width, p.image_height) == (900, 600)


def test_jpeg_only_and_raw_only(env, db) -> None:
    j = write_capture(env["photos"], "DSC_3000", T0, raw=False)
    r = write_capture(env["photos"], "DSC_3001", T0 + timedelta(seconds=5), jpeg=False)
    ingest_path(db, j["jpeg"], source="scan")
    ingest_path(db, r["raw"], source="scan")
    db.commit()
    by_name = {p.base_filename: p for p in _photos(db)}
    assert by_name["DSC_3000"].has_jpeg and not by_name["DSC_3000"].has_raw
    assert by_name["DSC_3001"].has_raw and not by_name["DSC_3001"].has_jpeg


def test_counter_rollover_same_name_different_time_is_new_photo(env, db) -> None:
    first = write_capture(env["photos"], "DSC_0001", T0)
    later = T0 + timedelta(days=40)
    second = write_capture(env["photos"], "DSC_0001", later, seed=7)
    for p in (first["jpeg"], first["raw"], second["jpeg"], second["raw"]):
        ingest_path(db, p, source="scan")
        db.commit()
    photos = _photos(db)
    assert len(photos) == 2
    assert all(p.has_jpeg and p.has_raw for p in photos)


def test_second_camera_same_name_same_time_not_paired(env, db) -> None:
    a = write_capture(env["photos"], "DSC_5000", T0, raw=False, serial="1111111")
    b = write_capture(env["photos"], "DSC_5000", T0, jpeg=False, serial="2222222")
    ingest_path(db, a["jpeg"], source="scan")
    db.commit()
    out = ingest_path(db, b["raw"], source="scan")
    db.commit()
    assert out.status == "created"
    assert out.pair_reason and "serial_mismatch" in out.pair_reason
    assert len(_photos(db)) == 2


def test_capture_time_outside_window_not_paired(env, db) -> None:
    a = write_capture(env["photos"], "DSC_6000", T0, raw=False)
    b = write_capture(env["photos"], "DSC_6000", T0 + timedelta(seconds=30), jpeg=False, seed=3)
    ingest_path(db, a["jpeg"], source="scan")
    db.commit()
    out = ingest_path(db, b["raw"], source="scan")
    db.commit()
    assert out.status == "created"
    assert len(_photos(db)) == 2


def test_missing_exif_falls_back_to_directory_date_and_mtime(env, db) -> None:
    f = write_capture(env["photos"], "DSC_7000", T0)
    # Replace the RAW with a file that has no readable metadata at all.
    f["raw"].write_bytes(b"\x00" * 4096)
    ingest_path(db, f["jpeg"], source="scan")
    db.commit()
    out = ingest_path(db, f["raw"], source="scan")
    db.commit()
    assert out.status == "paired"
    assert out.pair_reason == "directory_date+mtime"
    assert out.warnings  # exiftool complaint recorded, not raised


def test_rescan_is_idempotent(env, db) -> None:
    f = write_capture(env["photos"], "DSC_8000", T0)
    for p in f.values():
        ingest_path(db, p, source="scan")
    db.commit()
    again = [ingest_path(db, p, source="scan") for p in f.values()]
    db.commit()
    assert {o.status for o in again} == {"unchanged"}
    assert db.scalar(select(func.count(Photo.id))) == 1
    assert db.scalar(select(func.count(PhotoFile.id))) == 2


def test_byte_identical_copy_is_duplicate_not_new_photo(env, db) -> None:
    f = write_capture(env["photos"], "DSC_9000", T0)
    ingest_path(db, f["jpeg"], source="scan")
    db.commit()
    copy = env["photos"] / "immich-jpeg" / "2026" / "10" / "01" / "DSC_9000 (1).JPG"
    copy.parent.mkdir(parents=True)
    shutil.copy2(f["jpeg"], copy)
    out = ingest_path(db, copy, source="scan")
    db.commit()
    assert out.status == "duplicate"
    assert len(_photos(db)) == 1
    dup = db.scalars(select(PhotoFile).where(PhotoFile.absolute_path == str(copy.resolve()))).one()
    assert dup.duplicate_of_id is not None


def test_moved_file_is_relocated(env, db) -> None:
    f = write_capture(env["photos"], "DSC_9100", T0, raw=False)
    first = ingest_path(db, f["jpeg"], source="scan")
    db.commit()
    new = env["photos"] / "immich-jpeg" / "2026" / "09" / "29" / "DSC_9100.JPG"
    new.parent.mkdir(parents=True)
    f["jpeg"].rename(new)
    out = ingest_path(db, new, source="scan")
    db.commit()
    assert out.status == "moved" and out.file_id == first.file_id
    assert len(_photos(db)) == 1


def test_deleted_file_marked_missing_original_never_touched(env, db) -> None:
    f = write_capture(env["photos"], "DSC_9200", T0)
    for p in f.values():
        ingest_path(db, p, source="scan")
    db.commit()
    f["raw"].unlink()
    out = ingest_path(db, f["raw"], source="scan")
    db.commit()
    assert out.status == "missing"
    p = _photos(db)[0]
    assert p.has_jpeg and not p.has_raw
    assert f["jpeg"].exists()


def test_live_ingest_waits_for_stable_file(env, db) -> None:
    import pytest

    from app.services.ingest import FileNotReadyError

    f = write_capture(env["photos"], "DSC_9300", T0, raw=False)
    with pytest.raises(FileNotReadyError):
        ingest_path(db, f["jpeg"], source="live")


def test_score_candidate_rules() -> None:
    p = Photo(
        base_filename="DSC_1",
        base_key="dsc_1",
        camera_serial="1",
        camera_model="NIKON Z6_3",
        shutter_count=100,
        capture_time=datetime(2026, 1, 1, tzinfo=UTC),
        extra={},
    )
    p.files = []
    base = dict(
        base_key="dsc_1",
        file_type="raw",
        camera_model="NIKON Z6_3",
        directory_date=None,
        mtime=datetime(2026, 1, 1, tzinfo=UTC),
    )
    ok = PairingInput(
        capture_time=datetime(2026, 1, 1, 0, 0, 0, 500000, tzinfo=UTC), camera_serial="1", shutter_count=100, **base
    )
    assert score_candidate(p, ok, 2.0)[0] > 90
    wrong_count = PairingInput(capture_time=p.capture_time, camera_serial="1", shutter_count=101, **base)
    assert score_candidate(p, wrong_count, 2.0) == (0.0, "shutter_count_mismatch")
    far = PairingInput(
        capture_time=p.capture_time + timedelta(seconds=10), camera_serial="1", shutter_count=None, **base
    )
    assert score_candidate(p, far, 2.0)[0] == 0


@requires_z8
def test_real_z8_pair(env, db, z8_pair) -> None:
    day = env["photos"] / "raw" / "2023" / "06" / "02"
    jday = env["photos"] / "immich-jpeg" / "2023" / "06" / "02"
    day.mkdir(parents=True)
    jday.mkdir(parents=True)
    nef = day / "DSC_2567.NEF"
    jpg = jday / "DSC_2567.JPG"
    shutil.copy2(z8_pair["nef"], nef)
    shutil.copy2(z8_pair["jpeg"], jpg)
    a = ingest_path(db, nef, source="scan")
    db.commit()
    b = ingest_path(db, jpg, source="scan")
    db.commit()
    assert (a.status, b.status) == ("created", "paired")
    assert "shutter_count" in b.pair_reason
    p = _photos(db)[0]
    assert p.camera_model == "NIKON Z 8" and p.shutter_count == 2567
    assert p.extra.get("nef_compression") == "High Efficiency"
