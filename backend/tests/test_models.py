from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.image.renditions import fingerprint
from app.models import Photo, PhotoFile, Rendition
from app.models.enums import FileType


def _photo(**kw) -> Photo:
    return Photo(base_filename="DSC_0001", base_key="dsc_0001", **kw)


def test_oversized_metadata_is_truncated_not_fatal(env, db) -> None:
    p = _photo(flash="x" * 500, lens_model="NIKKOR " * 40, picture_control="p" * 100)
    db.add(p)
    db.commit()
    db.expire_all()
    got = db.scalar(select(Photo))
    assert got is not None
    assert len(got.flash) == 128 and len(got.lens_model) == 128 and len(got.picture_control) == 64

    got.scene = "s" * 300
    db.commit()
    db.expire_all()
    assert len(db.scalar(select(Photo)).scene) == 64


def test_capture_time_round_trips_with_offset(env, db) -> None:
    taken = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone(timedelta(hours=-5)))
    db.add(_photo(capture_time=taken))
    db.commit()
    db.expire_all()
    got = db.scalar(select(Photo)).capture_time
    assert got == taken
    assert got.tzinfo is not None and got.utcoffset() == timedelta(0)


def test_rendition_fingerprint_fits_column(env, db, monkeypatch) -> None:
    monkeypatch.setenv("THUMBNAIL_SIZES", "256,512,1024,2048")
    get_settings.cache_clear()
    p = _photo()
    f = PhotoFile(
        file_type=FileType.RAW,
        absolute_path="/photos/raw/DSC_0001.NEF",
        relative_path="raw/DSC_0001.NEF",
        filename="DSC_0001.NEF",
        extension="nef",
        file_size=1,
        checksum="a" * 64,
        modification_time=datetime.now(UTC),
        exists=True,
    )
    p.files.append(f)
    db.add(p)
    db.flush()
    fp = fingerprint(f)
    limit = Rendition.__table__.c.source_fingerprint.type.length
    assert len(fp) <= limit
    monkeypatch.setenv("THUMBNAIL_SIZES", "256,512")
    get_settings.cache_clear()
    assert fingerprint(f) != fp
