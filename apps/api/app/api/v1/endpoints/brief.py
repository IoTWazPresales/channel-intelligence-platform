from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_optional_current_user
from app.services.brief_signals import build_brief_payload

router = APIRouter()


@router.get("/signals")
async def brief_signals(
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
):
    return await build_brief_payload(db, user)
