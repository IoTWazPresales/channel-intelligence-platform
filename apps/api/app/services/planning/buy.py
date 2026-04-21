"""Deterministic buy recommendation from coverage math."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class BuyInputs:
    forecast_weekly_demand: float
    on_hand: float
    inbound: float
    target_wos: float
    lead_time_weeks: float
    horizon_weeks: float = 8.0


@dataclass(frozen=True)
class BuyPlanResult:
    recommended_qty: float
    window_start: date
    window_end: date
    rationale: str
    risk_if_not_ordered: str


def build_buy_plan(inputs: BuyInputs, today: date | None = None) -> BuyPlanResult:
    today = today or date.today()
    weekly = max(inputs.forecast_weekly_demand, 0.0)
    pipeline = inputs.on_hand + inputs.inbound
    target_cover = inputs.target_wos * weekly
    lead_cover = inputs.lead_time_weeks * weekly
    need = target_cover + lead_cover - pipeline
    recommended = max(need, 0.0)

    window_start = today
    window_end = today + timedelta(weeks=1)

    rationale = (
        f"Pipeline {pipeline:.0f} units vs target coverage {target_cover:.0f} "
        f"(WOS {inputs.target_wos:.1f} × weekly demand {weekly:.1f}) "
        f"plus lead-time cover {lead_cover:.0f} ({inputs.lead_time_weeks:.1f}w × demand)."
    )
    risk = (
        "Delayed or skipped order risks stockout before inbound and lead-time coverage closes the gap."
        if recommended > 0
        else "No immediate procurement gap at current forecast and pipeline."
    )

    return BuyPlanResult(
        recommended_qty=round(recommended, 2),
        window_start=window_start,
        window_end=window_end,
        rationale=rationale,
        risk_if_not_ordered=risk,
    )
