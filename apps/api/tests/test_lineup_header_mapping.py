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


def test_old_srp_does_not_steal_current_srp():
    cols = ["SKU", "Old SRP", "New SRP", "Qty"]
    m = build_commercial_lineup_column_map(cols)
    assert m.get("old_srp_local") == "Old SRP"
    assert m.get("msrp_local") == "New SRP"


def test_full_pricing_chain_columns_map():
    cols = [
        "SKU",
        "SRP",
        "Dealer margin",
        "Rebate",
        "Disti margin",
        "Import Tax",
        "ROE",
        "VAT",
        "Net price",
        "Disti Cost",
        "Dealer price",
        "Actual DAP",
        "Qty",
    ]
    m = build_commercial_lineup_column_map(cols)
    assert m.get("msrp_local") == "SRP"
    assert m.get("dealer_margin_pct_evidence") == "Dealer margin"
    assert m.get("rebate_pct_evidence") == "Rebate"
    assert m.get("distributor_margin_pct_evidence") == "Disti margin"
    assert m.get("import_tax_pct_evidence") == "Import Tax"
    assert m.get("roe_evidence") == "ROE"
    assert m.get("vat_pct_evidence") == "VAT"
    assert m.get("net_price_evidence_local") == "Net price"
    assert m.get("disti_cost_evidence_local") == "Disti Cost"
    assert m.get("dealer_price_evidence_local") == "Dealer price"
    assert m.get("actual_dap_evidence_local") == "Actual DAP"
