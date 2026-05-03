"""Unit tests for DSI customer-resolution helpers (no import pipeline / DB)."""

from __future__ import annotations


def test_effective_dsi_customer_resolution_raw_dealer_group_and_placeholders() -> None:
    from app.services.imports.distributor_sales_inventory import effective_dsi_customer_resolution_raw

    token, notes = effective_dsi_customer_resolution_raw("to be mapped", "Metro Market Group")
    assert token == "Metro Market Group"
    assert "customer_token_source_dealer_group" in notes

    t2, n2 = effective_dsi_customer_resolution_raw("  ", "Metro Market Group")
    assert t2 == "Metro Market Group"
    assert "customer_token_source_dealer_group" in n2

    assert effective_dsi_customer_resolution_raw("CUST-1001", "Other Group")[0] == "CUST-1001"

    assert effective_dsi_customer_resolution_raw("to be mapped", "to be mapped") == (None, [])
