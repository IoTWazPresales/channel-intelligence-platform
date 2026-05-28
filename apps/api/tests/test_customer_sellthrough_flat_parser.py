"""Customer sell-through flat parser (synthetic fixtures, no DB)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.services.imports.parsers.customer_sell_through_flat import (
    EXPECTED_COLUMNS_META_KEY,
    parse_flat_report,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "customer_reports"

DEFAULT_EXPECTED = {
    "units_sold": {
        "aliases": ["units_sold", "qty_sold", "quantity_sold", "tw_sales", "tw sales", "sales", "units", "qty"],
        "required": True,
    },
    "raw_product_token": {
        "aliases": [
            "product_code",
            "sku",
            "item_code",
            "itemno",
            "article",
            "barcode",
            "supplier_code",
        ],
        "required": True,
    },
    "raw_location_token": {
        "aliases": ["site_code", "site_name", "store_code", "store_name", "site"],
        "required": False,
    },
    "raw_period_ref": {
        "aliases": ["week", "transaction_week", "period", "report_week", "week_no"],
        "required": False,
    },
    "unit_sell_price": {
        "aliases": ["sell_price", "unit_price", "price", "selling_price", "retail_price"],
        "required": False,
    },
    "unit_cost": {
        "aliases": ["cost", "unit_cost", "mac", "moving_avg_cost", "cost_price"],
        "required": False,
    },
    "reported_soh": {
        "aliases": [
            "soh",
            "stock_on_hand",
            "in_stock",
            "qty_available",
            "current_stock",
            "on_hand",
            "total_soh",
            "total_sellable_soh",
        ],
        "required": False,
    },
}


def _mapping_for_standard() -> dict:
    return {
        "SKU": "raw_product_token",
        "Site Code": "raw_location_token",
        "TW Sales": "units_sold",
        "Sell Price": "unit_sell_price",
        "SOH": "reported_soh",
        "Week": "raw_period_ref",
        EXPECTED_COLUMNS_META_KEY: DEFAULT_EXPECTED,
    }


def test_header_detected_row_1_standard_file() -> None:
    data = (FIXTURES / "flat_standard.xlsx").read_bytes()
    result = parse_flat_report(data, "flat_standard.xlsx", _mapping_for_standard(), 1)
    assert result.error is None
    assert len(result.rows) == 5


def test_header_detected_when_offset_row_4() -> None:
    data = (FIXTURES / "flat_offset_header.xlsx").read_bytes()
    mapping = {
        "Item Code": "raw_product_token",
        "Store Code": "raw_location_token",
        "Qty Sold": "units_sold",
        "Cost": "unit_cost",
        "Report Week": "raw_period_ref",
        EXPECTED_COLUMNS_META_KEY: DEFAULT_EXPECTED,
    }
    result = parse_flat_report(data, "flat_offset_header.xlsx", mapping, 2)
    assert result.error is None
    assert len(result.rows) == 4
    assert result.rows[0]["source_row_number"] == 5


def test_units_sold_mapped_from_alias() -> None:
    data = (FIXTURES / "flat_standard.xlsx").read_bytes()
    result = parse_flat_report(data, "flat_standard.xlsx", _mapping_for_standard(), 1)
    assert result.rows[0]["units_sold"] == 10.0


def test_period_extracted_from_date_column() -> None:
    data = (FIXTURES / "flat_standard.xlsx").read_bytes()
    result = parse_flat_report(data, "flat_standard.xlsx", _mapping_for_standard(), 1)
    assert result.period_start_date == date(2026, 5, 11)


def test_period_extracted_from_filename_date_range() -> None:
    data = (FIXTURES / "flat_filename_period.xlsx").read_bytes()
    mapping = {
        "Product Code": "raw_product_token",
        "Units": "units_sold",
        "MAC": "unit_cost",
        EXPECTED_COLUMNS_META_KEY: DEFAULT_EXPECTED,
    }
    result = parse_flat_report(
        data,
        "sellthrough_20260501_20260514.xlsx",
        mapping,
        3,
    )
    assert result.period_start_date == date(2026, 5, 1)


def test_period_extracted_from_week_number_in_filename() -> None:
    data = (FIXTURES / "flat_filename_period.xlsx").read_bytes()
    mapping = {
        "Product Code": "raw_product_token",
        "Units": "units_sold",
        EXPECTED_COLUMNS_META_KEY: DEFAULT_EXPECTED,
    }
    result = parse_flat_report(data, "report_week_18_summary.xlsx", mapping, 4)
    assert result.period_start_date == date.fromisocalendar(date.today().year, 18, 1)


def test_period_none_and_warning_when_not_found() -> None:
    data = (FIXTURES / "flat_filename_period.xlsx").read_bytes()
    mapping = {
        "Product Code": "raw_product_token",
        "Units": "units_sold",
        EXPECTED_COLUMNS_META_KEY: DEFAULT_EXPECTED,
    }
    result = parse_flat_report(data, "no_period_hints.xlsx", mapping, 5)
    assert result.period_start_date is None
    assert any("Period could not be extracted" in w for w in result.warnings)


def test_formula_artifact_stripped_from_product_token() -> None:
    data = (FIXTURES / "flat_formula_artifacts.xlsx").read_bytes()
    mapping = {
        "Article": "raw_product_token",
        "Qty": "units_sold",
        EXPECTED_COLUMNS_META_KEY: DEFAULT_EXPECTED,
    }
    result = parse_flat_report(data, "flat_formula_artifacts.xlsx", mapping, 6)
    assert result.error is None
    tokens = [r["raw_product_token"] for r in result.rows]
    assert "PROD-FORMULA" in tokens
    assert "ABC" in tokens


def test_row_skipped_when_units_sold_missing() -> None:
    import io

    import pandas as pd

    bio = io.BytesIO()
    df = pd.DataFrame(
        [
            ["SKU", "Qty"],
            ["A", None],
            ["B", 5],
        ]
    )
    df.to_excel(bio, index=False, header=False)
    mapping = {"SKU": "raw_product_token", "Qty": "units_sold", EXPECTED_COLUMNS_META_KEY: DEFAULT_EXPECTED}
    result = parse_flat_report(bio.getvalue(), "t.xlsx", mapping, 7)
    assert len(result.rows) == 1
    assert result.rows[0]["raw_product_token"] == "B"


def test_row_skipped_when_product_token_missing() -> None:
    import io

    import pandas as pd

    bio = io.BytesIO()
    df = pd.DataFrame([["SKU", "Qty"], [None, 5], ["X", 3]])
    df.to_excel(bio, index=False, header=False)
    mapping = {"SKU": "raw_product_token", "Qty": "units_sold", EXPECTED_COLUMNS_META_KEY: DEFAULT_EXPECTED}
    result = parse_flat_report(bio.getvalue(), "t.xlsx", mapping, 8)
    assert len(result.rows) == 1
    assert result.rows[0]["raw_product_token"] == "X"


def test_missing_units_sold_column_returns_error_not_exception() -> None:
    import io

    import pandas as pd

    bio = io.BytesIO()
    # Two recognizable headers for detection; no column maps to units_sold.
    pd.DataFrame([["SKU", "Site"], ["A", "S1"]]).to_excel(bio, index=False, header=False)
    mapping = {"SKU": "raw_product_token", EXPECTED_COLUMNS_META_KEY: DEFAULT_EXPECTED}
    result = parse_flat_report(bio.getvalue(), "t.xlsx", mapping, 9)
    assert result.error is not None
    assert "units_sold" in result.error


def test_all_output_rows_contain_required_keys() -> None:
    data = (FIXTURES / "flat_standard.xlsx").read_bytes()
    result = parse_flat_report(data, "flat_standard.xlsx", _mapping_for_standard(), 10)
    required = {
        "import_job_id",
        "source_row_number",
        "raw_row_payload",
        "raw_customer_token",
        "raw_location_token",
        "raw_product_token",
        "raw_period_ref",
        "period_start_date",
        "period_type",
        "units_sold",
        "raw_mtd_units",
        "is_mtd_estimate",
        "unit_sell_price",
        "unit_cost",
        "reported_soh",
        "resolution_status",
    }
    for row in result.rows:
        assert set(row.keys()) == required


def test_raw_mtd_units_none_and_is_mtd_estimate_false() -> None:
    data = (FIXTURES / "flat_standard.xlsx").read_bytes()
    result = parse_flat_report(data, "flat_standard.xlsx", _mapping_for_standard(), 11)
    for row in result.rows:
        assert row["raw_mtd_units"] is None
        assert row["is_mtd_estimate"] is False
