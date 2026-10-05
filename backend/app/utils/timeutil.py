from __future__ import annotations

import os
from datetime import UTC, datetime, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@lru_cache
def local_tz() -> tzinfo:
    """Timezone used for camera timestamps that carry no UTC offset (TZ env)."""
    name = os.environ.get("TZ")
    if name:
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            pass
    return datetime.now().astimezone().tzinfo or UTC


def from_timestamp(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=UTC)


def ensure_aware(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; treat naive datetimes from the DB as UTC."""
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=UTC)


def start_of_local_day(now: datetime | None = None) -> datetime:
    now = (now or datetime.now(UTC)).astimezone(local_tz())
    return now.replace(hour=0, minute=0, second=0, microsecond=0)
