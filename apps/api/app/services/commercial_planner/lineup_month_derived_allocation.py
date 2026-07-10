"""Month-derived 1H quarter allocation with uniform_half fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.commercial_planner.lineup_fiscal_calendar import (
    FiscalCalendarConfig,
    calendar_months_in_fiscal_quarter,
    first_half_fiscal_quarters,
    get_lineup_fiscal_calendar_config,
)
from app.services.commercial_planner.lineup_half_year_quantity import (
    HALF_YEAR_ALLOCATION_FLAG,
    allocate_uniform_half,
)
from app.services.commercial_planner.lineup_header_mapping import (
    build_commercial_lineup_column_map,
    norm_lineup_column_token,
)
from app.services.commercial_planner.lineup_month_column_detector import detect_month_columns

MONTH_DERIVED_ALLOCATION_FLAG = "allocation=month_derived"
QTY_MONTH_DISAGREEMENT_FLAG = "lineup_qty_month_disagreement"
QTY_DISAGREEMENT_TOLERANCE = 1e-3

_ALLOCATABLE_FIELDS = (
    "quantity_units",
    "msrp_local",
    "promo_price_evidence_local",
    "dap_evidence_local",
    "calc_dap_cost_currency",
    "calc_profit_total",
)

# quantity_units is set on allocation.quantity_units — never via proportional monetary split.
_MONETARY_FIELDS = tuple(f for f in _ALLOCATABLE_FIELDS if f != "quantity_units")

HalfName = Literal["q1", "q2"]


@dataclass
class HalfYearLineAllocation:
    tier: Literal["month_derived", "uniform_half"]
    half: HalfName
    quantity_units: float | None
    monetary: dict[str, float | None] = field(default_factory=dict)
    month_values: dict[str, float] = field(default_factory=dict)
    month_total_units: float = 0.0
    fiscal_q1_units: float = 0.0
    fiscal_q2_units: float = 0.0
    allocated_units_for_half: float = 0.0
    allocation_flag: str = HALF_YEAR_ALLOCATION_FLAG
    diagnostic_codes: list[str] = field(default_factory=list)
    qty_cell: float | None = None
    qty_month_disagreement: dict[str, Any] | None = None
    source_fields: dict[str, float] = field(default_factory=dict)


def _qty_from_uploaded(uploaded: dict[str, Any]) -> float | None:
    col_map = build_commercial_lineup_column_map(list(uploaded.keys()))
    header = col_map.get("quantity_units")
    if header and header in uploaded:
        try:
            return float(str(uploaded[header]).replace(",", "").strip())
        except (TypeError, ValueError):
            return None
    for key, val in uploaded.items():
        if norm_lineup_column_token(key) in ("qty", "quantity", "units", "forecastqty"):
            try:
                return float(str(val).replace(",", "").strip())
            except (TypeError, ValueError):
                return None
    return None


def _month_label(month: int) -> str:
    names = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return names[month] if 1 <= month <= 12 else str(month)


def _sum_fiscal_quarter_units(month_values: dict[int, float], fq: int, config: FiscalCalendarConfig) -> float:
    months = calendar_months_in_fiscal_quarter(fq, config)
    return sum(month_values.get(m, 0.0) for m in months)


def _line_source_fields(line: Any, raw: dict[str, Any]) -> dict[str, float]:
    sources: dict[str, float] = {}
    codes = list(getattr(line, "diagnostic_codes", None) or [])
    restore_double = HALF_YEAR_ALLOCATION_FLAG in codes and MONTH_DERIVED_ALLOCATION_FLAG not in codes
    for field in _ALLOCATABLE_FIELDS:
        snap_key = f"half_year_source_{field}"
        if snap_key in raw and raw[snap_key] is not None:
            sources[field] = float(raw[snap_key])
            continue
        val = getattr(line, field, None)
        if val is not None:
            v = float(val)
            if restore_double and field != "quantity_units":
                v *= 2.0
            sources[field] = v
    return sources


def _allocate_monetary_proportional(
    sources: dict[str, float],
    *,
    allocated_units: float,
    month_total_units: float,
) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    if month_total_units <= 0:
        return {k: None for k in _MONETARY_FIELDS}
    ratio = allocated_units / month_total_units
    for field in _MONETARY_FIELDS:
        src = sources.get(field)
        out[field] = float(src) * ratio if src is not None else None
    return out


def _allocate_monetary_uniform(sources: dict[str, float], *, half: HalfName) -> dict[str, float | None]:
    return {
        field: allocate_uniform_half(sources.get(field), half=half) if sources.get(field) is not None else None
        for field in _MONETARY_FIELDS
    }


def _build_diagnostic_codes(
    *,
    tier: str,
    qty_cell: float | None,
    month_total: float,
    disagreement_meta: dict[str, Any] | None,
    existing: list[str] | None,
) -> list[str]:
    codes = [c for c in (existing or []) if c not in (HALF_YEAR_ALLOCATION_FLAG, MONTH_DERIVED_ALLOCATION_FLAG, QTY_MONTH_DISAGREEMENT_FLAG)]
    if tier == "month_derived":
        codes.append(MONTH_DERIVED_ALLOCATION_FLAG)
    else:
        codes.append(HALF_YEAR_ALLOCATION_FLAG)
    if disagreement_meta is not None:
        codes.append(QTY_MONTH_DISAGREEMENT_FLAG)
    return codes


def compute_line_half_year_allocation(
    line: Any,
    *,
    half: HalfName,
    fiscal_config: FiscalCalendarConfig | None = None,
    shipment_q1_hint: float | None = None,
) -> HalfYearLineAllocation:
    """Allocate one lineup line to Q1 or Q2 using month-derived or uniform_half tier."""
    config = fiscal_config or get_lineup_fiscal_calendar_config()
    raw = dict(getattr(line, "raw_row_payload", None) or {})
    uploaded = raw.get("uploaded") if isinstance(raw.get("uploaded"), dict) else {}
    column_order = list(uploaded.keys()) if isinstance(uploaded, dict) else []
    qty_cell = _qty_from_uploaded(uploaded) if uploaded else None
    detection = detect_month_columns(uploaded, column_order=column_order, qty_cell_hint=qty_cell)
    sources = _line_source_fields(line, raw)

    fq1, fq2 = first_half_fiscal_quarters(config)
    fiscal_q1 = _sum_fiscal_quarter_units(detection.month_values, fq1, config)
    fiscal_q2 = _sum_fiscal_quarter_units(detection.month_values, fq2, config)
    month_total = fiscal_q1 + fiscal_q2

    month_labels = {_month_label(m): v for m, v in detection.month_values.items()}

    if detection.has_qualifying_block and month_total > 0:
        allocated_units = fiscal_q1 if half == "q1" else fiscal_q2
        monetary = _allocate_monetary_proportional(
            sources, allocated_units=allocated_units, month_total_units=month_total
        )
        disagreement_meta = None
        if qty_cell is not None and abs(qty_cell - month_total) > QTY_DISAGREEMENT_TOLERANCE:
            disagreement_meta = {
                "qty_cell": qty_cell,
                "month_total": month_total,
                "delta": month_total - qty_cell,
                "shipment_q1_hint": shipment_q1_hint,
            }
        diag = _build_diagnostic_codes(
            tier="month_derived",
            qty_cell=qty_cell,
            month_total=month_total,
            disagreement_meta=disagreement_meta,
            existing=list(getattr(line, "diagnostic_codes", None) or []),
        )
        return HalfYearLineAllocation(
            tier="month_derived",
            half=half,
            quantity_units=allocated_units,
            monetary=monetary,
            month_values=month_labels,
            month_total_units=month_total,
            fiscal_q1_units=fiscal_q1,
            fiscal_q2_units=fiscal_q2,
            allocated_units_for_half=allocated_units,
            allocation_flag=MONTH_DERIVED_ALLOCATION_FLAG,
            diagnostic_codes=diag,
            qty_cell=qty_cell,
            qty_month_disagreement=disagreement_meta,
            source_fields=sources,
        )

    # uniform_half fallback — source total from qty cell, else restored month total, else 2× persisted half.
    source_total = qty_cell
    if source_total is None:
        snap = raw.get("half_year_source_quantity_units")
        if snap is not None:
            source_total = float(snap) * 2.0
        elif getattr(line, "quantity_units", None) is not None:
            source_total = float(line.quantity_units) * 2.0
    if source_total is None:
        source_total = 0.0

    allocated_units = allocate_uniform_half(source_total, half=half)
    monetary = _allocate_monetary_uniform(sources, half=half)
    diag = _build_diagnostic_codes(
        tier="uniform_half",
        qty_cell=qty_cell,
        month_total=month_total,
        disagreement_meta=None,
        existing=list(getattr(line, "diagnostic_codes", None) or []),
    )
    return HalfYearLineAllocation(
        tier="uniform_half",
        half=half,
        quantity_units=allocated_units,
        monetary=monetary,
        month_values=month_labels,
        month_total_units=month_total,
        fiscal_q1_units=allocate_uniform_half(source_total, half="q1") or 0.0,
        fiscal_q2_units=allocate_uniform_half(source_total, half="q2") or 0.0,
        allocated_units_for_half=float(allocated_units or 0),
        allocation_flag=HALF_YEAR_ALLOCATION_FLAG,
        diagnostic_codes=diag,
        qty_cell=qty_cell,
        source_fields=sources,
    )


def case_allocation_summary_from_lines(
    line_allocations_q1: list[HalfYearLineAllocation],
    line_allocations_q2: list[HalfYearLineAllocation],
) -> dict[str, Any]:
    q1_total = sum(a.allocated_units_for_half for a in line_allocations_q1)
    q2_total = sum(a.allocated_units_for_half for a in line_allocations_q2)
    month_derived_count = sum(1 for a in line_allocations_q1 if a.tier == "month_derived")
    uniform_count = sum(1 for a in line_allocations_q1 if a.tier == "uniform_half")
    flags = {MONTH_DERIVED_ALLOCATION_FLAG, HALF_YEAR_ALLOCATION_FLAG}
    if month_derived_count and uniform_count:
        allocation_flag = "mixed"
    elif month_derived_count:
        allocation_flag = MONTH_DERIVED_ALLOCATION_FLAG
    else:
        allocation_flag = HALF_YEAR_ALLOCATION_FLAG
    return {
        "source_total_units": q1_total + q2_total,
        "q1_allocated_units": q1_total,
        "q2_allocated_units": q2_total,
        "allocation_flag": allocation_flag,
        "month_derived_line_count": month_derived_count,
        "uniform_half_line_count": uniform_count,
        "sum_invariant": abs(q1_total + q2_total - (q1_total + q2_total)) < 1e-3,
    }


def line_preview_dict(alloc_q1: HalfYearLineAllocation, alloc_q2: HalfYearLineAllocation, line: Any) -> dict[str, Any]:
    return {
        "line_id": int(getattr(line, "id", 0) or 0),
        "source_row_number": getattr(line, "source_row_number", None),
        "sku_raw": getattr(line, "sku_raw", None),
        "part_number_raw": getattr(line, "part_number_raw", None),
        "model_raw": getattr(line, "model_raw", None),
        "customer_token": getattr(line, "customer_token", None),
        "months_detected": alloc_q1.month_values,
        "month_total_units": alloc_q1.month_total_units,
        "qty_cell": alloc_q1.qty_cell,
        "q1_allocated_units": alloc_q1.allocated_units_for_half,
        "q2_allocated_units": alloc_q2.allocated_units_for_half,
        "allocation_tier": alloc_q1.tier,
        "allocation_flag": alloc_q1.allocation_flag,
        "qty_month_disagreement": alloc_q1.qty_month_disagreement,
    }


def lines_indicate_1h_month_phasing_for_config(
    lines: list[Any],
    config: FiscalCalendarConfig | None = None,
) -> bool:
    """True when stored rows have qualifying months spanning both 1H fiscal quarters."""
    cfg = config or get_lineup_fiscal_calendar_config()
    from app.services.commercial_planner.lineup_fiscal_calendar import calendar_months_in_first_half

    h1 = calendar_months_in_first_half(cfg)
    fq1_months = calendar_months_in_fiscal_quarter(1, cfg)
    fq2_months = calendar_months_in_fiscal_quarter(2, cfg)
    seen_q1 = seen_q2 = False
    for ln in lines:
        raw = getattr(ln, "raw_row_payload", None) or {}
        uploaded = raw.get("uploaded") if isinstance(raw, dict) else None
        if not isinstance(uploaded, dict):
            continue
        qty_cell = _qty_from_uploaded(uploaded)
        det = detect_month_columns(uploaded, column_order=list(uploaded.keys()), qty_cell_hint=qty_cell)
        if not det.has_qualifying_block:
            continue
        if det.month_values.keys() & fq1_months:
            seen_q1 = True
        if det.month_values.keys() & fq2_months:
            seen_q2 = True
        if seen_q1 and seen_q2:
            return True
    return False
