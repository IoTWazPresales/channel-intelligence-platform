"""Read-only steward export for unresolved lineup case tokens (no auto-create)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupLine
from app.services.commercial_planner.lineup_entity_resolution import collect_entity_resolution_candidates


async def build_lineup_steward_export(db: AsyncSession, case_id: int) -> dict:
    """Export entity-resolution candidates + unresolved product SKUs for steward review."""
    candidates = await collect_entity_resolution_candidates(db, case_id)

    unresolved_products: list[dict] = []
    rows = (
        await db.execute(
            select(CommercialLineupLine).where(
                CommercialLineupLine.case_id == case_id,
                CommercialLineupLine.product_id.is_(None),
            )
        )
    ).scalars().all()
    seen: set[str] = set()
    for ln in rows:
        token = (ln.sku_raw or ln.part_number_raw or ln.model_raw or "").strip()
        if not token:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        unresolved_products.append(
            {
                "token_display": token,
                "sku_raw": ln.sku_raw,
                "part_number_raw": ln.part_number_raw,
                "model_raw": ln.model_raw,
                "line_count": 1,
                "sample_line_ids": [ln.id],
                "diagnostic_codes": ln.diagnostic_codes or [],
            }
        )

    return {
        "case_id": case_id,
        "customer_tokens": candidates.get("customer_tokens", []),
        "distributor_tokens": candidates.get("distributor_tokens", []),
        "unresolved_products": unresolved_products,
        "governance_note": (
            "Read-only export for steward review. Resolve via case entity-resolution or Product Master — "
            "no automatic dim_product / dim_customer / dim_distributor creation from this export."
        ),
    }
