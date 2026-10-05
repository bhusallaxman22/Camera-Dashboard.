"""Watcher entrypoint: `python -m app.watchers.run`.

Watches JPEG_ROOT, RAW_ROOT, VIDEO_ROOT and UNSORTED_ROOT recursively (read-only), debounces
events until files are stable, and enqueues ingest jobs. Also triggers the
startup scan and periodic reconcile scans, and publishes a heartbeat.
"""

from __future__ import annotations

import signal
import sys
import threading
import time
from pathlib import Path

from redis.exceptions import RedisError
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers.api import BaseObserver
from watchdog.observers.polling import PollingObserver

from app.config import get_settings
from app.log import configure_logging, get_logger
from app.models.enums import JobKind
from app.utils.paths import classify
from app.watchers.stability import StabilityTracker
from app.workers.queue import enqueue, reap_orphaned_jobs, set_watcher_heartbeat

log = get_logger(__name__)

REAP_INTERVAL_SECONDS = 300


class MediaEventHandler(FileSystemEventHandler):
    def __init__(self, tracker: StabilityTracker) -> None:
        self.tracker = tracker
        self.events_seen = 0

    def _consider(self, path: str | bytes, deleted: bool = False) -> None:
        p = path.decode() if isinstance(path, bytes) else path
        if classify(p) is None:
            return
        self.events_seen += 1
        if deleted:
            self.tracker.deleted(p)
        else:
            self.tracker.touch(p)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._consider(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._consider(event.src_path)

    def on_closed(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._consider(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        # The FTP sorter moves files into YYYY/MM/DD; the destination matters.
        if event.is_directory:
            return
        self._consider(event.dest_path)
        self._consider(event.src_path, deleted=True)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._consider(event.src_path, deleted=True)


def make_observer(mode: str, poll_interval: float) -> tuple[BaseObserver, str]:
    if mode == "polling":
        return PollingObserver(timeout=poll_interval), "polling"
    if sys.platform.startswith("linux"):
        try:
            from watchdog.observers.inotify import InotifyObserver

            return InotifyObserver(), "inotify"
        except Exception as exc:
            if mode == "inotify":
                raise
            log.warning("inotify_unavailable", category="WATCH", error=str(exc))
            return PollingObserver(timeout=poll_interval), "polling"
    from watchdog.observers import Observer

    return Observer(), "native"


class Watcher:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.tracker = StabilityTracker(self.settings.file_stable_seconds)
        self.handler = MediaEventHandler(self.tracker)
        self.stop_event = threading.Event()
        self.observer: BaseObserver | None = None
        self.mode = "starting"
        self.watched: list[str] = []
        self.enqueued = 0
        self.last_event_at: float | None = None
        self.last_scan_at = 0.0

    def _roots(self) -> list[Path]:
        return [r for r in self.settings.media_roots.values()]

    def start_observer(self) -> None:
        roots = [r for r in self._roots() if r.is_dir()]
        missing = [str(r) for r in self._roots() if not r.is_dir()]
        if missing:
            log.warning("watch_roots_missing", category="WATCH", roots=missing)
        self.observer, self.mode = make_observer(self.settings.watch_mode, self.settings.watch_poll_interval_seconds)
        for root in roots:
            self.observer.schedule(self.handler, str(root), recursive=True)
        self.observer.start()
        self.watched = [str(r) for r in roots]
        log.info("watcher_started", category="WATCH", mode=self.mode, roots=self.watched)

    def _enqueue_ingest(self, path: str) -> bool:
        try:
            enqueue(
                JobKind.INGEST_FILE,
                dedupe_key=path,
                target_path=path,
                payload={"path": path, "source": "live"},
            )
            self.enqueued += 1
            self.last_event_at = time.time()
            log.info("file_ready", category="WATCH", path=path)
            return True
        except RedisError as exc:
            log.error("enqueue_failed", category="ERROR", path=path, error=str(exc))
            return False
        except Exception as exc:
            log.error("enqueue_failed", category="ERROR", path=path, error=str(exc))
            return False

    def _scan(self, reason: str) -> None:
        try:
            enqueue(JobKind.SCAN, dedupe_key="reconcile", payload={"source": "scan"})
            self.last_scan_at = time.time()
            log.info("scan_enqueued", category="WATCH", reason=reason)
        except Exception as exc:
            log.error("scan_enqueue_failed", category="ERROR", error=str(exc))

    def heartbeat(self) -> None:
        try:
            set_watcher_heartbeat(
                {
                    "mode": self.mode,
                    "roots": self.watched,
                    "roots_ok": len(self.watched) == len(self._roots()),
                    "pending": len(self.tracker),
                    "enqueued": self.enqueued,
                    "events_seen": self.handler.events_seen,
                    "last_event_at": self.last_event_at,
                    "observer_alive": bool(self.observer and self.observer.is_alive()),
                }
            )
        except RedisError as exc:
            log.warning("heartbeat_failed", category="WATCH", error=str(exc))

    def run(self) -> None:
        s = self.settings
        if s.watch_enabled:
            self.start_observer()
        else:
            self.mode = "disabled"
        if s.scan_on_startup:
            self._scan("startup")
        else:
            self.last_scan_at = time.time()

        last_hb = 0.0
        last_reap = time.time()
        reconcile_every = s.reconcile_interval_minutes * 60
        while not self.stop_event.is_set():
            ready, gone = self.tracker.poll()
            failed = [p for p in ready + gone if not self._enqueue_ingest(p)]
            if failed:
                self.tracker.requeue(failed)
            now = time.time()
            if now - last_hb >= 10:
                self.heartbeat()
                last_hb = now
                if self.observer and not self.observer.is_alive() and s.watch_enabled:
                    log.error("observer_died_restarting", category="WATCH")
                    self.start_observer()
                elif s.watch_enabled and len(self.watched) < len(self._roots()):
                    # A root was unavailable at start (share not mounted yet, or the
                    # sorter has not created the optional unsorted folder).
                    if any(r.is_dir() for r in self._roots() if str(r) not in self.watched):
                        log.info("watch_roots_recovered", category="WATCH")
                        if self.observer:
                            self.observer.stop()
                        self.start_observer()
                        self._scan("roots_recovered")
            if reconcile_every and now - self.last_scan_at >= reconcile_every:
                self._scan("periodic")
            if now - last_reap >= REAP_INTERVAL_SECONDS:
                last_reap = now
                try:
                    reap_orphaned_jobs()
                except Exception as exc:
                    log.warning("reap_failed", category="ERROR", error=str(exc))
            self.stop_event.wait(1.0)

        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
        log.info("watcher_stopped", category="WATCH")


def main() -> None:
    configure_logging()
    watcher = Watcher()

    def _stop(*_: object) -> None:
        watcher.stop_event.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    watcher.run()


if __name__ == "__main__":
    main()
