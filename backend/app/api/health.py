from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.services.system_status import health_components

router = APIRouter(tags=["health"])


@router.get("/health/live", include_in_schema=False)
def live() -> dict[str, str]:
    """Process liveness (used by the container healthcheck)."""
    return {"status": "ok"}


@router.get("/health")
def health() -> JSONResponse:
    comps = health_components()
    core_ok = comps["database"].ok and comps["redis"].ok
    all_ok = all(c.ok for c in comps.values())
    status = "ok" if all_ok else ("degraded" if core_ok else "error")
    body = {
        "status": status,
        "version": get_settings().app_version,
        "time": datetime.now(UTC).isoformat(),
        "components": {k: v.model_dump() for k, v in comps.items()},
    }
    return JSONResponse(body, status_code=200 if core_ok else 503)
