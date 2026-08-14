"""P3-2 query engine API — execute + explain."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_optional_current_user
from app.core.tenant_scope import tenant_id_from_user
from app.query.engine import execute_query

router = APIRouter()


class QueryBody(BaseModel):
    metric: str = Field(..., min_length=1, description="Metric key or id (e.g. fill_rate, A3-02)")
    grains: list[str] = Field(default_factory=list, description="Dimension ids to slice by")
    filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional filters: period_from/to, distributor_id, product_id, bu, customer_id",
    )
    period_grain: str | None = Field(
        default=None,
        description="Calendar bucket for calendar-period metrics: week | month | quarter (not daily)",
    )


@router.post("/execute")
async def query_execute(
    body: QueryBody,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Compose metric + grains + filters → validated execute with invariants + cache."""
    tid = tenant_id_from_user(user)
    result = await execute_query(
        db,
        metric=body.metric,
        grains=body.grains,
        filters=body.filters,
        tenant_id=tid,
        explain_only=False,
        period_grain=body.period_grain,
    )
    return result.as_dict()


@router.post("/explain")
async def query_explain(
    body: QueryBody,
    db: AsyncSession = Depends(get_db),
    user: dict | None = Depends(get_optional_current_user),
) -> dict[str, Any]:
    """Validate + show planned handler/invariants without running metric SQL."""
    tid = tenant_id_from_user(user)
    result = await execute_query(
        db,
        metric=body.metric,
        grains=body.grains,
        filters=body.filters,
        tenant_id=tid,
        explain_only=True,
        period_grain=body.period_grain,
    )
    return result.as_dict()
