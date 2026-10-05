"""Worker entrypoint: `python -m app.workers.run [queue ...]`."""

from __future__ import annotations

import socket
import sys
import time
import uuid

from redis.exceptions import RedisError
from rq import Worker

from app.config import get_settings
from app.log import configure_logging, get_logger
from app.services.redis_client import get_redis
from app.workers.queue import ALL_QUEUES, WORKER_TTL

# Import heavy modules in the parent so forked work-horses inherit them.
import app.workers.tasks  # noqa: F401
import cv2  # noqa: F401

log = get_logger(__name__)


def main(argv: list[str]) -> None:
    configure_logging()
    queues = argv or list(ALL_QUEUES)
    settings = get_settings()
    while True:
        try:
            get_redis().ping()
            break
        except RedisError as exc:
            log.warning("worker_waiting_for_redis", error=str(exc))
            time.sleep(3)
    # Unique per start: a crashed worker's registration lingers until its TTL.
    name = f"z6iii-{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
    worker = Worker(queues, connection=get_redis(), name=name, worker_ttl=WORKER_TTL)
    log.info("worker_started", queues=queues, name=name, ai_provider=settings.ai_provider)
    worker.work(with_scheduler=True, logging_level=settings.log_level.upper())


if __name__ == "__main__":
    main(sys.argv[1:])
