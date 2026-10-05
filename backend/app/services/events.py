"""Activity log + live event bus.

Events are persisted as SystemEvent rows and published on a Redis pub/sub
channel that the SSE endpoint relays to browsers. Publishing is deferred until
the surrounding DB transaction commits so clients never fetch data that is not
visible yet.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from redis.exceptions import RedisError
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.log import get_logger
from app.models import SystemEvent
from app.services.redis_client import get_redis

log = get_logger(__name__)

CHANNEL = "z6iii:events"
_PENDING_KEY = "z6iii_pending_events"


def _default(obj: Any) -> Any:
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"not JSON serialisable: {type(obj)}")


def publish(event_type: str, payload: dict[str, Any] | None = None) -> None:
    """Publish immediately (best effort; Redis outages never fail the caller)."""
    message = {"type": event_type, "ts": datetime.now(UTC).isoformat(), "data": payload or {}}
    try:
        get_redis().publish(CHANNEL, json.dumps(message, default=_default))
    except RedisError as exc:
        log.warning("event_publish_failed", category="ERROR", type=event_type, error=str(exc))


def publish_after_commit(session: Session, event_type: str, payload: dict[str, Any]) -> None:
    session.info.setdefault(_PENDING_KEY, []).append((event_type, payload))


def record_event(
    session: Session,
    category: str,
    event_name: str,
    message: str,
    *,
    level: str = "info",
    photo_id: uuid.UUID | None = None,
    data: dict[str, Any] | None = None,
    broadcast: bool = True,
) -> SystemEvent:
    row = SystemEvent(
        category=category,
        event=event_name,
        message=message,
        level=level,
        photo_id=photo_id,
        data=json.loads(json.dumps(data or {}, default=_default)),
    )
    session.add(row)
    if broadcast:
        publish_after_commit(
            session,
            "system.event",
            {
                "category": category,
                "event": event_name,
                "message": message,
                "level": level,
                "photo_id": photo_id,
                "data": data or {},
            },
        )
    return row


@event.listens_for(Session, "after_commit")
def _flush_pending(session: Session) -> None:
    pending = session.info.pop(_PENDING_KEY, None)
    for event_type, payload in pending or ():
        publish(event_type, payload)


@event.listens_for(Session, "after_rollback")
def _drop_pending(session: Session) -> None:
    session.info.pop(_PENDING_KEY, None)
