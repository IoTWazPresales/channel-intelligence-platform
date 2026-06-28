"""PO Management surface endpoints (Session C Unit 3).

Read-only, derived. Coverage = POs observed vs linked, grouped by quarter/year x product line.
Backlog = the same groups split into linked (with a reconciliation rollup) and unlinked (with an
upload prompt). Gated behind the commercial-planner feature flag, like the lineup endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.commercial_planner_auth import require_commercial_planner_enabled
from app.services.commercial_planner.po_management import backlog, coverage


async def _require_commercial_planner_enabled() -> None:
    await require_commercial_planner_enabled()


router = APIRouter(dependencies=[Depends(_require_commercial_planner_enabled)])


@router.get("/coverage")
async def get_coverage(db: AsyncSession = Depends(get_db)):
    """POs observed vs linked, grouped by quarter/year x inferred product line."""
    return await coverage(db)


@router.get("/backlog")
async def get_backlog(db: AsyncSession = Depends(get_db)):
    """Observed-PO groups split linked (reconciliation rollup) vs unlinked (upload prompt)."""
    return await backlog(db)
