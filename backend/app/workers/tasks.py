"""RQ job functions. Each receives the DB Job id first for status tracking."""

from __future__ import annotations

import functools
import time
import traceback
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from rq import get_current_job

from app.database import session_scope
from app.log import configure_logging, get_logger
from app.models import Job
from app.models.enums import JobKind, JobStatus
from app.observability import metrics
from app.services import pipeline
from app.services.events import publish, record_event
from app.services.scanner import mark_missing, plan_scan, verify_files
from app.workers.queue import enqueue_safe

log = get_logger(__name__)


def _update_job(job_id: str, **fields: Any) -> None:
    try:
        with session_scope() as s:
            row = s.get(Job, uuid.UUID(job_id))
            if row is None:
                return
            for k, v in fields.items():
                if k == "attempts_inc":
                    row.attempts += 1
                else:
                    setattr(row, k, v)
    except Exception as exc:
        log.warning("job_tracking_failed", job_id=job_id, error=str(exc))


def tracked(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Persist job lifecycle (running/succeeded/failed + error) in the jobs table."""

    @functools.wraps(fn)
    def wrapper(job_id: str, **kwargs: Any) -> dict[str, Any]:
        configure_logging()
        started = time.perf_counter()
        _update_job(job_id, status=JobStatus.RUNNING.value, started_at=datetime.now(UTC), attempts_inc=True)
        try:
            result = fn(**kwargs) or {}
        except Exception as exc:
            rq_job = get_current_job()
            retrying = bool(rq_job and rq_job.retries_left)
            err = f"{type(exc).__name__}: {exc}"
            _update_job(
                job_id,
                status=JobStatus.QUEUED.value if retrying else JobStatus.FAILED.value,
                error=err + ("" if retrying else "\n" + traceback.format_exc(limit=8)),
                finished_at=datetime.now(UTC),
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            log.error(
                "job_failed",
                category="ERROR",
                job=fn.__name__,
                job_id=job_id,
                error=err,
                retrying=retrying,
            )
            if not retrying:
                if fn.__name__ == "ingest_file_task":
                    metrics.inc("ingest_failures")
                try:
                    with session_scope() as s:
                        record_event(
                            s,
                            "ERROR",
                            "job_failed",
                            f"{fn.__name__} failed: {err}",
                            level="error",
                            data={"job_id": job_id, **kwargs},
                        )
                except Exception:
                    pass
            publish("job.updated", {"job_id": job_id, "status": "failed"})
            raise
        _update_job(
            job_id,
            status=JobStatus.SUCCEEDED.value,
            result=result,
            error=None,
            finished_at=datetime.now(UTC),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        return result

    return wrapper


def _chain_after_render(photo_id: str, render: pipeline.StepResult) -> None:
    if render.needs_analysis:
        enqueue_safe(JobKind.ANALYZE, dedupe_key=photo_id, photo_id=photo_id, payload={"photo_id": photo_id})


@tracked
def ingest_file_task(path: str, source: str = "live", force: bool = False) -> dict[str, Any]:
    outcome = pipeline.ingest_step(path, source=source, force=force)
    result: dict[str, Any] = {
        "status": outcome.status,
        "photo_id": str(outcome.photo_id) if outcome.photo_id else None,
        "pair_reason": outcome.pair_reason,
        "warnings": outcome.warnings,
        "duration_ms": outcome.duration_ms,
    }
    if outcome.photo_id and outcome.status not in ("skipped", "missing"):
        pid = str(outcome.photo_id)
        render = pipeline.render_step(pid)
        result["render"] = render.status
        _chain_after_render(pid, render)
    return result


@tracked
def render_task(photo_id: str, force: bool = False) -> dict[str, Any]:
    render = pipeline.render_step(photo_id, force=force)
    if force and render.status == "rendered":
        render.needs_analysis = True
    _chain_after_render(photo_id, render)
    return {"status": render.status, **render.details}


@tracked
def analyze_task(photo_id: str, with_ai: bool | None = None) -> dict[str, Any]:
    res = pipeline.analyze_step(photo_id, with_ai=with_ai)
    if res.needs_analysis:
        enqueue_safe(JobKind.AI_CRITIQUE, dedupe_key=photo_id, photo_id=photo_id, payload={"photo_id": photo_id})
    return {"status": res.status, **res.details}


@tracked
def ai_critique_task(photo_id: str, provider: str | None = None) -> dict[str, Any]:
    res = pipeline.ai_step(photo_id, provider)
    return {"status": res.status, **res.details}


@tracked
def scan_task(source: str = "scan") -> dict[str, Any]:
    with session_scope() as s:
        plan = plan_scan(s)
        missing = mark_missing(s, plan.missing)
        if plan.to_ingest or missing:
            record_event(
                s,
                "INGEST",
                "scan_completed",
                f"Scan found {len(plan.to_ingest)} new/changed files, {missing} missing",
                data={"seen": plan.total_seen, "unchanged": plan.unchanged},
            )
    queued = 0
    for path in plan.to_ingest:
        if enqueue_safe(
            JobKind.INGEST_FILE,
            dedupe_key=str(path),
            target_path=str(path),
            payload={"path": str(path), "source": source},
        ):
            queued += 1
    return {
        "seen": plan.total_seen,
        "queued": queued,
        "unchanged": plan.unchanged,
        "missing": missing,
        "skipped_recent": plan.skipped_recent,
        "roots_unavailable": plan.roots_unavailable,
    }


@tracked
def verify_task() -> dict[str, Any]:
    with session_scope() as s:
        return verify_files(s)
