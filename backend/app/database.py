from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    if settings.is_sqlite:
        engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # pragma: no cover - sqlite only
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine
    # pool_pre_ping transparently recovers from Postgres restarts.
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=10,
        pool_recycle=1800,
    )


def _reset_pool_after_fork() -> None:
    # RQ forks a work-horse per job; never share pooled connections across fork.
    if get_engine.cache_info().currsize:
        get_engine().dispose(close=False)


os.register_at_fork(after_in_child=_reset_pool_after_fork)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for workers/CLI: commit on success, rollback on error."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def db_healthy() -> tuple[bool, str | None]:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:
        return False, str(exc).splitlines()[0]


def advisory_lock(session: Session, key: str) -> None:
    """Transaction-scoped Postgres advisory lock (no-op on SQLite).

    Used to serialise pairing of files that share a base filename so that a
    JPEG and NEF processed concurrently by two workers never create two Photos.
    """
    if session.get_bind().dialect.name != "postgresql":
        return
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": key})
