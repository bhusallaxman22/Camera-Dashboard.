from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db

DB = Annotated[Session, Depends(get_db)]


def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
    """Optional shared-token auth. Disabled when API_TOKEN is empty.

    The Next.js proxy injects the token server-side, so browsers never see it.
    For internet exposure put Cloudflare Access in front as well.
    """
    token = get_settings().api_token
    if not token:
        return
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied, token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing API token")
