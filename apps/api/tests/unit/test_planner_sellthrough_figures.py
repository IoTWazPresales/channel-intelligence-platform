"""Promotion planner figures come from customer sell-through only (Warren 2026-11-19).

Pure-function proofs for ``app.services.cpor.planner_sellthrough``: price, cost, stock, run rate
and cover are derived from sell-through rows (units sold, ``unit_sell_price``, ``unit_cost``,
``unit_mac``, ``reported_soh``) and nothing else. A missing figure is returned as ``None`` with a
reason, never a zero. No database. Nothing here names a customer, retailer, site or product.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from app.services.cpor import planner_sellthrough as st

WEEK0 = date(2026, 1, 5)


def _wk(i: int) -> date:
    return WEEK0 + timedelta(weeks=i)


def _weeks(units: list[float]) -> list[tuple]:
    """Chain-grain weekly rows: (period, grain, kind, units, soh, site)."""
    return [(_wk(i), "week", "week", u, None, None) for i, u in enumerate(units)]


# --- configurable window -------------------------------------------------------------------


def test_run_rate_window_defaults_to_eight_weeks(monkeypatch):
    monkeypatch.delenv(st.RUN_RATE_WEEKS_ENV, raising=False)
    assert st.DEFAULT_RUN_RATE_WEEKS == 8
    assert st.run_rate_weeks() == 8


def test_run_rate_window_is_read_from_configuration(monkeypatch):
    monkeypatch.setenv(st.RUN_RATE_WEEKS_ENV, "12")
    assert st.run_rate_weeks() == 12


@pytest.mark.parametrize("raw,expected", [("0", 1), ("-3", 1), ("999", 52), ("abc", 8)])
def test_run_rate_window_is_bounded(monkeypatch, raw, expected):
    monkeypatch.setenv(st.RUN_RATE_WEEKS_ENV, raw)
    assert st.run_rate_weeks() == expected


# --- run rate -----------------------------------------------------------------------------


def test_run_rate_is_the_mean_of_the_most_recent_reported_weeks():
    rows = _weeks([100.0] * 4 + [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0])
    fig = st.figures_from_rows(rows, None, None, window_weeks=8)
    assert fig["weekly_rate"] == pytest.approx(45.0)
    assert fig["weeks_used"] == 8
    assert fig["window_weeks"] == 8
    assert fig["units_reason"] is None


def test_run_rate_uses_fewer_weeks_when_fewer_were_reported():
    fig = st.figures_from_rows(_weeks([10.0, 30.0]), None, None, window_weeks=8)
    assert fig["weekly_rate"] == pytest.approx(20.0)
    assert fig["weeks_used"] == 2


def test_run_rate_sums_site_rows_inside_one_week():
    rows = [
        (_wk(0), "week", "week", 4.0, None, "A"),
        (_wk(0), "week", "week", 6.0, None, "B"),
        (_wk(1), "week", "week", 10.0, None, "A"),
    ]
    fig = st.figures_from_rows(rows, None, None, window_weeks=8)
    assert fig["weekly_rate"] == pytest.approx(10.0)


def test_chain_rows_are_not_added_on_top_of_site_rows():
    rows = [
        (_wk(0), "week", "week", 100.0, None, None),  # collapsed chain grain
        (_wk(0), "week", "week", 4.0, None, "A"),
        (_wk(0), "week", "week", 6.0, None, "B"),
    ]
    fig = st.figures_from_rows(rows, None, None, window_weeks=8)
    assert fig["weekly_rate"] == pytest.approx(10.0)


def test_monthly_rows_do_not_make_a_weekly_run_rate():
    rows = [(date(2026, 1, 1), "month", "month", 500.0, None, None)]
    fig = st.figures_from_rows(rows, None, None, window_weeks=8)
    assert fig["weekly_rate"] is None
    assert fig["units_reason"] == st.NO_WEEKLY


def test_no_rows_is_missing_with_a_reason_not_zero():
    fig = st.figures_from_rows([], None, None, window_weeks=8)
    for key in ("weekly_rate", "price", "cost", "soh_units", "cover_weeks"):
        assert fig[key] is None
    assert fig["units_reason"] == st.NO_SELLTHROUGH
    assert fig["price_reason"] == st.NO_SELLTHROUGH
    assert fig["cost_reason"] == st.NO_SELLTHROUGH
    assert fig["soh_reason"] == st.NO_SELLTHROUGH


# --- stock and cover ---------------------------------------------------------------------


def test_stock_is_the_latest_reported_soh_and_cover_is_soh_over_run_rate():
    rows = [
        (_wk(0), "week", "week", 10.0, 500.0, None),
        (_wk(1), "week", "week", 10.0, 80.0, None),
    ]
    fig = st.figures_from_rows(rows, None, None, window_weeks=8)
    assert fig["soh_units"] == pytest.approx(80.0)
    assert fig["weekly_rate"] == pytest.approx(10.0)
    assert fig["cover_weeks"] == pytest.approx(8.0)


def test_each_sites_latest_stock_counts_once():
    rows = [
        (_wk(0), "week", "week", 1.0, 50.0, "A"),
        (_wk(1), "week", "week", 1.0, 20.0, "A"),
        (_wk(1), "week", "week", 1.0, 30.0, "B"),
    ]
    fig = st.figures_from_rows(rows, None, None, window_weeks=8)
    assert fig["soh_units"] == pytest.approx(50.0)


def test_cover_is_missing_with_a_reason_when_the_run_rate_is_zero():
    rows = [(_wk(0), "week", "week", 0.0, 40.0, None), (_wk(1), "week", "week", 0.0, 40.0, None)]
    fig = st.figures_from_rows(rows, None, None, window_weeks=8)
    assert fig["weekly_rate"] == 0.0
    assert fig["cover_weeks"] is None
    assert fig["cover_reason"] == st.NO_RATE


def test_stock_is_missing_when_no_row_reports_it():
    fig = st.figures_from_rows(_weeks([5.0, 5.0]), None, None, window_weeks=8)
    assert fig["soh_units"] is None
    assert fig["soh_reason"] == st.NO_SOH
    assert fig["cover_weeks"] is None


# --- price and cost ----------------------------------------------------------------------


def test_price_is_the_latest_reported_positive_unit_sell_price():
    fig = st.figures_from_rows([], (_wk(5), 249.0), None, window_weeks=8)
    assert fig["price"] == pytest.approx(249.0)
    assert fig["price_as_of"] == _wk(5).isoformat()
    assert fig["price_reason"] is None


def test_non_positive_price_is_missing():
    fig = st.figures_from_rows([], (_wk(5), 0.0), None, window_weeks=8)
    assert fig["price"] is None
    assert fig["price_reason"] == st.NO_PRICE


def test_cost_prefers_unit_mac_over_unit_cost():
    fig = st.figures_from_rows([], None, (_wk(3), 80.0, 90.0), window_weeks=8)
    assert fig["cost"] == pytest.approx(80.0)
    assert fig["cost_field"] == "unit_mac"
    assert fig["cost_as_of"] == _wk(3).isoformat()


def test_cost_falls_back_to_unit_cost_when_mac_is_missing_or_not_positive():
    for mac in (None, 0.0):
        fig = st.figures_from_rows([], None, (_wk(3), mac, 90.0), window_weeks=8)
        assert fig["cost"] == pytest.approx(90.0)
        assert fig["cost_field"] == "unit_cost"


def test_cost_missing_when_neither_is_positive():
    fig = st.figures_from_rows([], None, (_wk(3), None, None), window_weeks=8)
    assert fig["cost"] is None
    assert fig["cost_reason"] == st.NO_COST


# --- volume -------------------------------------------------------------------------------


def test_volume_is_run_rate_times_horizon():
    fig = st.figures_from_rows(_weeks([10.0, 20.0]), None, None, window_weeks=8)
    vol = st.volume_from_figures(fig, horizon_weeks=13, as_of=date(2026, 3, 2))
    assert vol["forecast_units"] == pytest.approx(15.0 * 13)
    assert vol["weekly_run_rate"] == pytest.approx(15.0)
    assert vol["source"] == st.VOLUME_SOURCE
    assert vol["available"] is True
    assert vol["horizon_weeks"] == 13
    assert vol["period_from"] == "2026-03-02"
    assert vol["period_to"] == "2026-06-01"


def test_volume_is_missing_not_zero_without_sellthrough():
    fig = st.figures_from_rows([], None, None, window_weeks=8)
    vol = st.volume_from_figures(fig, horizon_weeks=13, as_of=date(2026, 3, 2))
    assert vol["forecast_units"] is None
    assert vol["available"] is False
    assert vol["reason"] == st.NO_SELLTHROUGH


def test_a_real_zero_run_rate_is_a_zero_volume_that_is_available():
    rows = [(_wk(0), "week", "week", 0.0, None, None)]
    fig = st.figures_from_rows(rows, None, None, window_weeks=8)
    vol = st.volume_from_figures(fig, horizon_weeks=13, as_of=date(2026, 3, 2))
    assert vol["forecast_units"] == 0.0
    assert vol["available"] is True


def test_srp_is_vat_inclusive_and_never_guesses_a_rate_opus_r04():
    assert st.srp_from_price(100.0, "inc_vat", None) == (100.0, None)
    assert st.srp_from_price(100.0, "ex_vat", 0.15) == (pytest.approx(115.0), None)
    assert st.srp_from_price(100.0, "ex_vat", None) == (None, st.VAT_RATE_UNSET)
    assert st.srp_from_price(100.0, None, 0.15) == (None, st.PRICE_VAT_UNKNOWN)
    assert st.srp_from_price(100.0, "gross?", 0.15) == (None, st.PRICE_VAT_UNKNOWN)
    assert st.srp_from_price(None, "ex_vat", 0.15) == (None, None)
    fig = st.figures_from_rows(
        [], (date(2026, 3, 2), 200.0, "ex_vat"), None, window_weeks=8, vat_rate=0.16
    )
    assert fig["price"] == 200.0 and fig["price_vat_basis"] == "ex_vat"
    assert fig["srp"] == pytest.approx(232.0) and fig["srp_reason"] is None
    unset = st.figures_from_rows([], (date(2026, 3, 2), 200.0, "ex_vat"), None, window_weeks=8)
    assert unset["srp"] is None and unset["srp_reason"] == st.VAT_RATE_UNSET
    none = st.figures_from_rows([], None, None, window_weeks=8, vat_rate=0.15)
    assert none["srp"] is None and none["srp_reason"] == none["price_reason"]