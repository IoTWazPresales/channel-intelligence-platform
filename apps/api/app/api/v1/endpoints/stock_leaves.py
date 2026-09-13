"""Stock leftover-leaf read APIs (Sell-through / Forecasts ThinLens honesty)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_optional_current_user
from app.services.stock_leaves_honesty import stock_leaves_honesty

router = APIRouter()


@router.get("/leaves-honesty")
async def get_stock_leaves_honesty(
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
):
    """ThinLens grains for leftover stock lenses. Read-only."""
    return await stock_leaves_honesty(db, user)
