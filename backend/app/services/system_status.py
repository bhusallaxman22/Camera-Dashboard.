from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.registry import describe_providers
from app.config import get_settings
from app.database import db_healthy
from app.metadata.exiftool import exiftool_version
from app.models import Job, Photo, Rendition
from app.models.enums import JobKind, JobStatus
from app.schemas.system import ComponentHealth
from app.services.immich import ImmichClient
from app.services.redis_client import redis_healthy


def _disk(path: str) -> dict[str, Any] | None:
    try:
        u = shutil.disk_usage(path)
        return {"path": path, "total": u.total, "used": u.used, "free": u.free}
    except OSError:
        return None


def roots_status() -> list[dict[str, Any]]:
    s = get_settings()
    out = []
    for name, root in s.media_roots.items():
        exists = root.is_dir()
        out.append(
            {
                "name": name,
                "path": str(root),
                "nas_path": s.display_path(str(root)),
                "accessible": exists and os.access(root, os.R_OK | os.X_OK),
                "required": name != "unsorted",
                # Expected False: originals are mounted read-only.
                "writable": exists and os.access(root, os.W_OK),
            }
        )
    return out


def health_components() -> dict[str, ComponentHealth]:
    from app.workers.queue import watcher_status, workers_info

    db_ok, db_err = db_healthy()
    r_ok, r_err = redis_healthy()
    comps = {
        "api": ComponentHealth(ok=True),
        "database": ComponentHealth(ok=db_ok, detail=db_err),
        "redis": ComponentHealth(ok=r_ok, detail=r_err),
    }
    if r_ok:
        try:
            workers = workers_info()
            alive = sum(1 for w in workers if w["alive"])
            comps["worker"] = ComponentHealth(
                ok=alive > 0,
                detail=f"{alive} worker(s) online" if alive else "no live workers (stale or none registered)",
                data={"workers": workers},
            )
        except Exception as exc:
            comps["worker"] = ComponentHealth(ok=False, detail=str(exc))
        try:
            w = watcher_status()
            alive = bool(w and w.get("age_seconds", 999) < 60)
            comps["watcher"] = ComponentHealth(
                ok=alive and bool(w and w.get("observer_alive", w.get("mode") == "disabled")),
                detail=None if alive else "no heartbeat from watcher",
                data=w or {},
            )
        except Exception as exc:
            comps["watcher"] = ComponentHealth(ok=False, detail=str(exc))
    else:
        comps["worker"] = ComponentHealth(ok=False, detail="redis unavailable")
        comps["watcher"] = ComponentHealth(ok=False, detail="redis unavailable")
    roots = roots_status()
    roots_ok = all(r["accessible"] for r in roots if r["required"])
    comps["photo_roots"] = ComponentHealth(
        ok=roots_ok,
        detail=None if roots_ok else "one or more photo roots unavailable",
        data={"roots": roots},
    )
    return comps


def system_overview(session: Session) -> dict[str, Any]:
    from app.workers.queue import queue_stats

    s = get_settings()
    comps = health_components()
    try:
        queues = queue_stats() if comps["redis"].ok else []
    except Exception:
        queues = []
    job_counts = dict(session.execute(select(Job.status, func.count(Job.id)).group_by(Job.status)).all())
    last_ingest = session.scalar(
        select(func.max(Job.finished_at)).where(
            Job.kind == JobKind.INGEST_FILE.value, Job.status == JobStatus.SUCCEEDED.value
        )
    )
    last_photo = session.scalar(select(func.max(Photo.imported_at)))
    cache_bytes, cache_files = session.execute(
        select(func.coalesce(func.sum(Rendition.file_size), 0), func.count(Rendition.id))
    ).one()
    immich = ImmichClient()
    immich_ok, immich_detail = immich.ping() if immich.enabled else (False, "disabled")
    return {
        "time": datetime.now(UTC),
        "version": s.app_version,
        "components": {k: v.model_dump() for k, v in comps.items()},
        "queues": queues,
        "jobs": {
            "pending": job_counts.get("queued", 0) + job_counts.get("running", 0),
            "failed": job_counts.get("failed", 0),
            "succeeded": job_counts.get("succeeded", 0),
            "by_status": job_counts,
        },
        "last_successful_ingest": last_ingest,
        "last_new_photo": last_photo,
        "disk": {
            "photos": _disk(str(s.photo_root)),
            "data": _disk(str(s.data_root)),
        },
        "cache": {"bytes": int(cache_bytes), "files": int(cache_files)},
        "config": {
            "ai_provider": s.ai_provider,
            "ai_auto_analyze": s.ai_auto_analyze,
            "ai_providers": describe_providers(),
            "watch_mode": s.watch_mode,
            "file_stable_seconds": s.file_stable_seconds,
            "pair_window_seconds": s.pair_window_seconds,
            "reconcile_interval_minutes": s.reconcile_interval_minutes,
            "immich_enabled": s.immich_enabled,
            "immich_reachable": immich_ok,
            "immich_detail": immich_detail,
            "auth_enabled": bool(s.api_token),
            "nas_photo_root": s.nas_photo_root,
        },
        "versions": {"app": s.app_version, "exiftool": exiftool_version()},
    }
