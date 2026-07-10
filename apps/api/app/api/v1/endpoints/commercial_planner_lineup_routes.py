"""Commercial planner lineup routes (parse async, steward export, duplicate partition)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.commercial_planner_auth import require_commercial_planner_enabled
from app.db.session_sync import SessionLocal
from app.models.commercial_lineup import CommercialLineupCase
from app.services.commercial_planner.lineup_duplicate_partition_repair import (
    apply_duplicate_partition,
    list_duplicate_ingestion_clusters,
    preview_duplicate_partition,
)
from app.services.commercial_planner.steward_export import build_lineup_steward_export

router = APIRouter(dependencies=[Depends(require_commercial_planner_enabled)])


class DuplicatePartitionBody(BaseModel):
    case_ids: list[int] = Field(..., min_length=1)
    confirm: bool = False


@router.get("/lineup/duplicate-ingestion/clusters")
async def get_duplicate_ingestion_clusters():
    """Active duplicate-ingestion clusters (BACKLOG-066 steward worklist)."""
    with SessionLocal() as db:
        return list_duplicate_ingestion_clusters(db, sample_limit=50)


@router.post("/lineup/duplicate-ingestion/partition/preview")
async def post_duplicate_partition_preview(body: DuplicatePartitionBody):
    with SessionLocal() as db:
        return preview_duplicate_partition(db, case_ids=body.case_ids)


@router.post("/lineup/duplicate-ingestion/partition/apply")
async def post_duplicate_partition_apply(body: DuplicatePartitionBody):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to apply partition repair")
    with SessionLocal() as db:
        return apply_duplicate_partition(db, case_ids=body.case_ids)


@router.get("/lineup-cases/{case_id}/steward-export")
async def get_lineup_steward_export(case_id: int, db: AsyncSession = Depends(get_db)):
    """Read-only export of unresolved tokens for steward review (no auto-create)."""
    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Lineup case not found")
    return await build_lineup_steward_export(db, case_id)
