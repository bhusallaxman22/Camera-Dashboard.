"""Immich integration (read-only, optional).

Startup never depends on Immich. With IMMICH_ENABLED=true the app can look up
the Immich asset that corresponds to a camera JPEG (Immich imports the same
`immich-jpeg` folder as an external library) and link to it. Nothing is ever
written to Immich.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.config import get_settings
from app.log import get_logger
from app.utils.timeutil import local_tz

log = get_logger(__name__)


class ImmichError(RuntimeError):
    pass


def immich_asset_url(asset_id: str | None) -> str | None:
    s = get_settings()
    base = s.immich_public_url or s.immich_url
    if not (s.immich_enabled and asset_id and base):
        return None
    return f"{base.rstrip('/')}/photos/{asset_id}"


class ImmichClient:
    def __init__(self) -> None:
        s = get_settings()
        self.enabled = bool(s.immich_enabled and s.immich_url and s.immich_api_key)
        self.base = s.immich_url.rstrip("/")
        self.headers = {"x-api-key": s.immich_api_key, "Accept": "application/json"}

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        if not self.enabled:
            raise ImmichError("Immich integration is disabled")
        try:
            r = httpx.post(f"{self.base}/api{path}", json=body, headers=self.headers, timeout=15)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            raise ImmichError(str(exc)) from exc

    def ping(self) -> tuple[bool, str | None]:
        if not self.enabled:
            return False, "disabled"
        try:
            r = httpx.get(f"{self.base}/api/server/ping", headers=self.headers, timeout=5)
            return r.status_code == 200, None if r.status_code == 200 else f"HTTP {r.status_code}"
        except httpx.HTTPError as exc:
            return False, str(exc)

    def find_asset(self, filename: str, capture_time: datetime | None) -> str | None:
        """Find an asset by original filename, disambiguated by capture time."""
        data = self._post("/search/metadata", {"originalFileName": filename, "size": 20})
        items = (data.get("assets") or {}).get("items") or []
        if not items:
            return None
        if capture_time is None or len(items) == 1:
            return items[0]["id"]

        # Immich's localDateTime is wall-clock time serialised with a "Z".
        local_capture = capture_time.astimezone(local_tz()).replace(tzinfo=None)

        def delta(item: dict[str, Any]) -> float:
            raw = item.get("localDateTime") or item.get("fileCreatedAt")
            try:
                t = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                return abs((t.replace(tzinfo=None) - local_capture).total_seconds())
            except (TypeError, ValueError):
                return float("inf")

        return min(items, key=delta)["id"]
