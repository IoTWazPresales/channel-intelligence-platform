"""B1 compute-from-history orchestrator — velocity then analogue, one engine.

Does not write sell-out / CST / inventory facts. Override rows are skipped.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.demand_forecast.analogue_compute import generate_analogue_demand_forecasts
from app.services.demand_forecast.velocity_compute import (
    generate_velocity_demand_forecasts,
    resolve_forecast_tenant_id,
)


def compute_from_history(
    db: Session,
    *,
    tenant_id: str | None = None,
    distributor_id: int | None = None,
    weeks_ahead: int = 13,
    max_analogue_products: int = 50,
) -> dict[str, Any]:
    tid = resolve_forecast_tenant_id(tenant_id)
    velocity = generate_velocity_demand_forecasts(
        db,
        distributor_id=distributor_id,
        weeks_ahead=weeks_ahead,
        skip_overrides=True,
        tenant_id=tid,
    )
    analogue = generate_analogue_demand_forecasts(
        db,
        weeks_ahead=weeks_ahead,
        skip_overrides=True,
        max_products=max_analogue_products,
        tenant_id=tid,
    )
    return {
        "tenant_id": tid,
        "weeks_ahead": int(weeks_ahead),
        "skip_overrides": True,
        "never_merges_actuals": True,
        "contract_table": "fact_demand_forecast",
        "velocity": velocity,
        "analogue": analogue,
    }
