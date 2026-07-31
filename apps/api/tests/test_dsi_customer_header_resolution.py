"""Unit tests for DSI RAW-style column auto-mapping inference (no DB)."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.imports.dsi_mapping_workflow import (
    apply_dsi_customer_column_target_resolution,
    apply_dsi_never_auto_map_denylist,
    apply_dsi_prefer_header_targets,
    apply_dsi_product_identifier_sample_inference,
    apply_exact_raw_customer_header_overrides,
    build_initial_dsi_field_mapping,
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


def test_exact_raw_customer_headers_set_primary_pair_with_extra_customerish_columns() -> None:
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


def test_confirmed_memory_beats_template_exact_overrides() -> None:
    """D-022 precedence: confirmed memory > template exact > heuristic."""
    headers = ["Customer name", "Dealer Name Group", "sku"]
    source = SimpleNamespace(
        column_mapping_memory={
            "schema_version": "1",
            "by_header_norm": {
                "customer_name": {"target": "region_or_province_token", "confirmations": 2},
            },
        }
    )
    template = {
        "product_identifier": {"aliases": ["sku"]},
        "customer_dealer_token": {"aliases": ["customer name"]},
        "dealer_group_token": {"aliases": ["dealer name group"]},
    }
    out = build_initial_dsi_field_mapping(None, headers, source, template)  # type: ignore[arg-type]
    assert out["Customer name"] == "region_or_province_token"
    assert out["Dealer Name Group"] == "dealer_group_token"


def test_denylist_clears_dealer_name_1_and_dealer_code() -> None:
    headers = ["Dealer Name 1", "Customer Code (Dealer Code)", "Dealer Name", "sku"]
    raw = {
        "Dealer Name 1": "customer_dealer_token",
        "Customer Code (Dealer Code)": "customer_dealer_token",
        "Dealer Name": "customer_dealer_token",
        "sku": "product_identifier",
    }
    cleared = apply_dsi_never_auto_map_denylist(headers, raw)
    assert "Dealer Name 1" not in cleared
    assert "Customer Code (Dealer Code)" not in cleared
    assert cleared.get("Dealer Name") == "customer_dealer_token"


def test_prefer_customer_name_over_dealer_name_when_both_map_to_source() -> None:
    headers = ["Customer name", "Dealer Name", "sku"]
    m = {
        "Customer name": "customer_dealer_token",
        "Dealer Name": "customer_dealer_token",
        "sku": "product_identifier",
    }
    out = apply_dsi_prefer_header_targets(headers, m)
    assert out.get("Customer name") == "customer_dealer_token"
    assert "Dealer Name" not in out or out.get("Dealer Name") != "customer_dealer_token"


def test_demote_total_price_when_unit_price_present() -> None:
    headers = ["Unit Price", "Total Price", "sku"]
    m = {
        "Unit Price": "unit_sellout_price_ex_tax_amount",
        "Total Price": "unit_sellout_price_ex_tax_amount",
        "sku": "product_identifier",
    }
    out = apply_dsi_prefer_header_targets(headers, m)
    assert out.get("Unit Price") == "unit_sellout_price_ex_tax_amount"
    assert out.get("Total Price") != "unit_sellout_price_ex_tax_amount"


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


def test_part_number_preferred_over_model_when_both_have_samples() -> None:
    """Resolve-tier alignment: item/part grain beats sales-model when both are populated."""
    headers = ["Model Name", "ASUS Part No.", "Customer Sku", "MFG model name", "Qty"]
    mapping = {
        "Model Name": "product_identifier",
        "ASUS Part No.": "product_identifier",
        "Customer Sku": "product_identifier",
        "MFG model name": "product_identifier",
        "Qty": "quantity_sold",
    }
    samples = {
        "Model Name": ["B3402FVA-C716512B0W", "X1504VAP-I516512BL2W"],
        "ASUS Part No.": ["90NX07N1-M02YP0", "90NB13Y1-M01M40"],
        "Customer Sku": [],
        "MFG model name": [],
    }
    out = apply_dsi_product_identifier_sample_inference(headers, mapping, samples)
    assert out.get("ASUS Part No.") == "product_identifier"
    assert out.get("Model Name") != "product_identifier"
    assert out.get("Customer Sku") != "product_identifier"
    assert out.get("MFG model name") != "product_identifier"


def test_model_kept_when_part_column_empty() -> None:
    headers = ["Model Name", "Part No.", "Qty"]
    mapping = {
        "Model Name": "product_identifier",
        "Part No.": "product_identifier",
        "Qty": "quantity_sold",
    }
    samples = {
        "Model Name": ["B3402FVA-C716512B0W", "X1504VAP-I516512BL2W"],
        "Part No.": [],
    }
    out = apply_dsi_product_identifier_sample_inference(headers, mapping, samples)
    assert out.get("Model Name") == "product_identifier"
    assert out.get("Part No.") != "product_identifier"


def test_header_seeds_map_generic_part_and_ean_columns() -> None:
    from app.services.imports.dsi_mapping_workflow import apply_dsi_product_identifier_header_seeds

    headers = ["Dealer Name", "Vendor Part No.", "EAN Code", "Notes"]
    out = apply_dsi_product_identifier_header_seeds(headers, {"Dealer Name": "customer_dealer_token"})
    assert out.get("Vendor Part No.") == "product_identifier"
    assert out.get("EAN Code") == "product_identifier"
    assert "Notes" not in out or out.get("Notes") != "product_identifier"


def test_customer_only_exact_header_sets_source_customer_name() -> None:
    headers = ["Customer name", "sku", "Qty"]
    m = {"Customer name": "dealer_group_token", "sku": "product_identifier", "Qty": "quantity_sold"}
    m = apply_exact_raw_customer_header_overrides(headers, m)
    assert m["Customer name"] == "customer_dealer_token"


def test_asus_dealer_name_maps_via_build_initial_without_customer_name() -> None:
    headers = ["Dealer Name", "ASUS Part No.", "Unit Price", "Qty"]
    template = {
        "customer_dealer_token": {"aliases": ["dealer name", "dealer_name"]},
        "product_identifier": {"aliases": ["asus part no.", "asus part no"]},
        "unit_sellout_price_ex_tax_amount": {"aliases": ["unit price"]},
        "quantity_sold": {"aliases": ["qty"]},
    }
    out = build_initial_dsi_field_mapping(None, headers, None, template)  # type: ignore[arg-type]
    assert out.get("Dealer Name") == "customer_dealer_token"
    assert out.get("ASUS Part No.") == "product_identifier"
    assert out.get("Unit Price") == "unit_sellout_price_ex_tax_amount"


def test_sanitize_clears_denylisted_customer_code_header() -> None:
    headers = ["Customer Code (Dealer Code)", "Dealer Name", "sku"]
    raw = {
        "Customer Code (Dealer Code)": "customer_dealer_token",
        "Dealer Name": "customer_dealer_token",
        "sku": "product_identifier",
    }
    clean, notices = sanitize_dsi_field_mapping(headers, raw)
    assert "Customer Code (Dealer Code)" not in clean
    assert clean.get("Dealer Name") == "customer_dealer_token"
    assert any(n.get("code") == "dsi_denylist_cleared" for n in notices)


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
