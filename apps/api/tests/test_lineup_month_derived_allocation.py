"""Tests for fiscal calendar, month detector, and month-derived 1H allocation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.commercial_planner.lineup_fiscal_calendar import (
    FiscalCalendarConfig,
    calendar_months_in_fiscal_quarter,
    fiscal_quarter_for_calendar_month,
    half_year_period_starts,
)
from app.services.commercial_planner.lineup_half_year_quantity import HALF_YEAR_ALLOCATION_FLAG
from app.services.commercial_planner.lineup_month_column_detector import (
    detect_month_columns,
    is_plausible_unit_quantity,
    parse_calendar_month_from_column,
)
from app.services.commercial_planner.lineup_month_derived_allocation import (
    MONTH_DERIVED_ALLOCATION_FLAG,
    QTY_MONTH_DISAGREEMENT_FLAG,
    compute_line_half_year_allocation,
)
from app.services.commercial_planner.lineup_bulk_rederivation import (
    _apply_allocation_to_line,
    _snapshot_line_sources,
)


def test_fiscal_calendar_january_default():
    cfg = FiscalCalendarConfig(fiscal_year_start_month=1)
    assert fiscal_quarter_for_calendar_month(1, cfg) == 1
    assert fiscal_quarter_for_calendar_month(4, cfg) == 2
    assert calendar_months_in_fiscal_quarter(1, cfg) == frozenset({1, 2, 3})
    assert calendar_months_in_fiscal_quarter(2, cfg) == frozenset({4, 5, 6})
    q1, q2 = half_year_period_starts(2026, cfg)
    assert q1 == __import__("datetime").date(2026, 1, 1)
    assert q2 == __import__("datetime").date(2026, 4, 1)


def test_fiscal_calendar_april_start():
    cfg = FiscalCalendarConfig(fiscal_year_start_month=4)
    assert fiscal_quarter_for_calendar_month(4, cfg) == 1
    assert fiscal_quarter_for_calendar_month(1, cfg) == 4
    assert calendar_months_in_fiscal_quarter(1, cfg) == frozenset({4, 5, 6})
    q1, q2 = half_year_period_starts(2026, cfg)
    assert q1 == __import__("datetime").date(2026, 4, 1)
    assert q2 == __import__("datetime").date(2026, 7, 1)


@pytest.mark.parametrize(
    "header,expected",
    [
        ("January", 1),
        ("Jan", 1),
        ("Jan-26", 1),
        ("Jan 2026", 1),
        ("2026-01", 1),
        ("May (TBC)", 5),
        ("May\n(TBC)", 5),
    ],
)
def test_month_header_patterns(header: str, expected: int):
    assert parse_calendar_month_from_column(header) == expected


def test_first_instance_ignores_revenue_twin():
    uploaded = {"Jan": "36", "Jan2": "52416", "Apr": "36", "Qty": "36"}
    det = detect_month_columns(uploaded, column_order=list(uploaded.keys()), qty_cell_hint=36.0)
    assert det.month_values == {1: 36.0, 4: 36.0}
    assert "Jan2" in det.skipped_columns


def test_whole_number_guard_rejects_revenue_first_instance():
    uploaded = {"Jan2": "52416", "Apr": "36", "Qty": "36"}
    det = detect_month_columns(uploaded, column_order=["Jan2", "Apr"], qty_cell_hint=36.0)
    assert 1 not in det.month_values
    assert det.month_values.get(4) == 36.0


def test_whole_number_guard_rejects_non_integer():
    assert not is_plausible_unit_quantity(12.5)


def test_month_derived_evetech_row_q1_not_halved():
    line = SimpleNamespace(
        id=3055,
        quantity_units=18.0,
        msrp_local=1000.0,
        promo_price_evidence_local=None,
        dap_evidence_local=None,
        calc_dap_cost_currency=None,
        calc_profit_total=None,
        diagnostic_codes=[HALF_YEAR_ALLOCATION_FLAG],
        customer_token="Evetech",
        model_raw="UX3405CA-OU93210BL0X",
        part_number_raw="90NB14W3-M006H0",
        raw_row_payload={
            "uploaded": {"Qty": "36", "Jan": "36", "Apr": "36", "Jan2": "52416", "Apr2": "52416"},
        },
    )
    q1 = compute_line_half_year_allocation(line, half="q1")
    q2 = compute_line_half_year_allocation(line, half="q2")
    assert q1.tier == "month_derived"
    assert q1.quantity_units == 36.0
    assert q2.quantity_units == 36.0
    assert q1.month_total_units == 72.0
    assert q1.fiscal_q1_units + q2.fiscal_q2_units == 72.0
    assert QTY_MONTH_DISAGREEMENT_FLAG in q1.diagnostic_codes
    assert MONTH_DERIVED_ALLOCATION_FLAG in q1.diagnostic_codes


def test_month_derived_all_six_months_split():
    line = SimpleNamespace(
        id=1,
        quantity_units=90.0,
        msrp_local=600.0,
        promo_price_evidence_local=None,
        dap_evidence_local=None,
        calc_dap_cost_currency=None,
        calc_profit_total=None,
        diagnostic_codes=[],
        raw_row_payload={
            "uploaded": {
                "Qty": "90",
                "Feb": "10",
                "Mar": "20",
                "Apr": "30",
                "May": "15",
                "Jun": "15",
            },
        },
    )
    q1 = compute_line_half_year_allocation(line, half="q1")
    q2 = compute_line_half_year_allocation(line, half="q2")
    assert q1.quantity_units == 30.0
    assert q2.quantity_units == 60.0
    assert q1.monetary["msrp_local"] == pytest.approx(200.0)
    assert q2.monetary["msrp_local"] == pytest.approx(400.0)


def test_uniform_half_fallback_when_no_months():
    line = SimpleNamespace(
        id=2,
        quantity_units=10.0,
        msrp_local=100.0,
        promo_price_evidence_local=None,
        dap_evidence_local=None,
        calc_dap_cost_currency=None,
        calc_profit_total=None,
        diagnostic_codes=[],
        raw_row_payload={"uploaded": {"Qty": "10"}},
    )
    q1 = compute_line_half_year_allocation(line, half="q1")
    q2 = compute_line_half_year_allocation(line, half="q2")
    assert q1.tier == "uniform_half"
    assert q1.quantity_units == 5.0
    assert q2.quantity_units == 5.0
    assert q1.quantity_units + q2.quantity_units == 10.0


def test_no_disagreement_flag_when_qty_equals_month_total():
    line = SimpleNamespace(
        id=3,
        quantity_units=30.0,
        msrp_local=None,
        promo_price_evidence_local=None,
        dap_evidence_local=None,
        calc_dap_cost_currency=None,
        calc_profit_total=None,
        diagnostic_codes=[],
        raw_row_payload={"uploaded": {"Qty": "30", "Jan": "10", "Feb": "10", "Mar": "10"}},
    )
    q1 = compute_line_half_year_allocation(line, half="q1")
    assert q1.tier == "month_derived"
    assert QTY_MONTH_DISAGREEMENT_FLAG not in q1.diagnostic_codes


def test_apply_path_preserves_month_derived_quantity_after_snapshot():
    """Regression: monetary proportional split must not overwrite quantity_units on apply."""
    line = SimpleNamespace(
        id=3055,
        quantity_units=18.0,
        msrp_local=1000.0,
        promo_price_evidence_local=None,
        dap_evidence_local=None,
        calc_dap_cost_currency=None,
        calc_profit_total=None,
        diagnostic_codes=[HALF_YEAR_ALLOCATION_FLAG],
        customer_token="Evetech",
        model_raw="UX3405CA-OU93210BL0X",
        part_number_raw="90NB14W3-M006H0",
        raw_row_payload={
            "uploaded": {"Qty": "36", "Jan": "36", "Apr": "36"},
        },
    )
    _snapshot_line_sources(line)
    allocation = compute_line_half_year_allocation(line, half="q1")
    _apply_allocation_to_line(line, allocation)
    assert line.quantity_units == 36.0
