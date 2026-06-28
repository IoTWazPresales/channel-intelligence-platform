"""Unit tests for lineup period + product-line inference."""

from datetime import date

from app.services.commercial_planner.lineup_period_inference import (
    detect_quarter_from_columns,
    infer_period_start,
    infer_product_line,
)


def test_label_with_quarter_and_two_digit_year():
    start, flags = infer_period_start("26Q1", ["SKU", "Qty"])
    assert start == date(2026, 1, 1)
    assert flags == []


def test_label_year_plus_month_columns_infer_q2():
    start, flags = infer_period_start("2026", ["SKU", "Apr", "May", "Jun"])
    assert start == date(2026, 4, 1)
    assert flags == []


def test_month_columns_span_quarters_is_ambiguous():
    assert detect_quarter_from_columns(["Mar", "Apr"]) is None


def test_label_quarter_beats_columns_with_mismatch_flag():
    start, flags = infer_period_start("2026 Q1", ["Jul", "Aug", "Sep"])
    assert start == date(2026, 1, 1)
    assert "period_quarter_mismatch" in flags


def test_year_without_quarter_defaults_to_jan_with_flag():
    start, flags = infer_period_start("FY2026", ["SKU", "Qty"])
    assert start == date(2026, 1, 1)
    assert "period_quarter_unknown" in flags


def test_no_year_returns_none():
    start, flags = infer_period_start("Q1", ["Jan", "Feb", "Mar"])
    assert start is None
    assert "period_year_unknown" in flags


def test_explicit_month_label():
    start, flags = infer_period_start("Jan 2026", ["SKU"])
    assert start == date(2026, 1, 1)


def test_product_line_majority_value():
    cols = ["SKU", "Product Line", "Qty"]
    rows = [
        {"SKU": "A", "Product Line": "Notebook", "Qty": "10"},
        {"SKU": "B", "Product Line": "Notebook", "Qty": "5"},
        {"SKU": "C", "Product Line": "Desktop", "Qty": "2"},
    ]
    assert infer_product_line(cols, rows) == "Notebook"


def test_product_line_absent_column_returns_none():
    cols = ["SKU", "Qty"]
    rows = [{"SKU": "A", "Qty": "10"}]
    assert infer_product_line(cols, rows) is None


def test_product_line_from_catalogue_majority_product_line():
    from app.services.commercial_planner.lineup_period_inference import (
        infer_product_line_from_catalogue_values,
    )

    assert infer_product_line_from_catalogue_values(
        ["Gaming", "Gaming", "NB"],
        [None, None, None],
    ) == "Gaming"


def test_product_line_from_catalogue_falls_back_to_business_unit():
    from app.services.commercial_planner.lineup_period_inference import (
        infer_product_line_from_catalogue_values,
    )

    assert infer_product_line_from_catalogue_values(
        [None, None],
        ["NB", "NB", "Gaming"],
    ) == "NB"
