"""Unit tests for lineup period + product-line inference."""

from datetime import date

from app.services.commercial_planner.lineup_period_inference import (
    CANONICAL_PRODUCT_LINES,
    detect_quarter_from_columns,
    infer_case_product_line,
    infer_period_start,
    infer_product_line,
    infer_product_line_from_catalogue_values,
    infer_product_line_from_filename,
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


def test_product_line_majority_value_legacy_sheet_helper():
    """infer_product_line (sheet column) remains for legacy callers — parser no longer uses it."""
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
    assert infer_product_line_from_catalogue_values(["Gaming", "Gaming", "NB"]) == "Gaming"


def test_catalogue_primary_even_when_filename_suggests_consumer():
    """Gaming NR file: resolved catalogue rows are Gaming — must not infer Consumer from sheet/filename."""
    resolved = ["Gaming"] * 10
    assert (
        infer_case_product_line(
            filename="ACZA_Consumer_NR_Q2.xlsx",
            total_rows=10,
            resolved_product_lines=resolved,
        )
        == "Gaming"
    )


def test_filename_fallback_when_under_resolved():
    assert (
        infer_case_product_line(
            filename="Gaming_NR_Q2.xlsx",
            total_rows=20,
            resolved_product_lines=["Gaming"],
        )
        == "Gaming"
    )


def test_filename_fallback_nv_ally():
    assert infer_product_line_from_filename("NV_Ally_lineup.xlsx") == "NV"


def test_filename_fallback_consumer_and_nb():
    assert infer_product_line_from_filename("consumer_26Q2.xlsx") == "Consumer"
    assert infer_product_line_from_filename("NB_refresh.xlsx") == "NB"


def test_canonical_product_line_labels():
    assert CANONICAL_PRODUCT_LINES == frozenset({"Gaming", "Consumer", "NV", "NB"})


def test_case_inference_ignores_sheet_category_mislabel_scenario():
    """Catalogue majority Gaming wins; misleading category column would have said Consumer."""
    gaming_rows = ["Gaming"] * 8 + ["Gaming"]  # 9/10 resolved
    assert (
        infer_case_product_line(
            filename="misleading_consumer_category.xlsx",
            total_rows=10,
            resolved_product_lines=gaming_rows,
        )
        == "Gaming"
    )
