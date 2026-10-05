from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import DB
from app.models import Job
from app.models.enums import JobKind, JobStatus
from app.schemas.system import JobOut, JobPage, StatsOut
from app.services.stats import compute_stats
from app.services.system_status import system_overview
from app.workers.queue import enqueue

router = APIRouter(tags=["system"])


@router.get("/stats", response_model=StatsOut)
def stats(db: DB, recent: Annotated[int, Query(ge=0, le=100)] = 24) -> StatsOut:
    return compute_stats(db, recent)


@router.get("/system")
def system(db: DB) -> dict[str, Any]:
    return system_overview(db)


@router.post("/system/rescan", status_code=status.HTTP_202_ACCEPTED)
def rescan() -> dict[str, Any]:
    """Queue an idempotent reconcile scan of JPEG/RAW/VIDEO roots."""
    job = enqueue(JobKind.SCAN, dedupe_key="reconcile", payload={"source": "scan"})
    return {
        "queued": bool(job),
        "job_id": str(job) if job else None,
        "detail": None if job else "a scan is already running",
    }


@router.post("/system/verify", status_code=status.HTTP_202_ACCEPTED)
def verify() -> dict[str, Any]:
    job = enqueue(JobKind.VERIFY, dedupe_key="verify")
    return {"queued": bool(job), "job_id": str(job) if job else None}


@router.get("/jobs", response_model=JobPage)
def jobs(
    db: DB,
    status_: Annotated[str | None, Query(alias="status")] = None,
    kind: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobPage:
    stmt = select(Job)
    if status_:
        stmt = stmt.where(Job.status == status_)
    if kind:
        stmt = stmt.where(Job.kind == kind)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Job.created_at.desc()).offset(offset).limit(limit)).all()
    counts = dict(db.execute(select(Job.status, func.count(Job.id)).group_by(Job.status)).all())
    return JobPage(items=[JobOut.model_validate(r) for r in rows], total=total, counts=counts)


def _requeue(row: Job) -> uuid.UUID | None:
    payload = dict(row.payload or {})
    if row.kind == JobKind.INGEST_FILE:
        payload["force"] = True
    new_id = enqueue(row.kind, photo_id=row.photo_id, target_path=row.target_path, payload=payload)
    if new_id:
        row.status = JobStatus.RETRIED.value
    return new_id


@router.post("/jobs/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_job(db: DB, job_id: uuid.UUID) -> dict[str, Any]:
    row = db.get(Job, job_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    if row.status != JobStatus.FAILED.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "only failed jobs can be retried")
    new_id = _requeue(row)
    db.commit()
    return {"job_id": str(new_id) if new_id else None}


@router.post("/jobs/retry-failed", status_code=status.HTTP_202_ACCEPTED)
def retry_all_failed(db: DB, limit: Annotated[int, Query(ge=1, le=1000)] = 200) -> dict[str, Any]:
    rows = db.scalars(
        select(Job).where(Job.status == JobStatus.FAILED.value).order_by(Job.created_at.desc()).limit(limit)
    ).all()
    queued = sum(1 for row in rows if _requeue(row))
    db.commit()
    return {"queued": queued}
