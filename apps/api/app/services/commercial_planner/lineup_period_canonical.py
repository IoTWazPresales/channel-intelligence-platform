"""Canonical lineup period keys — quarter from ``inferred_period_start`` only.

``period_label`` is display metadata; consumers must key on ``inferred_period_start``.
"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from app.services.commercial_planner.lineup_period_inference import _parse_label

if TYPE_CHECKING:
    from app.models.commercial_lineup import CommercialLineupCase


def quarter_from_period_start(period_start: date) -> tuple[int, int]:
    """Return (calendar_year, quarter_number 1-4) for a period-start date."""
    return period_start.year, (period_start.month - 1) // 3 + 1


def quarter_bounds_from_period_start(period_start: date) -> tuple[date, date]:
    """Inclusive start, exclusive end for the calendar quarter of ``period_start``."""
    _year, q = quarter_from_period_start(period_start)
    start_month = 3 * (q - 1) + 1
    start = date(period_start.year, start_month, 1)
    if q == 4:
        end = date(period_start.year + 1, 1, 1)
    else:
        end = date(period_start.year, start_month + 3, 1)
    return start, end


def quarter_key_from_period_start(period_start: date) -> str:
    """Compact quarter token used in PO management groups (e.g. ``26Q2``)."""
    year, q = quarter_from_period_start(period_start)
    return f"{str(year)[-2:]}Q{q}"


def display_period_label_from_period_start(period_start: date) -> str:
    """Human display label — majority format on ``cip`` (e.g. ``2026 Q2``)."""
    year, q = quarter_from_period_start(period_start)
    return f"{year} Q{q}"


def parse_period_filter_to_year_quarter(period_filter: str | None) -> tuple[int | None, int | None]:
    """Parse a steward/API period filter into (year, quarter); month labels map to quarter."""
    if not period_filter or not str(period_filter).strip():
        return None, None
    year, quarter, month = _parse_label(period_filter)
    if quarter is None and month is not None:
        quarter = (month - 1) // 3 + 1
    return year, quarter


def period_filter_matches_period_start(period_filter: str | None, period_start: date | None) -> bool:
    """True when filter is empty or matches the case quarter derived from ``period_start``."""
    if not period_filter or not str(period_filter).strip():
        return True
    if period_start is None:
        return False
    filt_year, filt_q = parse_period_filter_to_year_quarter(period_filter)
    case_year, case_q = quarter_from_period_start(period_start)
    if filt_year is not None and filt_year != case_year:
        return False
    if filt_q is not None and filt_q != case_q:
        return False
    return True


def canonical_case_line_code(case: CommercialLineupCase) -> str | None:
    """Archive folder / card product-line code — ``business_unit`` wins over inferred ``product_line``."""
    for raw in (case.business_unit, case.product_line):
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    return None


def case_product_line_tokens(case: CommercialLineupCase) -> set[str]:
    """Product-line tokens used to match PO-management observed groups (BU-primary)."""
    code = canonical_case_line_code(case)
    return {code} if code else set()


def case_coverage_key(case: CommercialLineupCase) -> set[tuple[int, int, str]]:
    """(year, quarter, line) keys this case satisfies for PO-management coverage."""
    if case.inferred_period_start is None:
        return set()
    line = canonical_case_line_code(case)
    if not line:
        return set()
    year, q = quarter_from_period_start(case.inferred_period_start)
    return {(year, q, line)}


def is_active_lineup_case(case: CommercialLineupCase) -> bool:
    """Non-superseded, non-cancelled lineup case eligible for PO consumers."""
    if case.commercial_status in ("cancelled", "superseded"):
        return False
    return case.superseded_by_case_id is None


def active_lineup_case_filters():
    """SQLAlchemy boolean filters for active lineup cases."""
    from app.models.commercial_lineup import CommercialLineupCase

    return (
        CommercialLineupCase.superseded_by_case_id.is_(None),
        CommercialLineupCase.commercial_status.notin_(("cancelled", "superseded")),
    )


def supersession_group_key_from_period_start(
    period_start: date | str | None,
    *,
    customer_id: int | None,
    customer_token: str | None,
    business_unit: str | None,
    normalize_customer_token,
) -> str:
    """Canonical supersession key: ISO quarter-start | customer | BU."""
    period_key = "unknown"
    if period_start is not None:
        if isinstance(period_start, str):
            try:
                d = date.fromisoformat(period_start[:10])
            except ValueError:
                d = None
        else:
            d = period_start
        if d is not None:
            period_key = d.isoformat()
    cust = str(customer_id) if customer_id is not None else normalize_customer_token(customer_token) or "unknown"
    bu = (business_unit or "unknown").strip().upper()
    return f"{period_key}|{cust}|{bu}"
