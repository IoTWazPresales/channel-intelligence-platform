"""Commercial read APIs for shipment evidence lines (filters + pagination)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.endpoints.shipment_evidence import _apply_filters, _line_to_dict
from app.models.dimensions import DimDistributor, DimProduct
from app.models.shipment_evidence import ShipmentEvidenceLine

router = APIRouter()


@router.get("/summary")
async def shipping_evidence_summary(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Lightweight counts for dashboard tiles (no admin gate — same posture as /dashboard/summary)."""
    by_state = await db.execute(
        select(ShipmentEvidenceLine.line_state, func.count())
        .group_by(ShipmentEvidenceLine.line_state)
        .order_by(ShipmentEvidenceLine.line_state)
    )
    by_product = await db.execute(
        select(ShipmentEvidenceLine.product_resolution_status, func.count())
        .group_by(ShipmentEvidenceLine.product_resolution_status)
        .order_by(ShipmentEvidenceLine.product_resolution_status)
    )
    total = await db.scalar(select(func.count()).select_from(ShipmentEvidenceLine)) or 0
    return {
        "total_lines": int(total),
        "by_line_state": {str(r[0]): int(r[1]) for r in by_state.all() if r[0] is not None},
        "by_product_resolution_status": {
            str(r[0]): int(r[1]) for r in by_product.all() if r[0] is not None
        },
    }


@router.get("/lines")
async def shipping_evidence_lines(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    import_job_id: int | None = None,
    line_state: str | None = None,
    report_type: str | None = None,
    product_resolution_status: str | None = None,
    distributor_resolution_status: str | None = None,
    customer_resolution_status: str | None = None,
    search: str | None = None,
    include_raw_row: bool = Query(False),
) -> dict[str, Any]:
    filt: dict[str, Any] = {
        "import_job_id": import_job_id,
        "line_state": line_state,
        "report_type": report_type,
        "product_resolution_status": product_resolution_status,
        "distributor_resolution_status": distributor_resolution_status,
        "search": search,
    }
    count_stmt = select(func.count()).select_from(ShipmentEvidenceLine)
    count_stmt = _apply_filters(count_stmt, **filt)
    if customer_resolution_status:
        count_stmt = count_stmt.where(
            ShipmentEvidenceLine.customer_resolution_status == customer_resolution_status
        )
    total = int((await db.execute(count_stmt)).scalar_one())

    q = select(ShipmentEvidenceLine).order_by(ShipmentEvidenceLine.id.desc())
    q = _apply_filters(q, **filt)
    if customer_resolution_status:
        q = q.where(ShipmentEvidenceLine.customer_resolution_status == customer_resolution_status)
    res = await db.execute(q.offset(skip).limit(limit))
    rows = res.scalars().all()

    prod_ids = {r.product_id for r in rows if r.product_id}
    dist_ids = {r.distributor_id for r in rows if r.distributor_id}
    products: dict[int, str] = {}
    distributors: dict[int, str] = {}
    if prod_ids:
        pr = await db.execute(select(DimProduct).where(DimProduct.id.in_(prod_ids)))
        for p in pr.scalars().all():
            products[int(p.id)] = p.sku or ""
    if dist_ids:
        dr = await db.execute(select(DimDistributor).where(DimDistributor.id.in_(dist_ids)))
        for d in dr.scalars().all():
            distributors[int(d.id)] = d.code or d.name or ""

    items = [
        _line_to_dict(
            r,
            product_sku=products.get(int(r.product_id)) if r.product_id else None,
            distributor_code=distributors.get(int(r.distributor_id)) if r.distributor_id else None,
            include_raw_row=include_raw_row,
        )
        for r in rows
    ]
    return {"total": total, "skip": skip, "limit": limit, "items": items}
