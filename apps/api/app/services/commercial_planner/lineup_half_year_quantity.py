"""Uniform 50/50 half-year quantity and economics allocation (sum-invariant)."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

HALF_YEAR_ALLOCATION_FLAG = "allocation=uniform_half"
PERIOD_SCOPE_1H_SPLIT_FLAG = "period_scope=1h_split"

# Monetary / economics fields that follow the same half allocation as quantity.
_ALLOCATABLE_FIELDS = (
    "quantity_units",
    "msrp_local",
    "promo_price_evidence_local",
    "dap_evidence_local",
    "calc_dap_cost_currency",
    "calc_profit_total",
)


def allocate_uniform_half(value: float | None, *, half: str) -> float | None:
    """Q1 gets ceil half; Q2 gets floor half — sum equals source exactly."""
    if value is None:
        return None
    v = float(value)
    if half == "q1":
        return float(math.ceil(v / 2.0))
    if half == "q2":
        return float(math.floor(v / 2.0))
    raise ValueError(f"half must be 'q1' or 'q2', got {half!r}")


def half_year_allocation_summary(source_total: float) -> dict[str, Any]:
    q1 = allocate_uniform_half(source_total, half="q1")
    q2 = allocate_uniform_half(source_total, half="q2")
    assert q1 is not None and q2 is not None
    return {
        "source_total_units": float(source_total),
        "q1_allocated_units": q1,
        "q2_allocated_units": q2,
        "allocation_flag": HALF_YEAR_ALLOCATION_FLAG,
        "sum_invariant": abs(q1 + q2 - float(source_total)) < 1e-3,
    }


def _append_allocation_flag(diag: list[str] | None) -> list[str]:
    out = list(diag or [])
    if HALF_YEAR_ALLOCATION_FLAG not in out:
        out.append(HALF_YEAR_ALLOCATION_FLAG)
    return out


def apply_half_year_allocation_to_row_dict(row: dict[str, Any], *, half: str) -> dict[str, Any]:
    """Return a copy of a parse row dict with half-year allocation applied."""
    out = deepcopy(row)
    raw = dict(out.get("raw_row_payload") or {})
    for field in _ALLOCATABLE_FIELDS:
        if field not in out and field not in raw:
            continue
        source = out.get(field)
        if source is None and field in raw:
            source = raw.get(field)
        if source is None:
            continue
        allocated = allocate_uniform_half(float(source), half=half)
        out[field] = allocated
        raw[f"half_year_source_{field}"] = source
    out["raw_row_payload"] = raw
    out["diagnostic_codes"] = _append_allocation_flag(out.get("diagnostic_codes"))
    return out


def apply_half_year_allocation_to_line_fields(
    *,
    quantity_units: float | None,
    msrp_local: float | None = None,
    promo_price_evidence_local: float | None = None,
    dap_evidence_local: float | None = None,
    calc_dap_cost_currency: float | None = None,
    calc_profit_total: float | None = None,
    half: str,
) -> dict[str, float | None]:
    """Allocate persisted line columns for re-derivation updates."""
    fields = {
        "quantity_units": quantity_units,
        "msrp_local": msrp_local,
        "promo_price_evidence_local": promo_price_evidence_local,
        "dap_evidence_local": dap_evidence_local,
        "calc_dap_cost_currency": calc_dap_cost_currency,
        "calc_profit_total": calc_profit_total,
    }
    return {k: allocate_uniform_half(v, half=half) if v is not None else None for k, v in fields.items()}


def sum_line_quantities(lines: list[Any]) -> float:
    total = 0.0
    for ln in lines:
        q = getattr(ln, "quantity_units", None)
        if q is not None:
            total += float(q)
    return total
