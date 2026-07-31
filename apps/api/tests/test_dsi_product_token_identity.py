"""Unit tests for dsi_product_token_identity."""

from __future__ import annotations

from app.services.imports.dsi_product_token_identity import (
    channel_suffix_stripped_key,
    extract_derived_sales_model_codes,
    product_identity_lookup_keys,
    trailing_separator_bases,
)


def test_product_identity_lookup_keys_full_token_first() -> None:
    keys = product_identity_lookup_keys("B1502CBA-I58512B1X")
    assert keys[0] == "b1502cba-i58512b1x"
    # One-level peel is present after full (evidence-gated at lookup time).
    assert keys == ("b1502cba-i58512b1x", "b1502cba")


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
    assert keys[0] == "b1502cva-i58512b9x"
    assert "b1502cva" in keys  # one-level trailer base after full


def test_channel_suffix_stripped_key_cm_e_demo() -> None:
    assert channel_suffix_stripped_key("v440vak-i716512w0w-cm") == "v440vak-i716512w0w"
    assert channel_suffix_stripped_key("h7606wp-o93210b2x-e") == "h7606wp-o93210b2x"
    assert channel_suffix_stripped_key("b3402fea-i58512b0x-demo") == "b3402fea-i58512b0x"
    assert channel_suffix_stripped_key("bp2701 rog backpack/gr-cm") == "bp2701 rog backpack/gr"
    assert channel_suffix_stripped_key("rc73xa-zp2410b0w-cm") == "rc73xa-zp2410b0w"
    # Not a known channel segment — leave intact
    assert channel_suffix_stripped_key("v440vak-i716512w0w") is None
    assert channel_suffix_stripped_key("something-xx") is None


def test_trailing_separator_bases_hyphen_and_underscore() -> None:
    assert trailing_separator_bases("e1504fa-o58512b0w_deal") == ("e1504fa-o58512b0w",)
    assert trailing_separator_bases("rc72la-z12410b0w-dg") == ("rc72la-z12410b0w",)
    assert trailing_separator_bases("v440vak-i716512w0w-cm") == ("v440vak-i716512w0w",)
    assert trailing_separator_bases("nosep") == ()
    assert trailing_separator_bases("-only") == ()


def test_lookup_keys_include_channel_suffix_base_before_derived() -> None:
    keys = product_identity_lookup_keys("V440VAK-I716512W0W-CM")
    assert keys[0] == "v440vak-i716512w0w-cm"
    assert keys[1] == "v440vak-i716512w0w"
    # Prose / non-regex models still get the stripped base
    prose = product_identity_lookup_keys("BP2701 ROG BACKPACK/GR-CM")
    assert prose[0] == "bp2701 rog backpack/gr-cm"
    assert prose[1] == "bp2701 rog backpack/gr"
    rc = product_identity_lookup_keys("RC73XA-ZP2410B0W-CM")
    assert rc[0] == "rc73xa-zp2410b0w-cm"
    assert rc[1] == "rc73xa-zp2410b0w"


def test_lookup_keys_underscore_deal_and_hyphen_dg() -> None:
    deal = product_identity_lookup_keys("E1504FA-O58512B0W_Deal")
    assert deal[0] == "e1504fa-o58512b0w_deal"
    assert "e1504fa-o58512b0w" in deal
    dg = product_identity_lookup_keys("RC72LA-Z12410B0W-DG")
    assert dg[0] == "rc72la-z12410b0w-dg"
    assert "rc72la-z12410b0w" in dg
