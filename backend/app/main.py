from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Counter, Histogram, generate_latest
from redis.exceptions import RedisError
from sqlalchemy.exc import OperationalError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api import events, health, library, photos, system
from app.api.deps import require_token
from app.config import get_settings
from app.log import configure_logging, get_logger
from app.observability.metrics import AppCollector

log = get_logger(__name__)

HTTP_REQUESTS = Counter("z6iii_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram("z6iii_http_request_seconds", "HTTP request latency", ["route"])

_collector_registered = False


class MetricsMiddleware:
    """Pure ASGI (unlike BaseHTTPMiddleware it does not buffer SSE streams)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        status_code = 500

        async def _send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            route = scope.get("route")
            path = getattr(route, "path", "unmatched")
            if not path.endswith("/stream"):
                HTTP_LATENCY.labels(path).observe(time.perf_counter() - start)
            HTTP_REQUESTS.labels(scope.get("method", ""), path, str(status_code)).inc()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global _collector_registered
    configure_logging()
    if not _collector_registered:
        REGISTRY.register(AppCollector())
        _collector_registered = True
    s = get_settings()
    for d in (s.thumbnail_root, s.preview_root, s.cache_root):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log.error("data_dir_unwritable", path=str(d), error=str(exc))
    log.info("api_started", version=s.app_version, ai_provider=s.ai_provider)
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Z6III AI Studio API",
        description="Intelligent Nikon Photography Workflow — ingest, pairing, metadata and analysis.",
        version=s.app_version,
        lifespan=lifespan,
    )
    if s.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=s.cors_origins,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["*"],
        )
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.add_middleware(MetricsMiddleware)

    @app.exception_handler(OperationalError)
    async def db_down(_: Request, exc: OperationalError) -> JSONResponse:
        log.error("database_error", category="ERROR", error=str(exc).splitlines()[0])
        return JSONResponse({"detail": "database unavailable"}, status_code=503)

    @app.exception_handler(RedisError)
    async def redis_down(_: Request, exc: RedisError) -> JSONResponse:
        log.error("redis_error", category="ERROR", error=str(exc))
        return JSONResponse({"detail": "queue unavailable (Redis)"}, status_code=503)

    app.include_router(health.router)

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

    secured = [Depends(require_token)]
    for r in (photos.router, photos.files_router, system.router, events.router, library.router):
        app.include_router(r, prefix="/api/v1", dependencies=secured)
    return app


app = create_app()
