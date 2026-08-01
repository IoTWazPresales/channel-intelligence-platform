"""B4 — promotion plan builder draft (compose A2 + B1 + B2).

Draft only; create-case remains the existing CPOR write path.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cpor import CporCaseLine
from app.models.fact_demand_forecast import FactDemandForecast
from app.services import commercial_tenant_profile as tenant_profile
from app.services.cpor.norms_and_comparable import build_comparable_cases


def _forecast_volume_sync(
    session: Session,
    *,
    product_id: int | None,
    customer_id: int | None,
    horizon_weeks: int = 13,
) -> dict[str, Any]:
    as_of = date.today()
    period_to = as_of + timedelta(weeks=max(1, horizon_weeks))
    stmt = select(func.coalesce(func.sum(FactDemandForecast.forecast_units), 0)).where(
        FactDemandForecast.period_start >= as_of,
        FactDemandForecast.period_start < period_to,
    )
    if product_id is not None:
        stmt = stmt.where(FactDemandForecast.product_id == int(product_id))
    if customer_id is not None:
        stmt = stmt.where(FactDemandForecast.customer_id == int(customer_id))
    units = float(session.execute(stmt).scalar() or 0)
    return {
        "horizon_weeks": horizon_weeks,
        "period_from": as_of.isoformat(),
        "period_to": period_to.isoformat(),
        "forecast_units": units,
        "source": "fact_demand_forecast",
        "grain_filters": {"product_id": product_id, "customer_id": customer_id},
    }


def build_promo_plan_draft(
    session: Session,
    *,
    seed_case_id: int,
    product_id: int | None = None,
    customer_id: int | None = None,
    planned_support_usd: float | None = None,
    planned_revenue_usd: float | None = None,
    period_label: str | None = None,
    horizon_weeks: int = 13,
    comparable_limit: int = 10,
) -> dict[str, Any]:
    """Compose a promotion-plan draft for operator review / case authoring."""
    comparables = build_comparable_cases(session, case_id=seed_case_id, limit=comparable_limit)
    volume = _forecast_volume_sync(
        session,
        product_id=product_id,
        customer_id=customer_id,
        horizon_weeks=horizon_weeks,
    )

    drawn_stmt = select(
        func.coalesce(func.sum(CporCaseLine.ttl_support_usd), 0),
        func.count(CporCaseLine.id),
    )
    if period_label:
        drawn_stmt = drawn_stmt.where(CporCaseLine.pod_quarter == period_label)
    drawn_usd, line_n = session.execute(drawn_stmt).one()
    reserved = float(planned_support_usd or 0)
    drawn = float(drawn_usd or 0)
    remaining = (reserved - drawn) if reserved else None
    support_pct = None
    if planned_revenue_usd and float(planned_revenue_usd) > 0 and reserved:
        support_pct = reserved / float(planned_revenue_usd)

    budget = {
        "hard_enforce": bool(tenant_profile.HARD_ENFORCE_BUDGET),
        "constraint_type": tenant_profile.CONSTRAINT_AXIS,
        "binding_axis": tenant_profile.CONSTRAINT_AXIS,
        "over_budget_action": tenant_profile.OVER_BUDGET_ACTION,
        "tenant_profile": tenant_profile.profile_snapshot(),
        "tracks": {
            "money": {
                "planned_reservation_usd": reserved,
                "drawn_cpor_usd": drawn,
                "remaining_usd": remaining,
                "status": (
                    "over"
                    if reserved > 0 and drawn > reserved
                    else ("ok" if reserved > 0 else "no_planned_reservation")
                ),
                "binding": tenant_profile.CONSTRAINT_AXIS in ("money", "dual"),
            },
            "support_pct": {
                "planned_support_pct_of_sell_in": support_pct,
                "binding": tenant_profile.CONSTRAINT_AXIS in ("support_pct", "dual"),
            },
        },
        "cpor_line_count": int(line_n or 0),
        "period_label": period_label,
        "reservation_source": tenant_profile.RESERVATION_SOURCE,
        "q002_reservation_source": tenant_profile.RESERVATION_SOURCE,
    }

    top = (comparables.get("items") or [])[:3]
    suggested_estimate = float(volume["forecast_units"])
    if suggested_estimate <= 0 and top:
        ests = [float(t.get("estimate_qty") or 0) for t in top]
        ests = [e for e in ests if e > 0]
        if ests:
            suggested_estimate = sum(ests) / len(ests)

    return {
        "draft": True,
        "seed_case_id": seed_case_id,
        "comparables": {
            "count": len(comparables.get("items") or []),
            "top": top,
            "error": comparables.get("error"),
        },
        "volume": volume,
        "suggested_estimate_qty": round(float(suggested_estimate), 4),
        "budget_check": budget,
        "next_step": "Create/edit CPOR case via existing /cpor/cases; export via CPOR export",
        "notes": [
            f"Reservation source={tenant_profile.RESERVATION_SOURCE}; "
            f"binding_axis={tenant_profile.CONSTRAINT_AXIS}; "
            f"over_action={tenant_profile.OVER_BUDGET_ACTION} (hard_enforce="
            f"{tenant_profile.HARD_ENFORCE_BUDGET})",
            "Volume from fact_demand_forecast (B1); comparable volume is fallback only",
        ],
    }
