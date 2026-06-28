"""Case-level product_line enrichment from resolved catalogue rows."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.dimensions import DimProduct
from app.services.commercial_planner.lineup_period_inference import infer_case_product_line


async def ensure_case_product_line_from_catalogue(
    db: AsyncSession, case: CommercialLineupCase
) -> bool:
    """When case.product_line is unset, derive it from resolved dim_product lines (row-weighted).

    Returns True when the case was updated (caller should commit).
    """
    if case.product_line is not None:
        return False

    product_ids_per_row = (
        await db.execute(
            select(CommercialLineupLine.product_id).where(CommercialLineupLine.case_id == case.id)
        )
    ).scalars().all()
    total_rows = len(product_ids_per_row)
    if total_rows == 0:
        return False

    unique_ids = sorted({int(pid) for pid in product_ids_per_row if pid is not None})
    pline_by_id: dict[int, str | None] = {}
    if unique_ids:
        rows = (
            await db.execute(
                select(DimProduct.id, DimProduct.product_line).where(DimProduct.id.in_(unique_ids))
            )
        ).all()
        pline_by_id = {int(r[0]): r[1] for r in rows}

    resolved_plines: list[str] = []
    for pid in product_ids_per_row:
        if pid is None:
            continue
        pl = pline_by_id.get(int(pid))
        if pl and str(pl).strip():
            resolved_plines.append(str(pl).strip())

    inferred = infer_case_product_line(
        filename=case.file_name,
        total_rows=total_rows,
        resolved_product_lines=resolved_plines,
    )
    if not inferred:
        return False
    case.product_line = inferred
    return True
