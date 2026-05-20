"""Unit tests for DSI RAW-style column auto-mapping inference (no DB)."""

from __future__ import annotations

from app.services.imports.dsi_mapping_workflow import (
    apply_dsi_customer_column_target_resolution,
    apply_dsi_product_identifier_sample_inference,
    apply_exact_raw_customer_header_overrides,
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


def test_exact_raw_customer_headers_override_bad_memory_with_extra_customerish_columns() -> None:
    headers = [
        "Bill to customer name",
        "Customer name",
        "Dealer Name Group",
        "End customer name",
        "sku",
    ]
    swapped = {
        "Bill to customer name": "dealer_group_token",
        "Customer name": "dealer_group_token",
        "Dealer Name Group": "customer_dealer_token",
        "End customer name": "customer_dealer_token",
        "sku": "product_identifier",
    }
    m = apply_exact_raw_customer_header_overrides(headers, swapped)
    assert m["Dealer Name Group"] == "dealer_group_token"
    assert m["Customer name"] == "customer_dealer_token"
    # Extra columns untouched by exact override
    assert m["Bill to customer name"] == "dealer_group_token"
    m2 = apply_dsi_customer_column_target_resolution(headers, m)
    assert m2["Customer name"] == "customer_dealer_token"
    assert m2["Dealer Name Group"] == "dealer_group_token"


def test_product_column_nb_like_product_header_demoted_modelname_kept() -> None:
    headers = ["PRODUCT", "ModelName", "Qty"]
    mapping = {"PRODUCT": "product_identifier", "ModelName": "product_identifier", "Qty": "quantity_sold"}
    samples = {
        "PRODUCT": ["NB", "NB", "DT"],
        "ModelName": ["X515MA-C42G0W", "FA507NV-71610G0W"],
    }
    out = apply_dsi_product_identifier_sample_inference(headers, mapping, samples)
    assert "PRODUCT" not in out or out.get("PRODUCT") != "product_identifier"
    assert out.get("ModelName") == "product_identifier"


def test_product_column_sku_like_product_samples_keeps_product_identifier() -> None:
    headers = ["PRODUCT", "Qty"]
    mapping = {"PRODUCT": "product_identifier", "Qty": "quantity_sold"}
    samples = {"PRODUCT": ["X515MA-C42G0W", "FA507NV-71610G0W"]}
    out = apply_dsi_product_identifier_sample_inference(headers, mapping, samples)
    assert out.get("PRODUCT") == "product_identifier"


def test_product_inference_assigns_modelname_when_product_demoted() -> None:
    headers = ["PRODUCT", "ModelName", "Qty"]
    mapping = {"PRODUCT": "product_identifier", "Qty": "quantity_sold"}
    samples = {
        "PRODUCT": ["NB", "NB"],
        "ModelName": ["X515MA-C42G0W", "E1504GA-I38512B0W"],
    }
    out = apply_dsi_product_identifier_sample_inference(headers, mapping, samples)
    assert "PRODUCT" not in out or out.get("PRODUCT") != "product_identifier"
    assert out.get("ModelName") == "product_identifier"


def test_customer_only_exact_header_sets_source_customer_name() -> None:
    headers = ["Customer name", "sku", "Qty"]
    m = {"Customer name": "dealer_group_token", "sku": "product_identifier", "Qty": "quantity_sold"}
    m = apply_exact_raw_customer_header_overrides(headers, m)
    assert m["Customer name"] == "customer_dealer_token"


def test_sanitize_dsi_does_not_mutate_valid_manual_mapping() -> None:
    """Validate/apply paths only sanitize; they must not re-run infer heuristics (contract)."""
    headers = ["Customer name", "Dealer Name Group", "PRODUCT", "ModelName"]
    manual = {
        "Customer name": "customer_dealer_token",
        "Dealer Name Group": "dealer_group_token",
        "PRODUCT": "channel_key_token",
        "ModelName": "product_identifier",
    }
    clean, _ = sanitize_dsi_field_mapping(headers, manual)
    assert clean == manual
