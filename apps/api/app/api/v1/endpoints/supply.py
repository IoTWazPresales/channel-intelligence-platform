"""Supply & Inbound domain read APIs (overview headlines)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_optional_current_user
from app.services.supply_overview import supply_overview

router = APIRouter()


@router.get("/overview")
async def get_supply_overview(
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
):
    """Headline grains for Supply & Inbound. Read-only; prints database identity in the payload."""
    return await supply_overview(db, user)
