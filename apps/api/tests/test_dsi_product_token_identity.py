"""Unit tests for dsi_product_token_identity."""

from __future__ import annotations

from app.services.imports.dsi_product_token_identity import (
    extract_derived_sales_model_codes,
    product_identity_lookup_keys,
)


def test_product_identity_lookup_keys_full_token_first() -> None:
    keys = product_identity_lookup_keys("B1502CBA-I58512B1X")
    assert keys[0] == "b1502cba-i58512b1x"
    assert keys == ("b1502cba-i58512b1x",)


def test_extract_embedded_asus_code_from_long_description() -> None:
    raw = (
        "ASUS i5-1335U 15.6 FHD+ 16GB 512GB SSD W11P B1502CVA-I58512B9X "
        "ExpertBook B1 Clamshell"
    )
    derived = extract_derived_sales_model_codes(raw)
    assert "b1502cva-i58512b9x" in derived
    keys = product_identity_lookup_keys(raw)
    assert keys[0] != "b1502cva-i58512b9x"  # full prose token first
    assert "b1502cva-i58512b9x" in keys


def test_extract_ignores_generic_tokens() -> None:
    assert extract_derived_sales_model_codes("unknown product tbd") == ()


def test_lookup_keys_deduplicate_full_and_derived() -> None:
    keys = product_identity_lookup_keys("B1502CVA-I58512B9X")
    assert keys == ("b1502cva-i58512b9x",)
