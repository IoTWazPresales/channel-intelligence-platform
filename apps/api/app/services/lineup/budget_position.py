"""B2 budget position — dual track (money + support-%), no hard enforce.

Domain §1.8: track both views; do not hard-enforce until constraint type is settled.
Drawn spend aggregates ``cpor_case_line.ttl_support_usd`` (prefer filter on pod_quarter).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_planner import CommercialSkuAssumption
from app.models.cpor import CporCaseLine


async def build_budget_position(
    db: AsyncSession,
    *,
    planned_reservations: list[dict[str, Any]] | None = None,
    period_label: str | None = None,
) -> dict[str, Any]:
    """Aggregate planned reservations vs CPOR line spend (dual track).

    ``planned_reservations`` items: ``{product_id?, customer_id?, reserved_amount, revenue?}``.
    """
    planned = list(planned_reservations or [])
    reserved_money = sum(float(p.get("reserved_amount") or 0) for p in planned)
    planned_revenue = sum(float(p.get("revenue") or 0) for p in planned)
    reserved_pct = (reserved_money / planned_revenue) if planned_revenue > 0 else None

    drawn_usd_f = 0.0
    drawn_zar_f = 0.0
    line_count = 0
    cpor_ok = True
    try:
        stmt = select(
            func.coalesce(func.sum(CporCaseLine.ttl_support_usd), 0),
            func.coalesce(func.sum(CporCaseLine.ttl_support), 0),
            func.count(CporCaseLine.id),
        )
        if period_label:
            stmt = stmt.where(CporCaseLine.pod_quarter == period_label)
        drawn_usd, drawn_zar, n = (await db.execute(stmt)).one()
        drawn_usd_f = float(drawn_usd or 0)
        drawn_zar_f = float(drawn_zar or 0)
        line_count = int(n or 0)
    except Exception:
        cpor_ok = False

    remaining_money = reserved_money - drawn_usd_f
    money_util = (drawn_usd_f / reserved_money) if reserved_money > 0 else None

    try:
        sku_n = int(
            (await db.execute(select(func.count()).select_from(CommercialSkuAssumption))).scalar()
            or 0
        )
    except Exception:
        sku_n = 0

    return {
        "as_of": date.today().isoformat(),
        "period_label": period_label,
        "hard_enforce": False,
        "constraint_type": "undetermined",
        "tracks": {
            "money": {
                "planned_reservation_usd": round(reserved_money, 4),
                "drawn_cpor_usd": round(drawn_usd_f, 4),
                "drawn_cpor_zar_display": round(drawn_zar_f, 4),
                "remaining_usd": round(remaining_money, 4),
                "utilisation": money_util,
                "status": (
                    "over"
                    if reserved_money > 0 and drawn_usd_f > reserved_money
                    else ("ok" if reserved_money > 0 else "no_planned_reservation")
                ),
            },
            "support_pct": {
                "planned_support_pct_of_sell_in": reserved_pct,
                "note": "Planned % from reservation÷sell-in revenue; actual % from A2 norms",
            },
        },
        "cpor_line_count": line_count,
        "cpor_data_available": cpor_ok,
        "sku_assumption_count": sku_n,
        "planned_line_count": len(planned),
        "basis": "cpor_case_line.ttl_support_usd; optional pod_quarter filter (landed)",
        "q002_reservation_source": "derived_interim",
    }
