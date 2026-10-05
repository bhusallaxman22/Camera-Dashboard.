from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Integer, MetaData, String, event, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Mapper, mapped_column
from sqlalchemy.types import TypeDecorator

# Portable JSON: JSONB on Postgres (indexable, compact), JSON elsewhere (tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")
# SQLite only auto-increments INTEGER PRIMARY KEY.
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware datetime stored and returned in UTC.

    Postgres timestamptz already does this; SQLite would silently drop the
    offset (shifting camera times by hours), so normalise explicitly.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


_BOUNDED: dict[Mapper[Any], list[tuple[str, int]]] = {}


def _bounded_columns(mapper: Mapper[Any]) -> list[tuple[str, int]]:
    cached = _BOUNDED.get(mapper)
    if cached is None:
        cached = [
            (mapper.get_property_by_column(col).key, col.type.length)
            for col in mapper.columns
            if isinstance(col.type, String) and col.type.length
        ]
        _BOUNDED[mapper] = cached
    return cached


@event.listens_for(Base, "before_insert", propagate=True)
@event.listens_for(Base, "before_update", propagate=True)
def _truncate_bounded_strings(mapper: Mapper[Any], _connection: Any, target: Any) -> None:
    """EXIF and AI text is untrusted and unbounded: clip it to the column size
    rather than failing a whole ingest on one oversized maker-note value."""
    for key, length in _bounded_columns(mapper):
        value = getattr(target, key, None)
        if isinstance(value, str) and len(value) > length:
            setattr(target, key, value[:length])


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
        nullable=False,
    )
