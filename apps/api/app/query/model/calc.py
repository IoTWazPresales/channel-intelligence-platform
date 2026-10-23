"""Calculated measures: null rules and totals.

Per row the calculated measures are SQL over the grouped result (``compiler.compile_plan``), so
they sort and limit like any other column. Null rules (the same in SQL and in totals):

- ratio a / b: null when b is 0 or null;
- difference a - b: null when either side is null (same units only; the loader checks);
- prior_period: the measure in the previous bucket of the same grain with the same other
  breakdown values; null when that bucket has no rows (never an invented 0);
- pct_change: (this - previous) / previous; null when previous is 0 or null;
- per_week_rate: measure / business weeks in the bucket (clipped to period.from / period.to) or in
  the period window; null when the window has no days.

Totals come from the SQL totals of the base inputs. A period comparison (prior_period, pct_change,
or a difference over a prior) has no single total and returns null.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from app.query.model.compiler import bucket_last_day, bucket_start_of
from app.query.model.loader import Calculated, DataModel, Measure


def _dec(v: Any) -> Decimal | None:
    if v is None:
        return None
    return v if isinstance(v, Decimal) else Decimal(str(v))


def window_weeks(
    *,
    period_from: date | None,
    period_to: date | None,
    grain: str | None,
    vintage_min: date | None,
    vintage_max: date | None,
) -> Decimal | None:
    """Business weeks covered by the query window (for per_week_rate totals)."""
    start = period_from
    end = period_to
    if grain:
        if start is None and vintage_min is not None:
            start = bucket_start_of(vintage_min, grain)
        if end is None and vintage_max is not None:
            end = bucket_last_day(bucket_start_of(vintage_max, grain), grain)
    if start is None or end is None or end < start:
        return None
    return Decimal((end - start).days + 1) / Decimal(7)


def total_for(
    dm: DataModel,
    measure: Measure | Calculated,
    base_totals: dict[str, Decimal | None],
    *,
    weeks: Decimal | None,
) -> Decimal | None:
    if isinstance(measure, Measure):
        return _dec(base_totals.get(measure.id))
    kind = measure.kind
    if kind in ("prior_period", "pct_change"):
        return None
    inputs = [dm.measure(i) for i in measure.inputs]
    if any(i is None for i in inputs):
        return None
    vals = [total_for(dm, i, base_totals, weeks=weeks) for i in inputs]  # type: ignore[arg-type]
    if kind == "difference":
        if vals[0] is None or vals[1] is None:
            return None
        return vals[0] - vals[1]
    if kind == "ratio":
        if vals[0] is None or vals[1] is None or vals[1] == 0:
            return None
        return vals[0] / vals[1]
    if kind == "per_week_rate":
        if vals[0] is None or weeks is None or weeks == 0:
            return None
        return vals[0] / weeks
    return None
