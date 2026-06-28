"""Case-level product_line enrichment from resolved catalogue rows."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.dimensions import DimProduct
from app.services.commercial_planner.lineup_period_inference import infer_product_line_from_catalogue_values


async def ensure_case_product_line_from_catalogue(
    db: AsyncSession, case: CommercialLineupCase
) -> bool:
    """When case.product_line is unset, derive it from majority dim_product line/BU on resolved rows.

    Returns True when the case was updated (caller should commit).
    """
    if case.product_line is not None:
        return False
    product_ids = (
        await db.execute(
            select(CommercialLineupLine.product_id)
            .where(CommercialLineupLine.case_id == case.id)
            .where(CommercialLineupLine.product_id.isnot(None))
        )
    ).scalars().all()
    unique_ids = sorted({int(pid) for pid in product_ids if pid is not None})
    if not unique_ids:
        return False
    rows = (
        await db.execute(
            select(DimProduct.product_line, DimProduct.business_unit).where(
                DimProduct.id.in_(unique_ids)
            )
        )
    ).all()
    inferred = infer_product_line_from_catalogue_values(
        [r[0] for r in rows],
        [r[1] for r in rows],
    )
    if not inferred:
        return False
    case.product_line = inferred
    return True
