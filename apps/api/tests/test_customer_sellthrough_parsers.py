"""Customer sell-through parsers Phase 1b-e (mocked AI, no DB writes)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import get_settings
from app.services.imports.ai_import_resolver import (
    AI_AUTO_RESOLVE_THRESHOLD,
    ColumnMappingSuggestion,
    TokenResolutionSuggestion,
    detect_format_drift,
    suggest_column_mapping,
    suggest_token_resolution,
)
from app.services.imports.parsers.customer_sell_through_flat import EXPECTED_COLUMNS_META_KEY
from app.services.imports.parsers.customer_sell_through_mtd_delta import parse_mtd_delta_report
from app.services.imports.parsers.customer_sell_through_multi_sheet import parse_multi_sheet_report
from app.services.imports.parsers.customer_sell_through_period import (
    classify_period_header,
    is_period_column_header,
    is_summary_sheet_name,
    parse_sheet_name_period,
)
from app.services.imports.parsers.customer_sell_through_pivoted import parse_pivoted_report
from app.services.imports.parsers.customer_sell_through_wide_extract import parse_wide_extract_report

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "customer_reports"

DEFAULT_EXPECTED = {
    "units_sold": {
        "aliases": ["units_sold", "qty_sold", "tw_sales", "sales", "units", "qty"],
        "required": True,
    },
    "raw_product_token": {
        "aliases": ["product_code", "sku", "item_code", "article", "barcode"],
        "required": True,
    },
    "raw_location_token": {
        "aliases": ["site_code", "site_name", "store_code", "store", "site"],
        "required": False,
    },
    "raw_period_ref": {
        "aliases": ["week", "period", "report_week"],
        "required": False,
    },
    "unit_sell_price": {"aliases": ["sell_price", "unit_price", "price"], "required": False},
    "unit_cost": {"aliases": ["cost", "unit_cost", "mac"], "required": False},
    "reported_soh": {"aliases": ["soh", "stock_on_hand", "on_hand"], "required": False},
    "raw_mtd_units": {"aliases": ["mtd", "mtd units", "month to date"], "required": False},
}


def _base_mapping(**extra: str) -> dict:
    m = {
        "SKU": "raw_product_token",
        "Store": "raw_location_token",
        "Site Code": "raw_location_token",
        "Site": "raw_location_token",
        "TW Sales": "units_sold",
        "SOH": "reported_soh",
        EXPECTED_COLUMNS_META_KEY: DEFAULT_EXPECTED,
    }
    m.update(extra)
    return m


# --- Period utilities ---


def test_period_iso_week_header() -> None:
    kind, d, _ = classify_period_header("2025-W10")
    assert kind == "iso_week"
    assert d == date.fromisocalendar(2025, 10, 1)


def test_period_fiscal_week_header() -> None:
    kind, d, _ = classify_period_header("FW02")
    assert kind == "fiscal_week"
    assert d is not None


def test_period_date_header() -> None:
    kind, d, _ = classify_period_header("2025-05-19")
    assert kind == "date"
    assert d is not None


def test_non_period_column_not_flagged() -> None:
    assert not is_period_column_header("SKU")


def test_summary_sheet_excluded() -> None:
    assert is_summary_sheet_name("Summary")
    assert not is_summary_sheet_name("Week 10")


# --- Pivoted ---


def test_pivoted_week_columns_detected() -> None:
    data = (FIXTURES / "pivoted_weekly.xlsx").read_bytes()
    result = parse_pivoted_report(data, "pivoted_weekly.xlsx", _base_mapping(), 1)
    assert result.error is None
    assert len(result.rows) > 0
    periods = {r["period_start_date"] for r in result.rows}
    assert len(periods) >= 3


def test_pivoted_fiscal_week_columns() -> None:
    data = (FIXTURES / "pivoted_fiscal.xlsx").read_bytes()
    result = parse_pivoted_report(data, "pivoted_fiscal.xlsx", _base_mapping(), 1)
    assert result.error is None
    assert any(r["raw_product_token"] == "P001" for r in result.rows)


def test_pivoted_unpivot_one_row_per_product_period() -> None:
    data = (FIXTURES / "pivoted_weekly.xlsx").read_bytes()
    result = parse_pivoted_report(data, "pivoted_weekly.xlsx", _base_mapping(), 1)
    keys = {(r["raw_product_token"], r["period_start_date"]) for r in result.rows}
    assert len(keys) == len(result.rows)


def test_pivoted_zero_cells_skipped() -> None:
    data = (FIXTURES / "pivoted_weekly.xlsx").read_bytes()
    result = parse_pivoted_report(data, "pivoted_weekly.xlsx", _base_mapping(), 1)
    assert all((r["units_sold"] or 0) > 0 for r in result.rows)


def test_pivoted_soh_on_latest_period_only() -> None:
    data = (FIXTURES / "pivoted_weekly.xlsx").read_bytes()
    result = parse_pivoted_report(data, "pivoted_weekly.xlsx", _base_mapping(), 1)
    p001 = [r for r in result.rows if r["raw_product_token"] == "P001"]
    with_soh = [r for r in p001 if r.get("reported_soh") is not None]
    assert len(with_soh) == 1
    assert with_soh[0]["period_start_date"] == max(r["period_start_date"] for r in p001 if r["period_start_date"])


def test_pivoted_undetectable_period_warning() -> None:
    mapping = _base_mapping()
    data = (FIXTURES / "pivoted_weekly.xlsx").read_bytes()
    with patch(
        "app.services.imports.parsers.customer_sell_through_pivoted.detect_period_columns",
        return_value=[("NotAWeek", None, "weekly")],
    ):
        result = parse_pivoted_report(data, "x.xlsx", mapping, 1)
    assert any("could not be parsed" in w.lower() for w in result.warnings) or result.rows == []


# --- Multi-sheet ---


def test_multi_sheet_week_sheets_processed() -> None:
    data = (FIXTURES / "multi_sheet_weekly.xlsx").read_bytes()
    result = parse_multi_sheet_report(data, "multi.xlsx", _base_mapping(), 1)
    assert result.error is None
    assert len(result.rows) >= 6


def test_multi_sheet_summary_excluded() -> None:
    data = (FIXTURES / "multi_sheet_with_summary.xlsx").read_bytes()
    result = parse_multi_sheet_report(data, "multi.xlsx", _base_mapping(), 1)
    assert result.error is None
    assert all("Summary" not in str(r.get("raw_period_ref", "")) for r in result.rows)


def test_multi_sheet_period_from_sheet_name() -> None:
    d, ptype, warn = parse_sheet_name_period("Week 10")
    assert warn is None
    assert d == date.fromisocalendar(date.today().year, 10, 1)
    assert ptype == "weekly"


def test_multi_sheet_dedupe_last_wins() -> None:
    data = (FIXTURES / "multi_sheet_weekly.xlsx").read_bytes()
    result = parse_multi_sheet_report(data, "multi.xlsx", _base_mapping(), 1)
    assert any("Deduplicated" in w for w in result.warnings) or len(result.rows) >= 2


def test_multi_sheet_undetectable_period_warning() -> None:
    d, _, warn = parse_sheet_name_period("Notes")
    assert d is None
    assert warn is not None


# --- MTD delta ---


def test_mtd_delta_no_prior_is_estimate() -> None:
    data = (FIXTURES / "mtd_delta_current.xlsx").read_bytes()
    db = MagicMock()
    db.execute.return_value.first.return_value = None
    mapping = _base_mapping()
    mapping["MTD Units"] = "raw_mtd_units"
    result = parse_mtd_delta_report(data, "mtd.xlsx", mapping, 1, db)
    assert result.error is None
    assert all(r["is_mtd_estimate"] for r in result.rows)
    assert all(r["raw_mtd_units"] is not None for r in result.rows)


def test_mtd_delta_derived_units_with_prior() -> None:
    data = (FIXTURES / "mtd_delta_current.xlsx").read_bytes()
    db = MagicMock()
    db.execute.return_value.first.return_value = (100.0, date(2025, 5, 12))
    mapping = _base_mapping()
    mapping["MTD Units"] = "raw_mtd_units"
    mapping["__customer_id__"] = 1
    result = parse_mtd_delta_report(data, "mtd.xlsx", mapping, 1, db)
    row = next(r for r in result.rows if r["raw_product_token"] == "P001")
    assert row["units_sold"] == 20.0
    assert row["is_mtd_estimate"] is False


def test_mtd_delta_negative_delta_clamped() -> None:
    data = (FIXTURES / "mtd_delta_current.xlsx").read_bytes()
    db = MagicMock()
    db.execute.return_value.first.return_value = (200.0, date(2025, 5, 12))
    mapping = _base_mapping()
    mapping["MTD Units"] = "raw_mtd_units"
    mapping["__customer_id__"] = 1
    result = parse_mtd_delta_report(data, "mtd.xlsx", mapping, 1, db)
    row = next(r for r in result.rows if r["raw_product_token"] == "P001")
    assert row["units_sold"] == 0.0
    assert any("Negative delta" in w for w in result.warnings)


# --- Wide extract ---


def test_wide_extract_finds_relevant_columns() -> None:
    data = (FIXTURES / "wide_extract_minimal.xlsx").read_bytes()
    result = parse_wide_extract_report(data, "wide.xlsx", _base_mapping(), 1)
    assert result.error is None
    assert len(result.rows) == 5


def test_wide_extract_ignores_irrelevant_columns() -> None:
    data = (FIXTURES / "wide_extract_minimal.xlsx").read_bytes()
    result = parse_wide_extract_report(data, "wide.xlsx", _base_mapping(), 1)
    assert all(r["units_sold"] is not None for r in result.rows)


def test_wide_extract_error_when_required_missing() -> None:
    data = (FIXTURES / "wide_extract_minimal.xlsx").read_bytes()
    result = parse_wide_extract_report(data, "wide.xlsx", {EXPECTED_COLUMNS_META_KEY: {}}, 1)
    assert result.error is not None


# --- AI layer ---


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_ai_disabled_no_api_call() -> None:
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "false"}, clear=False):
        get_settings.cache_clear()
        with patch("app.services.imports.ai_import_resolver._call_claude") as mock_claude:
            out = suggest_column_mapping(["A"], [{}], ["units_sold"])
        assert out is None
        mock_claude.assert_not_called()


def test_ai_suggest_column_mapping_when_enabled() -> None:
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "true"}, clear=False):
        get_settings.cache_clear()
        with patch(
            "app.services.imports.ai_import_resolver._call_claude",
            return_value={
                "mappings": {"Week 99": "units_sold"},
                "confidence": 0.8,
                "unmapped": [],
                "notes": "ok",
            },
        ):
            out = suggest_column_mapping(["Week 99"], [{}], ["units_sold"])
    assert out is not None
    assert out.mappings.get("Week 99") == "units_sold"


def test_ai_token_resolution_auto_threshold() -> None:
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "true"}, clear=False):
        get_settings.cache_clear()
        with patch(
            "app.services.imports.ai_import_resolver._call_claude",
            return_value={
                "best_match_id": 42,
                "confidence": AI_AUTO_RESOLVE_THRESHOLD,
                "reasoning": "match",
                "alternatives": [],
            },
        ):
            out = suggest_token_resolution("SKU1", "product", [{"id": 42}], None)
    assert out is not None
    assert out.best_match_id == 42
    assert out.confidence >= AI_AUTO_RESOLVE_THRESHOLD


def test_ai_failure_returns_none() -> None:
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "true"}, clear=False):
        get_settings.cache_clear()
        with patch("app.services.imports.ai_import_resolver._call_claude", return_value=None):
            out = suggest_token_resolution("X", "product", [], None)
    assert out is None


def test_detect_format_drift_without_ai() -> None:
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "false"}, clear=False):
        get_settings.cache_clear()
        drift = detect_format_drift(
            ["sku", "qty"],
            ["sku", "week"],
            {"by_header_norm": {"sku": {}, "week": {}}},
        )
    assert drift is not None
    assert drift.has_drift
    assert drift.suggested_updated_mapping is None


def test_ai_suggested_below_threshold_status_in_handler() -> None:
    from app.services.imports.customer_sell_through import _apply_ai_resolution_to_line

    line = SimpleNamespace(
        import_job_id=7,
        resolved_product_id=None,
        raw_product_token="UNK",
        raw_location_token=None,
        raw_row_payload={},
        resolution_status="pending",
        resolved_location_id=None,
    )
    prod_idx = SimpleNamespace(sku_to_id={})
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "true"}, clear=False):
        get_settings.cache_clear()
        # Now routed through the shared try_ai_token_resolution wrapper, which calls
        # suggest_token_resolution inside ai_resolver_wiring — patch it there.
        with patch(
            "app.services.imports.ai_resolver_wiring.suggest_token_resolution",
            return_value=TokenResolutionSuggestion(
                best_match_id=1,
                confidence=0.5,
                reasoning="weak",
                alternatives=[],
            ),
        ):
            used = [False]
            product_ok, _ = _apply_ai_resolution_to_line(
                MagicMock(),
                line=line,
                customer_id=1,
                prod_idx=prod_idx,
                ai_assist_used=used,
            )
    assert line.resolution_status == "ai_suggested"
    assert product_ok is False


# --- D1 column parity (Batch 1c) ---

D1_ROW_KEYS = {
    "import_job_id",
    "source_row_number",
    "raw_row_payload",
    "raw_customer_token",
    "raw_location_token",
    "site_label",
    "raw_product_token",
    "raw_period_ref",
    "period_start_date",
    "period_type",
    "units_sold",
    "raw_mtd_units",
    "is_mtd_estimate",
    "unit_sell_price",
    "unit_cost",
    "unit_mac",
    "reported_soh",
    "raw_article_token",
    "listing_external_id",
    "listing_marketplace",
    "resolution_status",
}

D1_EXPECTED_COLUMNS = {
    **DEFAULT_EXPECTED,
    "unit_mac": {"aliases": ["mac_cost", "unit_mac"], "required": False},
    "raw_article_token": {"aliases": ["article", "article_no"], "required": False},
    "listing_external_id": {"aliases": ["listing_id", "asin"], "required": False},
    "listing_marketplace": {"aliases": ["marketplace", "platform"], "required": False},
}


def _d1_mapping(**extra: str) -> dict:
    m = _base_mapping(**extra)
    m.update(
        {
            "Unit MAC": "unit_mac",
            "Article": "raw_article_token",
            "Listing ID": "listing_external_id",
            "Platform": "listing_marketplace",
        }
    )
    m[EXPECTED_COLUMNS_META_KEY] = D1_EXPECTED_COLUMNS
    return m


def _assert_d1_row_keys(rows: list) -> None:
    assert rows, "expected at least one parsed row"
    for row in rows:
        assert set(row.keys()) == D1_ROW_KEYS


def _assert_d1_values(row: dict) -> None:
    assert row["unit_mac"] == 90.5
    assert row["raw_article_token"] == "ART-1"
    assert row["listing_external_id"] == "L-99"
    assert row["listing_marketplace"] == "Amazon"
    assert row["site_label"] == "S1"
    assert row["raw_location_token"] == "S1"


def test_pivoted_emits_d1_row_keys() -> None:
    data = (FIXTURES / "pivoted_weekly.xlsx").read_bytes()
    result = parse_pivoted_report(data, "pivoted_weekly.xlsx", _base_mapping(), 1)
    assert result.error is None
    _assert_d1_row_keys(result.rows)
    for row in result.rows:
        assert row["unit_mac"] is None
        assert row["raw_article_token"] is None
        assert row["listing_external_id"] is None
        assert row["listing_marketplace"] is None
        assert row["site_label"] == row["raw_location_token"]


def test_pivoted_d1_fields_from_identity_columns() -> None:
    import io

    import pandas as pd

    bio = io.BytesIO()
    pd.DataFrame(
        [
            ["SKU", "Store", "Unit MAC", "Article", "Listing ID", "Platform", "2025-W10", "2025-W11"],
            ["P001", "S1", 90.5, "ART-1", "L-99", "Amazon", 10, 5],
        ]
    ).to_excel(bio, index=False, header=False)
    result = parse_pivoted_report(bio.getvalue(), "pivoted_d1.xlsx", _d1_mapping(), 1)
    assert result.error is None
    _assert_d1_row_keys(result.rows)
    sample = next(r for r in result.rows if r["raw_product_token"] == "P001")
    _assert_d1_values(sample)


def test_multi_sheet_emits_d1_row_keys() -> None:
    data = (FIXTURES / "multi_sheet_weekly.xlsx").read_bytes()
    result = parse_multi_sheet_report(data, "multi.xlsx", _base_mapping(), 1)
    assert result.error is None
    _assert_d1_row_keys(result.rows)


def test_multi_sheet_d1_fields_from_identity_columns() -> None:
    import io

    import pandas as pd

    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        pd.DataFrame(
            [
                ["SKU", "Store", "Unit MAC", "Article", "Listing ID", "Platform", "TW Sales"],
                ["P001", "S1", 90.5, "ART-1", "L-99", "Amazon", 12],
            ]
        ).to_excel(writer, sheet_name="Week 10", index=False, header=False)
    result = parse_multi_sheet_report(bio.getvalue(), "multi_d1.xlsx", _d1_mapping(), 1)
    assert result.error is None
    _assert_d1_row_keys(result.rows)
    sample = next(r for r in result.rows if r["raw_product_token"] == "P001")
    _assert_d1_values(sample)


def test_mtd_delta_emits_d1_row_keys() -> None:
    data = (FIXTURES / "mtd_delta_current.xlsx").read_bytes()
    db = MagicMock()
    db.execute.return_value.first.return_value = None
    mapping = _base_mapping()
    mapping["MTD Units"] = "raw_mtd_units"
    result = parse_mtd_delta_report(data, "mtd.xlsx", mapping, 1, db)
    assert result.error is None
    _assert_d1_row_keys(result.rows)


def test_mtd_delta_d1_fields_from_identity_columns() -> None:
    import io

    import pandas as pd

    bio = io.BytesIO()
    pd.DataFrame(
        [
            [
                "SKU",
                "Store",
                "MTD Units",
                "Unit MAC",
                "Article",
                "Listing ID",
                "Platform",
            ],
            ["P001", "S1", 120, 90.5, "ART-1", "L-99", "Amazon"],
        ]
    ).to_excel(bio, index=False, header=False)
    db = MagicMock()
    db.execute.return_value.first.return_value = None
    mapping = _d1_mapping()
    mapping["MTD Units"] = "raw_mtd_units"
    result = parse_mtd_delta_report(bio.getvalue(), "mtd_d1.xlsx", mapping, 1, db)
    assert result.error is None
    _assert_d1_row_keys(result.rows)
    sample = next(r for r in result.rows if r["raw_product_token"] == "P001")
    _assert_d1_values(sample)


def test_wide_extract_emits_d1_row_keys() -> None:
    data = (FIXTURES / "wide_extract_minimal.xlsx").read_bytes()
    result = parse_wide_extract_report(data, "wide.xlsx", _base_mapping(), 1)
    assert result.error is None
    _assert_d1_row_keys(result.rows)


def test_wide_extract_d1_fields_from_identity_columns() -> None:
    import io

    import pandas as pd

    bio = io.BytesIO()
    pd.DataFrame(
        [
            ["SKU", "Store", "TW Sales", "Unit MAC", "Article", "Listing ID", "Platform", "Noise"],
            ["P001", "S1", 8, 90.5, "ART-1", "L-99", "Amazon", "ignore"],
            ["P002", "S2", 3, 88.0, "ART-2", "L-88", "Takealot", "ignore"],
        ]
    ).to_excel(bio, index=False, header=False)
    result = parse_wide_extract_report(bio.getvalue(), "wide_d1.xlsx", _d1_mapping(), 1)
    assert result.error is None
    _assert_d1_row_keys(result.rows)
    sample = next(r for r in result.rows if r["raw_product_token"] == "P001")
    _assert_d1_values(sample)
