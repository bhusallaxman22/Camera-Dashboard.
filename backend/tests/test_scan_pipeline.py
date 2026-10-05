from __future__ import annotations

import os
import shutil
import time
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.metadata.exiftool import read_metadata
from app.metadata.parser import parse_metadata
from app.models import BurstGroup, Photo, PhotoFile, Rendition, TechnicalAnalysis
from app.services.photos import to_summary
from app.services.pipeline import process_file_inline
from app.services.scanner import plan_scan
from app.utils.samples import generate_library
from app.utils.timeutil import ensure_aware
from app.watchers.stability import StabilityTracker
from tests.conftest import age_files, requires_exiftool, requires_z8, run_jobs, write_capture

pytestmark = requires_exiftool


def _scan_inline(db) -> None:
    from app.config import get_settings

    age_files(get_settings().photo_root)
    plan = plan_scan(db)
    for p in plan.to_ingest:
        process_file_inline(p)


def test_initial_scan_pairs_renders_analyzes(env, db) -> None:
    generate_library(env["photos"], count=8, start=datetime(2026, 9, 30, 10, 0, 0))
    _scan_inline(db)
    db.expire_all()
    assert db.scalar(select(func.count(Photo.id))) == 8
    assert db.scalar(select(func.count(PhotoFile.id))) == 16
    assert all(p.has_jpeg and p.has_raw for p in db.scalars(select(Photo)))
    assert db.scalar(select(func.count(TechnicalAnalysis.id))) == 8
    # preview + 256 + 512 for every photo, all under DATA_ROOT
    renditions = db.scalars(select(Rendition)).all()
    assert len(renditions) == 8 * 3
    for r in renditions:
        assert (env["data"] / r.path).is_file()
    # samples include 200ms bursts at positions 1-2 of every 4
    groups = db.scalars(select(BurstGroup)).all()
    assert groups and all(g.photo_count >= 2 for g in groups)
    members = db.scalars(select(Photo).where(Photo.burst_group_id.is_not(None))).all()
    summaries = [to_summary(p) for p in members]
    assert all(s.burst_size == p.burst_group.photo_count for s, p in zip(summaries, members, strict=True))


def test_rescan_creates_no_duplicates(env, db) -> None:
    generate_library(env["photos"], count=5, start=datetime(2026, 9, 30, 10, 0, 0))
    _scan_inline(db)
    plan = plan_scan(db)
    assert plan.to_ingest == []
    assert plan.unchanged == 10
    _scan_inline(db)
    assert db.scalar(select(func.count(Photo.id))) == 5


def test_scan_skips_files_still_being_written(env, db) -> None:
    f = write_capture(env["photos"], "DSC_0100", datetime(2026, 9, 30, 9, 0))
    age_files(env["photos"])
    now = time.time()
    os.utime(f["jpeg"], (now, now))
    plan = plan_scan(db, now=now + 0.1)
    assert plan.skipped_recent == 1


def test_scan_marks_missing_only_for_available_roots(env, db) -> None:
    generate_library(env["photos"], count=2, start=datetime(2026, 9, 30, 10, 0, 0))
    _scan_inline(db)
    shutil.rmtree(env["photos"] / "raw")  # simulate an unmounted share
    plan = plan_scan(db)
    assert plan.roots_unavailable and plan.missing == []


def test_renders_are_cached_not_regenerated(env, db) -> None:
    from app.services.pipeline import render_step

    f = write_capture(env["photos"], "DSC_0200", datetime(2026, 9, 30, 9, 0))
    out = process_file_inline(f["jpeg"])
    again = render_step(out.photo_id)
    assert again.status == "current"


def test_queue_pipeline_end_to_end(env, db) -> None:
    """watcher-style enqueue -> worker -> DB, through RQ (fakeredis)."""
    from app.models.enums import JobKind
    from app.workers.queue import enqueue

    f = write_capture(env["photos"], "DSC_0300", datetime(2026, 9, 30, 9, 0))
    old = time.time() - 60
    for p in f.values():
        os.utime(p, (old, old))
        enqueue(JobKind.INGEST_FILE, dedupe_key=str(p), target_path=str(p), payload={"path": str(p)})
    run_jobs()
    db.expire_all()
    photos = db.scalars(select(Photo)).all()
    assert len(photos) == 1
    p = photos[0]
    assert p.processing_status == "ready"
    assert p.analysis is not None and p.analysis.sharpness_score is not None
    assert p.critiques and p.critiques[0].provider == "local"


