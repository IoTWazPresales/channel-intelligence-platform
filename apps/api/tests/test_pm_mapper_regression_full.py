"""Broad Product Master mapper regressions — generic behaviors, not one vendor."""

from unittest.mock import MagicMock

from app.services.imports.product_master_workflow import suggest_mapping_decisions


def _src_blank():
    s = MagicMock(import_template=MagicMock(expected_columns={}))
    return s


def test_strong_mappings_universal_terms() -> None:
    inf = {
        "columns": [
            {"name": "manufacturer_part_number", "dtype": "object", "sample": ["PN-001-A"]},
            {"name": "commercial_sku", "dtype": "object", "sample": ["COMM-9"]},
            {"name": "GTIN / EAN", "dtype": "object", "sample": ["5901234123457"]},
            {"name": "UPC retail", "dtype": "object", "sample": ["012345678905"]},
            {"name": "Sales country", "dtype": "object", "sample": ["MX"]},
            {"name": "Owning division", "dtype": "object", "sample": ["Ent"]},
            {"name": "Merchandising line", "dtype": "object", "sample": ["Notebooks"]},
            {"name": "Go live date", "dtype": "datetime64[ns]", "sample": ["2025-06-01"]},
            {"name": "EOL target date", "dtype": "datetime64[ns]", "sample": ["2028-12-31"]},
        ]
    }
    headers = [c["name"] for c in inf["columns"]]
    out = suggest_mapping_decisions(headers, _src_blank(), inf)
    assert out["manufacturer_part_number"]["target"] == "technical_product_id"
    assert out["commercial_sku"]["target"] == "market_sku"
    assert out["GTIN / EAN"]["target"] == "barcode_ean"
    assert out["UPC retail"]["target"] == "barcode_upc"
    assert out["Sales country"]["target"] == "country_code"
    assert out["Owning division"]["target"] == "business_unit"
    assert out["Merchandising line"]["target"] == "product_line"
    assert out["Go live date"]["target"] == "launch_date"
    assert out["EOL target date"]["target"] == "end_of_life_date"


def test_negative_iso_date_not_barcode() -> None:
    inf = {
        "columns": [
            {"name": "mystery_col", "dtype": "object", "sample": ["2024-01-15"]},
            {"name": "ean_column", "dtype": "object", "sample": ["5901234123457"]},
        ]
    }
    headers = ["mystery_col", "ean_column"]
    out = suggest_mapping_decisions(headers, _src_blank(), inf)
    tgt = out["mystery_col"].get("target")
    assert tgt is None or tgt != "barcode_ean"
    assert out["ean_column"]["target"] == "barcode_ean"


def test_negative_prose_not_technical_id() -> None:
    inf = {
        "columns": [
            {
                "name": "gpu_details_spec",
                "dtype": "object",
                "sample": ["NVIDIA RTX 4070 Laptop GPU 8GB GDDR6 with advanced ray tracing"],
            },
        ]
    }
    out = suggest_mapping_decisions(["gpu_details_spec"], _src_blank(), inf)
    assert out["gpu_details_spec"]["mapper_action"] != "auto_map" or out["gpu_details_spec"].get("target") not in (
        "technical_product_id",
        "display_name",
    )


def test_spec_column_recommends_stage_metadata() -> None:
    inf = {
        "columns": [
            {"name": "processor_model_name_full", "dtype": "object", "sample": ["Intel Core Ultra 7 155H"]},
        ]
    }
    out = suggest_mapping_decisions(["processor_model_name_full"], _src_blank(), inf)
    assert out["processor_model_name_full"]["mapper_action"] == "recommend_stage_metadata"


def test_noise_column_recommends_ignore() -> None:
    inf = {"columns": [{"name": "x", "dtype": "object", "sample": [""]}]}
    out = suggest_mapping_decisions(["x"], _src_blank(), inf)
    assert out["x"]["mapper_action"] == "recommend_ignore"


def test_generic_eu_article_number_alias_not_vendor_specific() -> None:
    """Contrasting regression: EU-style generic catalog headers (not US retailer naming)."""
    source = MagicMock(import_template=MagicMock(expected_columns={}))
    headers = ["artikelnummer", "libelle_produit"]
    inf = {
        "columns": [
            {"name": "artikelnummer", "dtype": "object", "sample": ["DE-ART-992"]},
            {"name": "libelle_produit", "dtype": "object", "sample": ["Ordinateur portable 14 pouces"]},
        ]
    }
    out = suggest_mapping_decisions(headers, source, inf)
    assert out["artikelnummer"]["mapper_action"] == "auto_map"
    assert out["artikelnummer"]["target"] == "technical_product_id"
    assert out["libelle_produit"]["mapper_action"] == "auto_map"
    assert out["libelle_produit"]["target"] == "display_name"


def test_weak_mapping_suppresses_runner_up_catchall() -> None:
    inf = {
        "columns": [
            {"name": "random_notes", "dtype": "object", "sample": ["misc"]},
        ]
    }
    out = suggest_mapping_decisions(["random_notes"], _src_blank(), inf)
    ru = out["random_notes"].get("runner_up")
    if ru:
        assert ru.get("target") not in ("technical_product_id", "display_name")


def test_source_memory_still_boosts_same_source() -> None:
    class _Tpl:
        expected_columns: dict = {}

    class _Src:
        pass

    src = _Src()
    src.import_template = _Tpl()
    src.expected_template = None
    src.column_mapping_memory = {
        "by_header_norm": {"partner_ref": {"target": "source_product_code", "confirmations": 2}},
    }
    inf = {"columns": [{"name": "partner_ref", "dtype": "object", "sample": ["Z"]}]}
    out = suggest_mapping_decisions(["partner_ref"], src, inf)
    assert out["partner_ref"].get("from_source_memory") is True
    assert out["partner_ref"]["target"] == "source_product_code"
