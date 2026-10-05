"""Prometheus metrics shared across containers.

The API, worker and watcher are separate processes/containers, so worker-side
counters and histograms are accumulated in Redis and exposed by the API's
/metrics endpoint through a custom collector. Library gauges are computed from
Postgres at scrape time.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from prometheus_client.core import (
    CounterMetricFamily,
    GaugeMetricFamily,
    HistogramMetricFamily,
)
from prometheus_client.registry import Collector

from app.log import get_logger

log = get_logger(__name__)

PREFIX = "z6iii"
_COUNTERS_KEY = "z6iii:metrics:counters"
_HIST_KEY = "z6iii:metrics:hist:{name}"
BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0)

COUNTERS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ingest_jobs": ("Ingest jobs processed", ("status",)),
    "ingest_failures": ("Ingest jobs that failed", ()),
    "analysis_runs": ("Technical analyses completed", ()),
    "ai_runs": ("AI critiques attempted", ("provider", "status")),
}
HISTOGRAMS: dict[str, str] = {
    "analysis_seconds": "Technical analysis duration",
    "thumbnail_generation_seconds": "Preview + thumbnail generation duration",
    "ingest_seconds": "Ingest (metadata + pairing) duration",
    "ai_seconds": "AI provider duration",
}


def _redis():
    from app.services.redis_client import get_redis

    return get_redis()


def _label_key(name: str, labels: dict[str, str]) -> str:
    if not labels:
        return name
    return name + "|" + ",".join(f"{k}={labels[k]}" for k in sorted(labels))


def inc(name: str, amount: float = 1.0, **labels: str) -> None:
    try:
        _redis().hincrbyfloat(_COUNTERS_KEY, _label_key(name, labels), amount)
    except Exception as exc:
        log.debug("metric_inc_failed", name=name, error=str(exc))


def observe(name: str, seconds: float) -> None:
    try:
        key = _HIST_KEY.format(name=name)
        pipe = _redis().pipeline(transaction=False)
        for b in BUCKETS:
            if seconds <= b:
                pipe.hincrby(key, f"{b}", 1)
        pipe.hincrby(key, "+Inf", 1)
        pipe.hincrbyfloat(key, "sum", seconds)
        pipe.execute()
    except Exception as exc:
        log.debug("metric_observe_failed", name=name, error=str(exc))


class _Timer:
    def __init__(self, name: str) -> None:
        self.name = name

    @contextmanager
    def time(self) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            observe(self.name, time.perf_counter() - start)


THUMBNAIL_SECONDS = _Timer("thumbnail_generation_seconds")
ANALYSIS_SECONDS = _Timer("analysis_seconds")
INGEST_SECONDS = _Timer("ingest_seconds")
AI_SECONDS = _Timer("ai_seconds")


class AppCollector(Collector):
    def collect(self) -> Iterator[Any]:
        yield from self._redis_metrics()
        yield from self._db_metrics()
        yield from self._queue_metrics()

    def _redis_metrics(self) -> Iterator[Any]:
        try:
            r = _redis()
            raw = {k.decode(): float(v) for k, v in r.hgetall(_COUNTERS_KEY).items()}
            hists = {n: r.hgetall(_HIST_KEY.format(name=n)) for n in HISTOGRAMS}
        except Exception:
            return
        for name, (doc, label_names) in COUNTERS.items():
            fam = CounterMetricFamily(f"{PREFIX}_{name}", doc, labels=list(label_names))
            seen = False
            for key, val in raw.items():
                base, _, lbl = key.partition("|")
                if base != name:
                    continue
                labels = dict(p.split("=", 1) for p in lbl.split(",")) if lbl else {}
                fam.add_metric([labels.get(n, "") for n in label_names], val)
                seen = True
            if not seen and not label_names:
                fam.add_metric([], 0.0)
            yield fam
        for name, doc in HISTOGRAMS.items():
            data = {k.decode(): float(v) for k, v in hists[name].items()}
            buckets = [(str(b), data.get(f"{b}", 0.0)) for b in BUCKETS]
            buckets.append(("+Inf", data.get("+Inf", 0.0)))
            fam = HistogramMetricFamily(f"{PREFIX}_{name}", doc)
            fam.add_metric([], buckets, sum_value=data.get("sum", 0.0))
            yield fam

    def _db_metrics(self) -> Iterator[Any]:
        from sqlalchemy import func, select

        from app.database import get_sessionmaker
        from app.models import Photo, PhotoFile

        try:
            with get_sessionmaker()() as s:
                photos = s.scalar(select(func.count(Photo.id))) or 0
                by_type = dict(
                    s.execute(
                        select(PhotoFile.file_type, func.count(PhotoFile.id))
                        .where(PhotoFile.exists.is_(True))
                        .group_by(PhotoFile.file_type)
                    ).all()
                )
                last = s.scalar(select(func.max(Photo.imported_at)))
        except Exception:
            return
        yield GaugeMetricFamily(f"{PREFIX}_photos_total", "Logical photos in library", value=photos)
        yield GaugeMetricFamily(f"{PREFIX}_raw_files_total", "RAW files tracked", value=by_type.get("raw", 0))
        yield GaugeMetricFamily(
            f"{PREFIX}_jpeg_files_total",
            "JPEG/HEIF files tracked",
            value=by_type.get("jpeg", 0) + by_type.get("image", 0),
        )
        yield GaugeMetricFamily(f"{PREFIX}_video_files_total", "Video files tracked", value=by_type.get("video", 0))
        yield GaugeMetricFamily(
            f"{PREFIX}_last_ingest_timestamp",
            "Unix time of the most recent new photo",
            value=last.timestamp() if last else 0,
        )

    def _queue_metrics(self) -> Iterator[Any]:
        from app.workers.queue import queue_stats, watcher_alive, worker_count

        try:
            stats = queue_stats()
            workers = worker_count()
            watcher = watcher_alive()
        except Exception:
            return
        depth = GaugeMetricFamily(f"{PREFIX}_queue_depth", "Jobs waiting", labels=["queue"])
        failed = GaugeMetricFamily(f"{PREFIX}_queue_failed", "Jobs in failed registry", labels=["queue"])
        for q in stats:
            depth.add_metric([q["name"]], q["queued"])
            failed.add_metric([q["name"]], q["failed"])
        yield depth
        yield failed
        yield GaugeMetricFamily(f"{PREFIX}_workers", "Active RQ workers", value=workers)
        yield GaugeMetricFamily(f"{PREFIX}_watcher_up", "Watcher heartbeat fresh", value=int(watcher))
