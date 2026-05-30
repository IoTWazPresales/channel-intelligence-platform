"""Commercial planner lineup routes (parse async, steward export)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.commercial_planner_auth import require_commercial_planner_enabled
from app.models.commercial_lineup import CommercialLineupCase
from app.services.commercial_planner.steward_export import build_lineup_steward_export

router = APIRouter(dependencies=[Depends(require_commercial_planner_enabled)])


@router.get("/lineup-cases/{case_id}/steward-export")
async def get_lineup_steward_export(case_id: int, db: AsyncSession = Depends(get_db)):
    """Read-only export of unresolved tokens for steward review (no auto-create)."""
    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Lineup case not found")
    return await build_lineup_steward_export(db, case_id)
