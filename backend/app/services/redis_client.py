from __future__ import annotations

from functools import lru_cache

import redis
import redis.asyncio as aioredis

from app.config import get_settings


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(
        get_settings().redis_url,
        socket_connect_timeout=3,
        socket_timeout=10,
        health_check_interval=30,
        retry_on_timeout=True,
    )


def get_async_redis() -> aioredis.Redis:
    """New asyncio client (one per SSE connection; closed by the caller)."""
    return aioredis.from_url(get_settings().redis_url, socket_connect_timeout=3)


def redis_healthy() -> tuple[bool, str | None]:
    try:
        get_redis().ping()
        return True, None
    except Exception as exc:
        return False, str(exc)
