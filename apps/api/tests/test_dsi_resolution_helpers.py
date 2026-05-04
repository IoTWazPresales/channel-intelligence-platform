"""Unit tests for DSI customer-resolution helpers (no import pipeline / DB)."""

from __future__ import annotations


def test_effective_dsi_customer_primary_dealer_group_first() -> None:
    from app.services.imports.distributor_sales_inventory import effective_dsi_customer_primary_for_resolution

    token, notes = effective_dsi_customer_primary_for_resolution("to be mapped", "Metro Market Group")
    assert token == "Metro Market Group"
    assert "customer_resolution_primary_dealer_name_group" in notes
    assert "customer_name_evidence_for_group" not in notes

    t2, n2 = effective_dsi_customer_primary_for_resolution("  ", "Metro Market Group")
    assert t2 == "Metro Market Group"
    assert "customer_resolution_primary_dealer_name_group" in n2

    t3, n3 = effective_dsi_customer_primary_for_resolution("Wootware Retail", "Wootware Computers")
    assert t3 == "Wootware Computers"
    assert "customer_resolution_primary_dealer_name_group" in n3
    assert "customer_name_evidence_for_group" in n3

    assert effective_dsi_customer_primary_for_resolution("CUST-1001", "to be mapped")[0] == "CUST-1001"
    assert effective_dsi_customer_primary_for_resolution("CUST-1001", None)[0] == "CUST-1001"

    assert effective_dsi_customer_primary_for_resolution("to be mapped", "to be mapped") == (None, [])


def test_customer_candidate_identity_norm_matches_db_uniqueness() -> None:
    from app.services.imports.distributor_sales_inventory import _customer_candidate_identity_norm

    assert _customer_candidate_identity_norm("Wootware", None) == "wootware"
    assert _customer_candidate_identity_norm(None, "Wootware Computers") == "wootware computers"
    assert _customer_candidate_identity_norm("Wootware Retail", "Wootware Computers") == "wootware computers"
    assert _customer_candidate_identity_norm("to be mapped", "Wootware Computers") == "wootware computers"
    assert _customer_candidate_identity_norm("to be mapped", "to be mapped") == "__blank__"
