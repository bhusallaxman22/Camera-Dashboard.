"""Test fixtures.

By default tests use a throwaway SQLite DB and fakeredis. Set
TEST_DATABASE_URL=postgresql+psycopg://... to run the same suite against a real
Postgres (schema is created through the Alembic migrations).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import fakeredis
import pytest
import redis

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / ".tools"
LOCAL_EXIFTOOL = TOOLS / "exiftool" / "exiftool"
EXIFTOOL = str(LOCAL_EXIFTOOL) if LOCAL_EXIFTOOL.exists() else (shutil.which("exiftool") or "exiftool")
FACE_MODEL = TOOLS / "models" / "face_detection_yunet_2023mar.onnx"
if not FACE_MODEL.exists():
    FACE_MODEL = Path("/opt/models/face_detection_yunet_2023mar.onnx")
Z8_NEF = TOOLS / "samples" / "Z8_HE.NEF"

HAS_EXIFTOOL = LOCAL_EXIFTOOL.exists() or shutil.which("exiftool") is not None
requires_exiftool = pytest.mark.skipif(not HAS_EXIFTOOL, reason="exiftool not installed")
requires_z8 = pytest.mark.skipif(not (HAS_EXIFTOOL and Z8_NEF.exists()), reason="Z8 NEF sample not present")

os.environ.setdefault("TZ", "America/Chicago")


def _clear_caches() -> None:
    from app.config import get_settings
    from app.database import get_engine, get_sessionmaker
    from app.services.redis_client import get_redis
    from app.utils.timeutil import local_tz

    for fn in (get_settings, get_sessionmaker, get_redis, local_tz):
        fn.cache_clear()
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()


@pytest.fixture(scope="session")
def pg_url() -> str | None:
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        backend = Path(__file__).resolve().parents[1]
        env = {**os.environ, "DATABASE_URL": url}
        subprocess.run(["alembic", "downgrade", "base"], cwd=backend, env=env, check=True, capture_output=True)
        subprocess.run(["alembic", "upgrade", "head"], cwd=backend, env=env, check=True, capture_output=True)
    return url


@pytest.fixture
def fake_redis_server() -> fakeredis.FakeServer:
    return fakeredis.FakeServer()


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pg_url: str | None, fake_redis_server) -> Iterator[dict]:
    photos = tmp_path / "photos"
    data = tmp_path / "data"
    for d in ("immich-jpeg", "raw", "video", "unsorted", "ftp-incoming"):
        (photos / d).mkdir(parents=True)
    data.mkdir()

    db_url = pg_url or f"sqlite:///{tmp_path / 'test.db'}"
    values = {
        "DATABASE_URL": db_url,
        "REDIS_URL": "redis://fake:6379/0",
        "PHOTO_ROOT": str(photos),
        "JPEG_ROOT": str(photos / "immich-jpeg"),
        "RAW_ROOT": str(photos / "raw"),
        "VIDEO_ROOT": str(photos / "video"),
        "UNSORTED_ROOT": str(photos / "unsorted"),
        "DATA_ROOT": str(data),
        "THUMBNAIL_ROOT": str(data / "thumbnails"),
        "PREVIEW_ROOT": str(data / "previews"),
        "CACHE_ROOT": str(data / "cache"),
        "NAS_PHOTO_ROOT": "/mnt/mainpool/photos/z6iii",
        "SMB_PHOTO_ROOT": r"\\nas\photos\z6iii",
        "EXIFTOOL_PATH": EXIFTOOL,
        "FACE_MODEL_PATH": str(FACE_MODEL),
        "FILE_STABLE_SECONDS": "0.5",
        "AI_PROVIDER": "local",
        "AI_AUTO_ANALYZE": "true",
        "API_TOKEN": "",
        "LOG_FORMAT": "console",
        "LOG_LEVEL": "WARNING",
        "THUMBNAIL_SIZES": "256,512",
    }
    for k, v in values.items():
        monkeypatch.setenv(k, v)

    def _fake_from_url(cls, url, **kwargs):
        return fakeredis.FakeRedis(server=fake_redis_server)

    monkeypatch.setattr(redis.Redis, "from_url", classmethod(_fake_from_url))
    from app.services import redis_client

    monkeypatch.setattr(redis_client, "get_async_redis", lambda: fakeredis.FakeAsyncRedis(server=fake_redis_server))
    _clear_caches()

    from app.database import get_engine
    from app.models import Base

    engine = get_engine()
    if pg_url:
        with engine.begin() as conn:
            tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
            conn.exec_driver_sql(f"TRUNCATE {tables} RESTART IDENTITY CASCADE")
    else:
        Base.metadata.create_all(engine)

    yield {"photos": photos, "data": data, "tmp": tmp_path}
    _clear_caches()


@pytest.fixture
def db(env) -> Iterator:
    from app.database import get_sessionmaker

    s = get_sessionmaker()()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client(env):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


def age_files(root: Path, seconds: float = 120) -> None:
    """Backdate mtimes so files count as fully written (stability check)."""
    t = time.time() - seconds
    for p in root.rglob("*"):
        if p.is_file():
            os.utime(p, (t, t))


def run_jobs() -> None:
    """Drain all RQ queues synchronously (in-process)."""
    from rq import SimpleWorker

    from app.services.redis_client import get_redis
    from app.workers.queue import ALL_QUEUES

    SimpleWorker(list(ALL_QUEUES), connection=get_redis()).work(burst=True)


def write_capture(
    photos: Path,
    name: str,
    when: datetime,
    *,
    jpeg: bool = True,
    raw: bool = True,
    serial: str = "7000123",
    seed: int = 1,
    size: tuple[int, int] = (900, 600),
    focal: float = 50.0,
    blur: float = 0.0,
) -> dict[str, Path]:
    from app.utils.samples import fake_nef_bytes, jpeg_bytes, synthetic_image

    day = when.strftime("%Y/%m/%d")
    data = jpeg_bytes(synthetic_image(*size, seed=seed, blur=blur), when, serial=serial, focal=focal)
    out: dict[str, Path] = {}
    if jpeg:
        p = photos / "immich-jpeg" / day / f"{name}.JPG"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        out["jpeg"] = p
    if raw:
        p = photos / "raw" / day / f"{name}.NEF"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(fake_nef_bytes(data))
        out["raw"] = p
    return out


@pytest.fixture(scope="session")
def z8_pair(tmp_path_factory) -> dict[str, Path] | None:
    """Real Z8 NEF + a camera-style JPEG (embedded preview with the NEF's EXIF)."""
    if not (HAS_EXIFTOOL and Z8_NEF.exists()):
        return None
    d = tmp_path_factory.mktemp("z8")
    jpg = d / "Z8_HE.JPG"
    with jpg.open("wb") as fh:
        subprocess.run([EXIFTOOL, "-b", "-JpgFromRaw", str(Z8_NEF)], stdout=fh, check=True)
    subprocess.run(
        [EXIFTOOL, "-q", "-overwrite_original", "-tagsFromFile", str(Z8_NEF), "-all:all", str(jpg)],
        check=True,
    )
    return {"nef": Z8_NEF, "jpeg": jpg}
