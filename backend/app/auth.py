from __future__ import annotations

import uuid

from fastapi import Header, HTTPException

from app.config import get_settings


async def current_user_id(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    authorization: str | None = Header(default=None),
) -> uuid.UUID:
    """
    Solo/dev: trust X-User-Id when allow_dev_auth is true.
    Production path: validate Supabase JWT from Authorization Bearer (Phase 4 hardening).
    """
    settings = get_settings()
    if x_user_id:
        if not settings.allow_dev_auth and settings.environment == "production":
            raise HTTPException(status_code=401, detail="Dev auth disabled")
        try:
            return uuid.UUID(x_user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid X-User-Id") from exc

    if authorization and authorization.lower().startswith("bearer "):
        # Placeholder: decode Supabase JWT in Phase 4. For now accept sub claim via header only.
        raise HTTPException(
            status_code=401,
            detail="JWT validation not wired yet — send X-User-Id for local/dev",
        )

    if settings.allow_dev_auth:
        return uuid.UUID(settings.dev_user_id)

    raise HTTPException(status_code=401, detail="Unauthorized")
