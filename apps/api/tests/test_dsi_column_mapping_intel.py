"""DSI column mapping intel: hints and high-confidence automap."""

from types import SimpleNamespace

from app.services.imports.dsi_column_mapping_intel import (
    apply_high_confidence_dsi_automap,
    suggest_dsi_column_mapping,
)


def test_suggest_dsi_prefers_saved_memory_target():
    src = SimpleNamespace(
        column_mapping_memory={
            "by_header_norm": {
                "distributor": {"target": "distributor_token", "confirmations": 5},
            }
        },
        import_template=None,
        expected_template=None,
    )
    headers = ["Distributor", "SKU", "Qty"]
    hints = suggest_dsi_column_mapping(headers, src, column_samples=None, current_field_mapping={})
    assert hints["Distributor"]["suggested_target"] == "distributor_token"
    assert hints["Distributor"]["confidence"] > 0.85


def test_apply_high_confidence_dsi_automap_fills_unused_high_confidence():
    src = SimpleNamespace(column_mapping_memory=None, import_template=None, expected_template=None)
    headers = ["Distributor", "PartNo", "Quantity Sold"]
    base = {"Distributor": "distributor_token"}
    out, applied = apply_high_confidence_dsi_automap(headers, src, base, column_samples=None, min_confidence=0.85)
    assert "distributor_token" in out.values()
    assert len(applied) >= 1
