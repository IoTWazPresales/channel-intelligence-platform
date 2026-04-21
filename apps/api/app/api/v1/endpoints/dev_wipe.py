"""Dangerous dev-only endpoints. Gated by ``ALLOW_DB_WIPE`` on the API process."""

from __future__ import annotations

import anyio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.db_wipe import wipe_all_application_tables

router = APIRouter()


class WipeConfirmBody(BaseModel):
    confirm: bool = Field(default=False, description="Must be true")


@router.get("/database-wipe")
async def database_wipe_status():
    """Whether POST /database-wipe is allowed for this API instance (no side effects)."""
    return {"wipe_enabled": get_settings().allow_db_wipe}


@router.post("/database-wipe", status_code=200)
async def database_wipe_execute(body: WipeConfirmBody):
    """
    Delete every row in every application table. Requires ``ALLOW_DB_WIPE=true`` on the API.

    Uses a sync engine in a worker thread so the request does not block the asyncio loop for long.
    """
    if not get_settings().allow_db_wipe:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "wipe_disabled",
                "message": "Set ALLOW_DB_WIPE=true on the API server to enable this endpoint.",
            },
        )
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm to true")

    out = await anyio.to_thread.run_sync(wipe_all_application_tables)
    return {"ok": True, **out}
