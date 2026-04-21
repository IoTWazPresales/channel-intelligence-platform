"""Commercial-style Product Master mapper: layers, restraint, memory, disposition hints."""

from unittest.mock import MagicMock

import pandas as pd

from app.services.imports.pm_mapping_memory import merge_memory_from_pm_save, norm_header_key
from app.services.imports.product_master_workflow import suggest_mapping_decisions


def test_global_synonym_maps_mpn_without_vendor_headers() -> None:
    """Generic synonym dictionary — not vendor-specific."""
    source = MagicMock(import_template=MagicMock(expected_columns={}))
    headers = ["mpn", "commercial_sku", "widget_title"]
    inf = {
        "columns": [
            {"name": "mpn", "dtype": "object", "sample": ["ABC-1"]},
            {"name": "commercial_sku", "dtype": "object", "sample": ["MKT-99"]},
            {"name": "widget_title", "dtype": "object", "sample": ["SuperBook 14"]},
        ]
    }
    out = suggest_mapping_decisions(headers, source, inf)
    assert out["mpn"]["mapper_action"] == "auto_map"
    assert out["mpn"]["target"] == "technical_product_id"
    assert out["commercial_sku"]["target"] == "market_sku"


def test_source_memory_boosts_repeated_column() -> None:
    """Learned mapping is scoped to source memory."""
    # Plain object — MagicMock makes getattr(column_mapping_memory) a MagicMock unless every attr is set.
    class _Tpl:
        expected_columns: dict = {}

    class _Src:
        pass

    source = _Src()
    source.import_template = _Tpl()
    source.expected_template = None
    source.column_mapping_memory = {
        "by_header_norm": {
            "partner_line_code": {"target": "source_product_code", "confirmations": 4},
        }
    }
    headers = ["partner_line_code", "sku", "name_col"]
    inf = {
        "columns": [
            {"name": "partner_line_code", "dtype": "object", "sample": ["Z9"]},
            {"name": "sku", "dtype": "object", "sample": ["S1"]},
            {"name": "name_col", "dtype": "object", "sample": ["Widget"]},
        ]
    }
    out = suggest_mapping_decisions(headers, source, inf)
    assert out["partner_line_code"].get("from_source_memory") is True
    assert out["partner_line_code"].get("target") == "source_product_code"


def test_noise_column_recommends_ignore() -> None:
    source = MagicMock(import_template=MagicMock(expected_columns={}))
    headers = ["sku", "name", "x"]
    inf = {
        "columns": [
            {"name": "sku", "dtype": "object", "sample": ["A"]},
            {"name": "name", "dtype": "object", "sample": ["N"]},
            {"name": "x", "dtype": "object", "sample": [""]},
        ]
    }
    out = suggest_mapping_decisions(headers, source, inf)
    assert out["x"]["mapper_action"] == "recommend_ignore"


def test_deterministic_barcode_gtin_header_auto_maps() -> None:
    """13-digit GTIN/EAN semantics — not vendor-specific."""
    source = MagicMock(import_template=MagicMock(expected_columns={}))
    headers = ["gtin_13", "commercial_sku"]
    inf = {
        "columns": [
            {"name": "gtin_13", "dtype": "object", "sample": ["5901234123457"]},
            {"name": "commercial_sku", "dtype": "object", "sample": ["SKU-1"]},
        ]
    }
    out = suggest_mapping_decisions(headers, source, inf)
    assert out["gtin_13"]["mapper_action"] == "auto_map"
    assert out["gtin_13"]["target"] == "barcode_ean"
    rs = out["gtin_13"].get("reasons") or []
    assert any("deterministic" in str(r).lower() for r in rs)


def test_deterministic_launch_go_live_header() -> None:
    source = MagicMock(import_template=MagicMock(expected_columns={}))
    headers = ["go_live_date"]
    inf = {"columns": [{"name": "go_live_date", "dtype": "datetime64[ns]", "sample": ["2024-01-15"]}]}
    out = suggest_mapping_decisions(headers, source, inf)
    assert out["go_live_date"]["mapper_action"] == "auto_map"
    assert out["go_live_date"]["target"] == "launch_date"


def test_deterministic_country_header() -> None:
    source = MagicMock(import_template=MagicMock(expected_columns={}))
    headers = ["country_code", "business_unit"]
    inf = {
        "columns": [
            {"name": "country_code", "dtype": "object", "sample": ["DE"]},
            {"name": "business_unit", "dtype": "object", "sample": ["PCSD"]},
        ]
    }
    out = suggest_mapping_decisions(headers, source, inf)
    assert out["country_code"]["target"] == "country_code"
    assert out["business_unit"]["target"] == "business_unit"


def test_mapper_explainability_codes_present() -> None:
    source = MagicMock(import_template=MagicMock(expected_columns={}))
    headers = ["form_factor"]
    inf = {"columns": [{"name": "form_factor", "dtype": "object", "sample": ["Notebook"]}]}
    out = suggest_mapping_decisions(headers, source, inf)
    assert out["form_factor"]["mapper_action"] == "auto_map"
    rs = out["form_factor"].get("reasons") or []
    assert any("exact_header_match" in str(r) for r in rs)


def test_merge_memory_updates_in_memory_object() -> None:
    """merge_memory mutates source column_mapping_memory (Postgres JSONB in production)."""
    from unittest.mock import MagicMock

    from app.services.imports.pm_mapping_memory import merge_memory_from_pm_save

    src = MagicMock()
    src.id = 1
    src.column_mapping_memory = None
    db = MagicMock()
    db.get.return_value = src
    merge_memory_from_pm_save(
        db,
        source_id=1,
        mapping_decisions={
            "Partner SKU": {"target": "market_sku"},
            "junk": {"disposition": "ignore"},
        },
    )
    assert src.column_mapping_memory["by_header_norm"]["partner_sku"]["target"] == "market_sku"
    assert src.column_mapping_memory["by_header_norm"]["junk"]["disposition"] == "ignore"
