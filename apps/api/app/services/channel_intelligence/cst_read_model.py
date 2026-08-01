"""CPOR U4.6 — CST channel intelligence read-model (compute-on-read).

Per (customer, product [, site]): trailing velocity, weeks-of-cover, aged/dead-stock
flag, velocity trend. Explainable factors only — no composite score. No schema writes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.services.channel_ops_derived_stock import VELOCITY_NEAR_ZERO, weeks_of_cover_or_none

# Grain policy (A3): monthly rows contribute as weekly-equivalent units (÷ 4.345).
MONTHLY_TO_WEEKLY = Decimal("4.345")
# Sparse threshold (A4): need this many weekly-equivalent observations before metrics fire.
DEFAULT_MIN_OBSERVED_WEEKS = 4
# Aged/dead-stock: SOH > 0 and velocity ≈ 0 over this many trailing weeks.
DEFAULT_AGED_LOOKBACK_WEEKS = 8
# Trend: compare recent 4wk vs prior 4wk.
TREND_WINDOW_WEEKS = 4
TREND_FLAT_PCT = Decimal("0.05")

GRAIN_POLICY = "normalize_monthly_to_weekly_avg"


@dataclass(frozen=True)
class PeriodObs:
    period_start: date
    period_type: str
    units_sold: Decimal
    reported_soh: Decimal | None
    unit_sell_price: Decimal | None
    weekly_equiv_units: Decimal


def _weekly_equiv(units: Decimal, period_type: str) -> Decimal:
    pt = (period_type or "weekly").strip().lower()
    if pt.startswith("month"):
        return units / MONTHLY_TO_WEEKLY
    return units


def _period_end(period_start: date, period_type: str) -> date:
    pt = (period_type or "weekly").strip().lower()
    if pt.startswith("month"):
        # Approximate month end for window membership
        if period_start.month == 12:
            return date(period_start.year + 1, 1, 1) - timedelta(days=1)
        return date(period_start.year, period_start.month + 1, 1) - timedelta(days=1)
    return period_start + timedelta(days=6)


def build_observations(rows: list[Any]) -> list[PeriodObs]:
    out: list[PeriodObs] = []
    for r in rows:
        units = Decimal(str(r.units_sold or 0))
        soh = Decimal(str(r.reported_soh)) if r.reported_soh is not None else None
        price = Decimal(str(r.unit_sell_price)) if r.unit_sell_price is not None else None
        pt = str(r.period_type or "weekly")
        out.append(
            PeriodObs(
                period_start=r.period_start_date,
                period_type=pt,
                units_sold=units,
                reported_soh=soh,
                unit_sell_price=price,
                weekly_equiv_units=_weekly_equiv(units, pt),
            )
        )
    out.sort(key=lambda o: o.period_start)
    return out


def sum_weekly_equiv_in_window(
    obs: list[PeriodObs],
    *,
    as_of: date,
    window_weeks: int,
) -> tuple[Decimal, int]:
    """Sum weekly-equivalent units whose period_start falls in [as_of - window*7 + 1, as_of]."""
    cutoff = as_of - timedelta(days=window_weeks * 7 - 1)
    total = Decimal("0")
    n = 0
    for o in obs:
        if cutoff <= o.period_start <= as_of:
            total += o.weekly_equiv_units
            n += 1
    return total, n


def velocity_units_per_week(window_sum: Decimal, window_weeks: int) -> Decimal:
    if window_weeks <= 0:
        return Decimal("0")
    return window_sum / Decimal(window_weeks)


def classify_trend(recent: Decimal, prior: Decimal) -> str:
    if prior <= VELOCITY_NEAR_ZERO and recent <= VELOCITY_NEAR_ZERO:
        return "flat"
    if prior <= VELOCITY_NEAR_ZERO:
        return "rising" if recent > VELOCITY_NEAR_ZERO else "flat"
    delta = (recent - prior) / prior
    if abs(delta) <= TREND_FLAT_PCT:
        return "flat"
    return "rising" if delta > 0 else "falling"


def compute_entity_metrics(
    obs: list[PeriodObs],
    *,
    as_of: date | None = None,
    min_observed_weeks: int = DEFAULT_MIN_OBSERVED_WEEKS,
    aged_lookback_weeks: int = DEFAULT_AGED_LOOKBACK_WEEKS,
) -> dict[str, Any]:
    """Pure metrics for one (customer, product [, site]) observation series."""
    if not obs:
        return {
            "data_state": "insufficient_data",
            "reason": "no_observations",
            "grain_policy": GRAIN_POLICY,
            "velocity_4wk": None,
            "velocity_13wk": None,
            "weeks_of_cover": None,
            "weeks_of_cover_reason": "no_observations",
            "aged_dead_stock": False,
            "velocity_trend": None,
            "factors": {"observed_weeks": 0, "min_observed_weeks": min_observed_weeks},
        }

    anchor = as_of or max(o.period_start for o in obs)
    # Count distinct ISO weeks covered by weekly rows + monthly as ~4 weeks each
    observed_weeks = 0
    for o in obs:
        pt = o.period_type.lower()
        if pt.startswith("month"):
            observed_weeks += 4
        else:
            observed_weeks += 1

    sum4, n4 = sum_weekly_equiv_in_window(obs, as_of=anchor, window_weeks=4)
    sum13, n13 = sum_weekly_equiv_in_window(obs, as_of=anchor, window_weeks=13)
    v4 = velocity_units_per_week(sum4, 4)
    v13 = velocity_units_per_week(sum13, 13)

    # Prior 4wk window for trend (weeks 5–8 before as_of)
    prior_end = anchor - timedelta(days=4 * 7)
    sum_prior, _ = sum_weekly_equiv_in_window(obs, as_of=prior_end, window_weeks=4)
    v_prior = velocity_units_per_week(sum_prior, 4)
    trend = classify_trend(v4, v_prior)

    # Latest SOH + sell price at or before as_of
    latest_soh: Decimal | None = None
    latest_soh_date: date | None = None
    latest_price: Decimal | None = None
    for o in reversed(obs):
        if o.period_start > anchor:
            continue
        if latest_soh is None and o.reported_soh is not None:
            latest_soh = o.reported_soh
            latest_soh_date = o.period_start
        if latest_price is None and o.unit_sell_price is not None:
            latest_price = o.unit_sell_price
        if latest_soh is not None and latest_price is not None:
            break

    aged_sum, _ = sum_weekly_equiv_in_window(obs, as_of=anchor, window_weeks=aged_lookback_weeks)
    aged_vel = velocity_units_per_week(aged_sum, aged_lookback_weeks)

    factors: dict[str, Any] = {
        "as_of": anchor.isoformat(),
        "observed_weeks": observed_weeks,
        "min_observed_weeks": min_observed_weeks,
        "window_4wk_units": float(sum4),
        "window_4wk_periods": n4,
        "window_13wk_units": float(sum13),
        "window_13wk_periods": n13,
        "velocity_4wk_raw": float(v4),
        "velocity_13wk_raw": float(v13),
        "prior_4wk_velocity": float(v_prior),
        "latest_soh": float(latest_soh) if latest_soh is not None else None,
        "latest_soh_date": latest_soh_date.isoformat() if latest_soh_date else None,
        "unit_sell_price": float(latest_price) if latest_price is not None else None,
        "aged_lookback_weeks": aged_lookback_weeks,
        "aged_window_units": float(aged_sum),
        "aged_velocity": float(aged_vel),
        "velocity_near_zero": float(VELOCITY_NEAR_ZERO),
        "grain_policy": GRAIN_POLICY,
    }

    if observed_weeks < min_observed_weeks:
        return {
            "data_state": "insufficient_data",
            "reason": "below_min_observed_weeks",
            "grain_policy": GRAIN_POLICY,
            "velocity_4wk": float(v4),
            "velocity_13wk": float(v13),
            "weeks_of_cover": None,
            "weeks_of_cover_reason": "insufficient_data",
            "aged_dead_stock": False,
            "velocity_trend": trend,
            "factors": factors,
        }

    woc = weeks_of_cover_or_none(latest_soh, v4)
    woc_reason = None
    if woc is None:
        if latest_soh is None:
            woc_reason = "missing_soh"
        else:
            woc_reason = "velocity_near_zero"

    aged = bool(
        latest_soh is not None
        and latest_soh > 0
        and aged_vel <= VELOCITY_NEAR_ZERO
    )
    aged_factors = {
        **{k: factors[k] for k in ("latest_soh", "latest_soh_date", "unit_sell_price", "aged_velocity", "aged_lookback_weeks")},
        "interpretation": (
            "not selling at the given price"
            if aged and latest_price is not None
            else ("dead stock / no movement" if aged else "not aged")
        ),
    }

    return {
        "data_state": "ok",
        "reason": None,
        "grain_policy": GRAIN_POLICY,
        "velocity_4wk": float(v4),
        "velocity_13wk": float(v13),
        "weeks_of_cover": woc,
        "weeks_of_cover_reason": woc_reason,
        "aged_dead_stock": aged,
        "aged_factors": aged_factors,
        "velocity_trend": trend,
        "factors": factors,
    }


def _site_key(site_label: str | None) -> str | None:
    if site_label is None:
        return None
    s = str(site_label).strip()
    return s or None


def load_cst_read_model(
    session: Session,
    *,
    customer_id: int | None = None,
    product_id: int | None = None,
    site_label: str | None = None,
    as_of: date | None = None,
    page: int = 1,
    page_size: int = 50,
    min_observed_weeks: int = DEFAULT_MIN_OBSERVED_WEEKS,
    aged_lookback_weeks: int = DEFAULT_AGED_LOOKBACK_WEEKS,
    tenant_id: str = "default",
) -> dict[str, Any]:
    """Aggregate CST facts → per-entity metrics. Compute-on-read; no writes."""
    tid = (tenant_id or "default").strip() or "default"
    stmt = select(FactCustomerSellthrough).where(FactCustomerSellthrough.tenant_id == tid)
    if customer_id is not None:
        stmt = stmt.where(FactCustomerSellthrough.customer_id == customer_id)
    if product_id is not None:
        stmt = stmt.where(FactCustomerSellthrough.product_id == product_id)
    if site_label is not None:
        stmt = stmt.where(FactCustomerSellthrough.site_label == site_label)

    rows = list(session.scalars(stmt).all())
    if not rows:
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "data_unavailable": True,
            "grain_policy": GRAIN_POLICY,
            "message": "No fact_customer_sellthrough rows for filters",
        }

    grouped: dict[tuple[int, int, str | None], list[Any]] = defaultdict(list)
    for r in rows:
        key = (int(r.customer_id), int(r.product_id), _site_key(r.site_label))
        grouped[key].append(r)

    items: list[dict[str, Any]] = []
    for (cid, pid, site), group_rows in grouped.items():
        obs = build_observations(group_rows)
        metrics = compute_entity_metrics(
            obs,
            as_of=as_of,
            min_observed_weeks=min_observed_weeks,
            aged_lookback_weeks=aged_lookback_weeks,
        )
        items.append(
            {
                "customer_id": cid,
                "product_id": pid,
                "site_label": site,
                **metrics,
            }
        )

    items.sort(key=lambda x: (x["customer_id"], x["product_id"], x["site_label"] or ""))
    total = len(items)
    start = max(0, (page - 1) * page_size)
    page_items = items[start : start + page_size]

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "data_unavailable": False,
        "grain_policy": GRAIN_POLICY,
        "thresholds": {
            "min_observed_weeks": min_observed_weeks,
            "aged_lookback_weeks": aged_lookback_weeks,
            "velocity_near_zero": float(VELOCITY_NEAR_ZERO),
        },
    }
