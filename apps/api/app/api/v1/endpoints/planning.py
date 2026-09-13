"""Planning domain read APIs (overview headlines)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_optional_current_user
from app.services.planning_overview import planning_overview

router = APIRouter()


@router.get("/overview")
async def get_planning_overview(
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
):
    """Headline grains for Planning. Read-only; prints database identity in the payload."""
    return await planning_overview(db, user)
