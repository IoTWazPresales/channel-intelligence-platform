"""Product Master gap worklist — cross-import unresolved product tokens."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services.imports.product_master_gap_worklist import product_master_gap_worklist

router = APIRouter()


@router.get("/worklist")
async def get_product_master_gap_worklist(
    db: AsyncSession = Depends(get_db),
    source: Literal["shipment", "dsi", "cpor_claim"] | None = Query(default=None),
    status: Literal["unresolved", "ignored"] | None = Query(default=None),
    search: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=2000, ge=1, le=5000),
):
    """Derived-on-read aggregation of product tokens that failed PM resolution."""
    return await product_master_gap_worklist(
        db,
        source=source,
        status=status,
        search=search,
        limit=limit,
    )
