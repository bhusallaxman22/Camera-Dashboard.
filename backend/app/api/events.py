from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import DB
from app.log import get_logger
from app.models import SystemEvent
from app.schemas.system import EventOut
from app.services import redis_client
from app.services.events import CHANNEL

router = APIRouter(prefix="/events", tags=["events"])
log = get_logger(__name__)

HEARTBEAT_SECONDS = 15


@router.get("", response_model=list[EventOut])
def list_events(
    db: DB,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    category: str | None = None,
    level: str | None = None,
    before_id: int | None = None,
) -> list[SystemEvent]:
    stmt = select(SystemEvent).order_by(SystemEvent.id.desc()).limit(limit)
    if category:
        stmt = stmt.where(SystemEvent.category == category.upper())
    if level:
        stmt = stmt.where(SystemEvent.level == level)
    if before_id:
        stmt = stmt.where(SystemEvent.id < before_id)
    return list(db.scalars(stmt).all())


async def _stream(request: Request) -> AsyncIterator[str]:
    client = redis_client.get_async_redis()
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(CHANNEL)
        yield "retry: 3000\n\n"
        yield f"event: hello\ndata: {json.dumps({'channel': CHANNEL})}\n\n"
        loop = asyncio.get_running_loop()
        last_beat = loop.time()
        while not await request.is_disconnected():
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg.get("type") == "message":
                data = msg["data"].decode() if isinstance(msg["data"], bytes) else msg["data"]
                yield f"data: {data}\n\n"
            if loop.time() - last_beat >= HEARTBEAT_SECONDS:
                yield ": keep-alive\n\n"
                last_beat = loop.time()
    except (aioredis.ConnectionError, OSError) as exc:
        log.warning("sse_redis_error", error=str(exc))
        yield f"event: error\ndata: {json.dumps({'error': 'event bus unavailable'})}\n\n"
    finally:
        try:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()
            await client.aclose()
        except Exception:
            pass


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    """Server-Sent Events: photo.created / photo.updated / photo.analyzed / system.event."""
    return StreamingResponse(
        _stream(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
