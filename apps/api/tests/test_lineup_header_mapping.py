"""Unit tests for commercial current-lineup header → field mapping (MSRP vs promo vs DAP)."""

from app.services.commercial_planner.lineup_header_mapping import build_commercial_lineup_column_map


def test_q2_msrp_maps_to_msrp_local():
    cols = ["SKU", "Q2 MSRP", "Qty"]
    m = build_commercial_lineup_column_map(cols)
    assert m.get("msrp_local") == "Q2 MSRP"


def test_promo_price_maps_to_promo_evidence_not_msrp():
    cols = ["SKU", "Promo Price", "MSRP"]
    m = build_commercial_lineup_column_map(cols)
    assert m.get("promo_price_evidence_local") == "Promo Price"
    assert m.get("msrp_local") == "MSRP"


def test_promo_srp_maps_to_promo_not_msrp():
    cols = ["Model", "Promo SRP", "FY MSRP"]
    m = build_commercial_lineup_column_map(cols)
    assert m.get("promo_price_evidence_local") == "Promo SRP"
    assert m.get("msrp_local") == "FY MSRP"


def test_dap_maps_only_to_dap_evidence():
    cols = ["SKU", "DAP", "Q1 MSRP"]
    m = build_commercial_lineup_column_map(cols)
    assert m.get("dap_evidence_local") == "DAP"
    assert m.get("msrp_local") == "Q1 MSRP"


def test_list_price_pattern_msrp_without_promo_qualifier():
    cols = ["Part", "List Price", "Deal Price"]
    m = build_commercial_lineup_column_map(cols)
    assert m.get("msrp_local") == "List Price"
    assert m.get("promo_price_evidence_local") == "Deal Price"
