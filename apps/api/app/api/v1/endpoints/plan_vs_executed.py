"""Plan vs Executed intelligence view endpoints (derived-on-read)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.commercial_planner_auth import require_commercial_planner_enabled
from app.services.commercial_planner.plan_vs_executed import plan_vs_executed_read_model


async def _require_commercial_planner_enabled() -> None:
    await require_commercial_planner_enabled()


router = APIRouter(dependencies=[Depends(_require_commercial_planner_enabled)])


@router.get("")
async def get_plan_vs_executed(
    db: AsyncSession = Depends(get_db),
    period_from: str | None = Query(None, description="Start quarter e.g. 26Q1"),
    period_to: str | None = Query(None, description="End quarter e.g. 26Q2"),
    product_line: str | None = Query(None, description="Optional BU / product_line filter"),
    rank_by: Literal["units", "value"] = Query("units"),
    product_group_by: Literal["description", "sku", "sales_model"] = Query(
        "description",
        description="Product lens grouping attribute",
    ),
    drill_customer_id: int | None = Query(None),
    drill_product_id: int | None = Query(None),
    drill_sales_model: str | None = Query(None),
    drill_bu: str | None = Query(None),
    exceptions_lens: Literal["customer", "product", "bu"] = Query(
        "customer",
        description="Exception grid lens (only this lens is returned; refetch on tab change)",
    ),
    exceptions_category: Literal[
        "short_ships",
        "over_ships",
        "unplanned_intake",
        "no_po_blind_spots",
    ] = Query("short_ships", description="Active exception category for the paged items slice"),
    exceptions_limit: int = Query(
        15,
        ge=1,
        le=500,
        description="Max exception rows returned for the active category",
    ),
    exceptions_offset: int = Query(0, ge=0, description="Offset into the active category ranked list"),
):
    """Portfolio scorecard, exception lists, trend, and six-flag drill rows."""
    return await plan_vs_executed_read_model(
        db,
        period_from=period_from,
        period_to=period_to,
        product_line=product_line,
        rank_by=rank_by,
        product_group_by=product_group_by,
        drill_customer_id=drill_customer_id,
        drill_product_id=drill_product_id,
        drill_sales_model=drill_sales_model,
        drill_bu=drill_bu,
        exceptions_lens=exceptions_lens,
        exceptions_category=exceptions_category,
        exceptions_limit=exceptions_limit,
        exceptions_offset=exceptions_offset,
    )
