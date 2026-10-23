"""P3-2 query engine API — execute + explain."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import get_current_user, get_optional_current_user
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


class V2Period(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    grain: str | None = Field(default=None, description="week | month | quarter | year (day refused)")
    from_: str | None = Field(default=None, alias="from", description="YYYY-MM-DD or 26Q2")
    to: str | None = Field(default=None, description="YYYY-MM-DD or 26Q2")


class V2Sort(BaseModel):
    by: str | None = Field(default=None, description="A requested measure id or breakdown id")
    dir: str | None = Field(default=None, description="asc | desc")


class V2QueryBody(BaseModel):
    measures: list[str] = Field(..., min_length=1, max_length=20, description="Measure ids from the v2 catalog")
    breakdowns: list[str] = Field(default_factory=list, max_length=10, description="Breakdown ids (at most 3 used)")
    filters: dict[str, Any] = Field(default_factory=dict, description="{breakdown_id: value | [values]}")
    period: V2Period | None = None
    sort: V2Sort | None = None
    limit: int | None = Field(default=None, description="Rows (default 500; above 5000 refused)")

    def to_request(self):
        from app.query.model.graph import V2Request

        p = self.period or V2Period()
        s = self.sort or V2Sort()
        return V2Request(
            measures=list(self.measures),
            breakdowns=list(self.breakdowns),
            filters=dict(self.filters),
            period_grain=p.grain,
            period_from=p.from_,
            period_to=p.to,
            sort_by=s.by,
            sort_dir=s.dir,
            limit=self.limit,
        )


@router.post("/v2/execute")
async def query_v2_execute(
    body: V2QueryBody,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """N-0115: measures x breakdowns x filters x period through the model compiler (signed in only)."""
    from app.query.model.execute import run_v2

    return await run_v2(db, body.to_request(), tenant_id=tenant_id_from_user(user))


@router.post("/v2/explain")
async def query_v2_explain(
    body: V2QueryBody,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Validate a v2 query and show the compiled SQL (parameter names only) without running it."""
    from app.query.model.execute import run_v2

    return await run_v2(db, body.to_request(), tenant_id=tenant_id_from_user(user), explain_only=True)


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
