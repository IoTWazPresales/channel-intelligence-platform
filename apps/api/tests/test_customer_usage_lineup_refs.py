"""customer_usage hard-reference labels align with ORM models."""

CUSTOMER_HARD_REF_LABELS = {
    "Sell-out",
    "Returns",
    "Customer inventory",
    "Inventory reconciliation",
    "Customer sell-through",
    "Customer velocity",
    "Pricing (customer-specific)",
    "Forecasts",
    "Lineup plan items",
    "Commercial customer terms",
    "Commercial plan lines",
    "Commercial lineup lines",
    "Historical lineup headers",
    "Shipment evidence (resolved customer)",
    "Customer report config",
    "DSI import staging (resolved customer)",
    "Customer sell-through import staging",
    "Customer source token aliases",
    "Budget requests (linked customer)",
    "Import mapping candidates (customer)",
}


def test_customer_hard_ref_labels_include_lineup_and_staging():
    assert "Commercial lineup lines" in CUSTOMER_HARD_REF_LABELS
    assert "Commercial lineup cases" not in CUSTOMER_HARD_REF_LABELS
    assert "DSI import staging (resolved customer)" in CUSTOMER_HARD_REF_LABELS
    assert "Customer sell-through import staging" in CUSTOMER_HARD_REF_LABELS