def test_sorter_renamed_copies_pair_and_dedupe(env, db) -> None:
    """The sorter appends `_HHMMSS` on name clashes; that must not split captures."""
    when = datetime(2026, 10, 1, 2, 19, 44)
    f = write_capture(env["photos"], "DSC_0111", when)
    renamed = f["jpeg"].with_name("DSC_0111_072752.JPG")
    f["jpeg"].rename(renamed)
    reupload = renamed.with_name("DSC_0111.JPG")
    shutil.copy2(renamed, reupload)
    for p in (renamed, f["raw"], reupload):
        process_file_inline(p)
    db.expire_all()
    photos = db.scalars(select(Photo)).all()
    assert len(photos) == 1
    assert photos[0].base_filename == "DSC_0111" and photos[0].has_jpeg and photos[0].has_raw
    files = db.scalars(select(PhotoFile)).all()
    assert len(files) == 3 and sum(f.duplicate_of_id is not None for f in files) == 1


def _primary_and_copies(photo: Photo) -> tuple[PhotoFile, list[PhotoFile]]:
    primary = [f for f in photo.files if f.duplicate_of_id is None]
    assert len(primary) == 1
    return primary[0], [f for f in photo.files if f.duplicate_of_id is not None]


def test_truncated_upload_is_superseded_by_complete_reupload(env, db) -> None:
    """Camera FTP retry: a cut-off DSC_0116.JPG, then the full file renamed by the sorter."""
    f = write_capture(env["photos"], "DSC_0116", datetime(2026, 10, 1, 11, 14, 26), raw=False)
    complete = f["jpeg"].read_bytes()
    f["jpeg"].write_bytes(complete[: len(complete) // 2])
    first = process_file_inline(f["jpeg"])
    db.expire_all()
    assert db.get(Photo, first.photo_id).processing_status == "error"

    reupload = f["jpeg"].with_name("DSC_0116_161540.JPG")
    reupload.write_bytes(complete)
    out = process_file_inline(reupload)
    assert out.status == "reupload" and out.photo_id == first.photo_id

    db.expire_all()
    photos = db.scalars(select(Photo)).all()
    assert len(photos) == 1
    photo = photos[0]
    assert photo.processing_status == "ready" and photo.processing_error is None
    primary, copies = _primary_and_copies(photo)
    assert primary.filename == "DSC_0116_161540.JPG"
    assert [c.filename for c in copies] == ["DSC_0116.JPG"]
    assert all(r.source_file_id == primary.id for r in photo.renditions)


def test_truncated_retry_after_complete_upload_is_attached(env, db) -> None:
    f = write_capture(env["photos"], "DSC_0117", datetime(2026, 10, 1, 11, 14, 29), raw=False)
    first = process_file_inline(f["jpeg"])
    data = f["jpeg"].read_bytes()
    retry = f["jpeg"].with_name("DSC_0117-1.JPG")
    retry.write_bytes(data[: len(data) // 3])
    out = process_file_inline(retry)
    assert out.status == "reupload" and out.photo_id == first.photo_id

    db.expire_all()
    photo = db.scalars(select(Photo)).one()
    assert photo.processing_status == "ready"
    primary, copies = _primary_and_copies(photo)
    assert primary.filename == "DSC_0117.JPG" and [c.filename for c in copies] == ["DSC_0117-1.JPG"]


def test_headerless_fragment_merges_with_later_complete_upload(env, db) -> None:
    f = write_capture(env["photos"], "DSC_0119", datetime(2026, 10, 1, 11, 15, 36), raw=False)
    complete = f["jpeg"].read_bytes()
    fragment = f["jpeg"].with_name("DSC_0119-1.JPG")
    fragment.write_bytes(b"\xff\xd8" + b"\x00" * 2000)
    f["jpeg"].unlink()
    frag_out = process_file_inline(fragment)

    full = fragment.with_name("DSC_0119-2.JPG")
    full.write_bytes(complete)
    out = process_file_inline(full)
    assert out.status == "reupload" and out.photo_id == frag_out.photo_id

    db.expire_all()
    photo = db.scalars(select(Photo)).one()
    assert photo.processing_status == "ready"
    assert photo.base_filename == "DSC_0119" and photo.camera_serial == "7000123"
    exif_time = parse_metadata(read_metadata(full)).capture_time
    assert exif_time is not None and ensure_aware(photo.capture_time) == exif_time
    primary, _ = _primary_and_copies(photo)
    assert primary.filename == "DSC_0119-2.JPG"


def test_heif_in_unsorted_is_ingested_and_reuploads_merge(env, db) -> None:
    """The sorter files `.HIF` under unsorted/; truncated retries must still collapse."""
    import io

    import pytest
    from PIL import Image

    f = write_capture(env["photos"], "DSC_0132", datetime(2026, 10, 1, 11, 29, 12), raw=False)
    jpeg = Image.open(io.BytesIO(f["jpeg"].read_bytes()))
    f["jpeg"].unlink()
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
        buf = io.BytesIO()
        jpeg.save(buf, "HEIF", exif=jpeg.info["exif"], quality=80)
    except Exception as exc:
        pytest.skip(f"HEIF encoder unavailable: {exc}")
    heif = buf.getvalue()

    day = env["photos"] / "unsorted" / "2026" / "10" / "01"
    day.mkdir(parents=True)
    (day / "DSC_0132.HIF").write_bytes(heif[: len(heif) // 2])
    (day / "DSC_0132_164644.HIF").write_bytes(heif)
    _scan_inline(db)

    db.expire_all()
    photo = db.scalars(select(Photo)).one()
    assert photo.processing_status == "ready" and photo.has_jpeg
    primary, copies = _primary_and_copies(photo)
    assert primary.filename == "DSC_0132_164644.HIF" and primary.file_type == "image"
    assert [c.filename for c in copies] == ["DSC_0132.HIF"]


def test_corrupt_jpeg_does_not_crash_pipeline(env, db) -> None:
    bad = env["photos"] / "immich-jpeg" / "2026" / "09" / "30" / "DSC_0666.JPG"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"\xff\xd8\xff\xe0garbage" * 100)
    out = process_file_inline(bad)
    db.expire_all()
    p = db.get(Photo, out.photo_id)
    assert p.processing_status == "error" and p.processing_error


@requires_z8
def test_raw_only_uses_embedded_preview(env, db) -> None:
    from tests.conftest import Z8_NEF

    dest = env["photos"] / "raw" / "2023" / "06" / "02" / "DSC_2567.NEF"
    dest.parent.mkdir(parents=True)
    shutil.copy2(Z8_NEF, dest)
    out = process_file_inline(dest)
    db.expire_all()
    p = db.get(Photo, out.photo_id)
    assert p.processing_status == "ready"
    preview = next(r for r in p.renditions if r.kind == "preview")
    assert max(preview.width, preview.height) == 2560


def test_stability_tracker_debounces() -> None:
    import tempfile
    from pathlib import Path

    clock = [0.0]
    tracker = StabilityTracker(2.0, clock=lambda: clock[0])
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "DSC_1.JPG"
        p.write_bytes(b"a" * 10)
        tracker.touch(str(p))
        assert tracker.poll() == ([], [])  # first observation
        clock[0] = 1.0
        p.write_bytes(b"a" * 20)  # still growing
        assert tracker.poll() == ([], [])
        clock[0] = 2.5
        assert tracker.poll() == ([], [])  # unchanged for only 1.5s
        clock[0] = 3.6
        assert tracker.poll() == ([str(p)], [])
        assert len(tracker) == 0


def test_burst_grouping_respects_focal_length(env, db) -> None:
    t = datetime(2026, 9, 30, 12, 0, 0)
    for i in range(3):
        f = write_capture(env["photos"], f"DSC_40{i}", t + timedelta(milliseconds=150 * i), raw=False, seed=i)
        process_file_inline(f["jpeg"])
    f = write_capture(env["photos"], "DSC_409", t + timedelta(milliseconds=600), raw=False, focal=200)
    process_file_inline(f["jpeg"])
    db.expire_all()
    groups = db.scalars(select(BurstGroup)).all()
    assert len(groups) == 1 and groups[0].photo_count == 3
    loner = db.scalars(select(Photo).where(Photo.base_filename == "DSC_409")).one()
    assert loner.burst_group_id is None
