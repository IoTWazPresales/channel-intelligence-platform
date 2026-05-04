"""Unit tests for DSI RAW-style customer column auto-mapping (no DB)."""

from __future__ import annotations

from app.services.imports.dsi_mapping_workflow import (
    apply_dsi_customer_column_target_resolution,
    sanitize_dsi_field_mapping,
)


def test_raw_pair_maps_dealer_name_group_to_account_and_customer_name_to_source() -> None:
    headers = ["Dealer Name Group", "Customer name", "sku"]
    raw = {
        "Dealer Name Group": "customer_dealer_token",
        "Customer name": "dealer_group_token",
        "sku": "product_identifier",
    }
    resolved = apply_dsi_customer_column_target_resolution(headers, raw)
    assert resolved["Dealer Name Group"] == "dealer_group_token"
    assert resolved["Customer name"] == "customer_dealer_token"
    clean, _ = sanitize_dsi_field_mapping(headers, resolved)
    assert clean["Dealer Name Group"] == "dealer_group_token"
    assert clean["Customer name"] == "customer_dealer_token"


def test_raw_pair_correct_mapping_unchanged() -> None:
    headers = ["Dealer Name Group", "Customer name"]
    m = {"Dealer Name Group": "dealer_group_token", "Customer name": "customer_dealer_token"}
    assert apply_dsi_customer_column_target_resolution(headers, m) == m


def test_dealer_name_group_avoids_legacy_name_heuristic_after_sanitize() -> None:
    """Shared default_field_mapping maps *name* substring to legacy 'name'; resolution fixes before sanitize."""
    headers = ["Dealer Name Group", "Qty"]
    # Simulates pre-sanitize bleed: wrong target dropped on sanitize without resolution
    raw = {"Dealer Name Group": "name", "Qty": "quantity_sold"}
    resolved = apply_dsi_customer_column_target_resolution(headers, raw)
    clean, _ = sanitize_dsi_field_mapping(headers, resolved)
    assert clean.get("Dealer Name Group") == "dealer_group_token"


def test_customer_only_file_wrong_dealer_group_target_corrected() -> None:
    headers = ["Customer name", "sku"]
    raw = {"Customer name": "dealer_group_token", "sku": "product_identifier"}
    resolved = apply_dsi_customer_column_target_resolution(headers, raw)
    assert resolved["Customer name"] == "customer_dealer_token"


def test_customer_only_sold_to_untouched_when_no_raw_customer_pattern() -> None:
    headers = ["Sold to", "sku"]
    raw = {"Sold to": "customer_dealer_token", "sku": "product_identifier"}
    assert apply_dsi_customer_column_target_resolution(headers, raw) == raw
