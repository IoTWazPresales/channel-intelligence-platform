"""DSI customer candidate identity (no DB — complements pipeline tests on disposable DB)."""

from __future__ import annotations


def test_customer_identity_same_key_for_customer_vs_dealer_column_wootware() -> None:
    """Regression: two source patterns that previously split into duplicate normalized_key."""
    from app.services.imports.distributor_sales_inventory import _customer_candidate_identity_norm

    k1 = _customer_candidate_identity_norm("Wootware Computers", None)
    k2 = _customer_candidate_identity_norm("to be mapped", "Wootware Computers")
    assert k1 == k2 == "wootware computers"
