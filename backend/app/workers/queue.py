"""RQ queues + persistent Job records.

Queues (highest priority first): `ingest` (new files, renders), `analysis`
(technical metrics + local critique), `ai` (remote/slow AI providers).
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.exceptions import RedisError
from rq import Queue, Retry, Worker
from rq.exceptions import NoSuchJobError
from rq.job import Job as RQJob
from rq.job import JobStatus as RQJobStatus
from sqlalchemy import select

from app.config import get_settings
from app.database import session_scope
from app.log import get_logger
from app.models import Job
from app.models.enums import JobKind, JobStatus
from app.services.redis_client import get_redis
from app.utils.hashing import short_hash

log = get_logger(__name__)

QUEUE_INGEST = "ingest"
QUEUE_ANALYSIS = "analysis"
QUEUE_AI = "ai"
ALL_QUEUES = (QUEUE_INGEST, QUEUE_ANALYSIS, QUEUE_AI)

WATCHER_HEARTBEAT_KEY = "z6iii:watcher:heartbeat"
WATCHER_TTL = 60
# Idle RQ workers heartbeat every (ttl - 15)s; a crashed worker's registration
# lingers for ttl + 60s, so liveness is judged by heartbeat age instead.
WORKER_TTL = 90
WORKER_STALE_SECONDS = WORKER_TTL + 30

TASKS: dict[str, tuple[str, str]] = {
    JobKind.INGEST_FILE: ("app.workers.tasks.ingest_file_task", QUEUE_INGEST),
    JobKind.RENDER: ("app.workers.tasks.render_task", QUEUE_INGEST),
    JobKind.ANALYZE: ("app.workers.tasks.analyze_task", QUEUE_ANALYSIS),
    JobKind.AI_CRITIQUE: ("app.workers.tasks.ai_critique_task", QUEUE_AI),
    JobKind.SCAN: ("app.workers.tasks.scan_task", QUEUE_INGEST),
    JobKind.VERIFY: ("app.workers.tasks.verify_task", QUEUE_INGEST),
}

_ACTIVE = {RQJobStatus.QUEUED, RQJobStatus.STARTED, RQJobStatus.SCHEDULED, RQJobStatus.DEFERRED}


def get_queue(name: str) -> Queue:
    return Queue(name, connection=get_redis(), default_timeout=get_settings().job_timeout_seconds)


LOST_ERROR = "lost: job is no longer in the queue (worker or Redis restarted); retry to run it again"


def _is_active(rq_id: str) -> bool:
    conn = get_redis()
    try:
        job = RQJob.fetch(rq_id, connection=conn)
    except NoSuchJobError:
        return False
    status = job.get_status()
    if status == RQJobStatus.QUEUED:
        # A worker killed between popping a job and starting it leaves the job
        # "queued" but in no list; trusting the status would make dedupe skip
        # that key forever.
        q = get_queue(job.origin)
        return q.get_job_position(rq_id) is not None or conn.lpos(q.intermediate_queue_key, rq_id) is not None
    return status in _ACTIVE


def enqueue(
    kind: str,
    *,
    dedupe_key: str | None = None,
    photo_id: uuid.UUID | str | None = None,
    target_path: str | None = None,
    payload: dict[str, Any] | None = None,
    retries: int | None = None,
) -> uuid.UUID | None:
    """Create a Job row and push it to RQ. Returns None if an identical job is active.

    Raises RedisError if Redis is unreachable (callers decide whether to retry).
    """
    func, queue_name = TASKS[kind]
    payload = payload or {}
    # RQ ids allow only [A-Za-z0-9_-]; paths are hashed into a stable key.
    rq_id = f"{kind}-{short_hash(dedupe_key, 32)}" if dedupe_key else None
    if rq_id and _is_active(rq_id):
        return None

    job_id = uuid.uuid4()
    rq_id = rq_id or str(job_id)
    with session_scope() as s:
        if dedupe_key:
            # Rows still marked active under this RQ id were lost (checked above).
            for stale in s.scalars(
                select(Job).where(
                    Job.rq_job_id == rq_id,
                    Job.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
                )
            ):
                stale.status, stale.error, stale.finished_at = JobStatus.FAILED.value, LOST_ERROR, datetime.now(UTC)
        s.add(
            Job(
                id=job_id,
                kind=kind,
                status=JobStatus.QUEUED.value,
                queue=queue_name,
                rq_job_id=rq_id,
                photo_id=uuid.UUID(str(photo_id)) if photo_id else None,
                target_path=target_path,
                payload=json.loads(json.dumps(payload, default=str)),
            )
        )

    max_retries = get_settings().job_max_retries if retries is None else retries
    try:
        get_queue(queue_name).enqueue(
            func,
            args=(str(job_id),),
            kwargs=payload,
            job_id=rq_id,
            retry=Retry(max=max_retries, interval=[5, 30, 120]) if max_retries else None,
            result_ttl=3600,
            failure_ttl=7 * 24 * 3600,
            meta={"db_job_id": str(job_id)},
        )
    except RedisError:
        with session_scope() as s:
            row = s.get(Job, job_id)
            if row is not None:
                row.status, row.error = JobStatus.FAILED.value, "could not enqueue: Redis unavailable"
        raise
    return job_id


ORPHAN_GRACE_SECONDS = 300


def reap_orphaned_jobs(grace_seconds: int = ORPHAN_GRACE_SECONDS) -> int:
    """Fail Job rows whose RQ job no longer exists (e.g. Redis data lost, worker
    SIGKILLed mid-run) so they surface in the UI and can be retried.

    Returns the number of rows marked failed.
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=grace_seconds)
    reaped = 0
    with session_scope() as s:
        rows = s.scalars(
            select(Job).where(
                Job.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]),
                Job.created_at < cutoff,
            )
        ).all()
        for row in rows:
            if row.rq_job_id and _is_active(row.rq_job_id):
                continue
            # A finished RQ job whose row was never updated means the worker
            # died between running the task and recording the outcome.
            row.status = JobStatus.FAILED.value
            row.error = LOST_ERROR
            row.finished_at = datetime.now(UTC)
            reaped += 1
    if reaped:
        log.warning("orphaned_jobs_reaped", category="ERROR", count=reaped)
    return reaped


def enqueue_safe(kind: str, **kwargs: Any) -> uuid.UUID | None:
    """enqueue() that logs instead of raising when Redis is down."""
    try:
        return enqueue(kind, **kwargs)
    except RedisError as exc:
        log.error("enqueue_failed", category="ERROR", kind=kind, error=str(exc))
        return None


def queue_stats() -> list[dict[str, Any]]:
    out = []
    for name in ALL_QUEUES:
        q = get_queue(name)
        out.append(
            {
                "name": name,
                "queued": q.count,
                "started": q.started_job_registry.count,
                "scheduled": q.scheduled_job_registry.count,
                "failed": q.failed_job_registry.count,
            }
        )
    return out


def _heartbeat_age(w: Worker) -> float | None:
    hb = w.last_heartbeat
    if hb is None:
        return None
    hb = hb if hb.tzinfo else hb.replace(tzinfo=UTC)
    return (datetime.now(UTC) - hb).total_seconds()


def worker_is_alive(w: Worker) -> bool:
    age = _heartbeat_age(w)
    return age is not None and age < WORKER_STALE_SECONDS


def workers_info() -> list[dict[str, Any]]:
    out = []
    for w in Worker.all(connection=get_redis()):
        hb = w.last_heartbeat
        age = _heartbeat_age(w)
        out.append(
            {
                "name": w.name,
                "state": w.get_state(),
                "queues": w.queue_names(),
                "alive": worker_is_alive(w),
                "heartbeat_age_seconds": round(age, 1) if age is not None else None,
                "last_heartbeat": (hb if hb.tzinfo else hb.replace(tzinfo=UTC)).isoformat() if hb else None,
                "successful_jobs": w.successful_job_count,
                "failed_jobs": w.failed_job_count,
            }
        )
    return out


def worker_count() -> int:
    return sum(1 for w in Worker.all(connection=get_redis()) if worker_is_alive(w))


def set_watcher_heartbeat(info: dict[str, Any]) -> None:
    info = {**info, "ts": time.time()}
    get_redis().set(WATCHER_HEARTBEAT_KEY, json.dumps(info), ex=WATCHER_TTL)


def watcher_status() -> dict[str, Any] | None:
    raw = get_redis().get(WATCHER_HEARTBEAT_KEY)
    if not raw:
        return None
    data = json.loads(raw)
    data["age_seconds"] = round(time.time() - data.get("ts", 0), 1)
    data["last_seen"] = datetime.fromtimestamp(data.get("ts", 0), UTC).isoformat()
    return data


def watcher_alive() -> bool:
    st = watcher_status()
    return bool(st and st["age_seconds"] < WATCHER_TTL)
