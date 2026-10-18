"""N-0111 (Warren 2026-10-16): a sell-through upload picks a reporting customer; the only per-customer
configuration is the saved column layout. Pure parts, no database:

- a header set is fingerprinted so the same layout matches next week's file (period-named columns,
  unit stubs, case, order and blank columns do not matter) while a real extra column does;
- a header row the aliases do not recognise is still found, so the mapping step can list the columns;
- the mapping a user confirms is checked (standard columns only, product mapped, units or on-hand mapped);
- two layouts that map one header two ways are refused for one job.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.imports.cst_layouts import (
    CANONICAL_LABELS,
    LEGACY_PRODUCT_TARGET,
    _union_mapping,
    detect_mapping,
    layout_signature,
    mapping_targets,
    sniff_columns,
    uses_legacy_product_slot,
    validate_field_mapping,
)
from app.services.imports.parsers.customer_sell_through_flat import CANONICAL_FIELDS

EXPECTED = {
    "units_sold": {"aliases": ["units", "qty"], "required": True},
    "raw_product_token": {"aliases": ["sku"], "required": True},
    "raw_period_ref": {"aliases": ["week", "date"], "required": False},
    "reported_soh": {"aliases": ["soh", "on_hand"], "required": False},
}


def test_signature_ignores_order_case_spacing_and_blank_columns() -> None:
    a = ["SKU", "Units Sold", "Store  Name", None, "Unnamed: 4"]
    b = ["store name", "UNITS SOLD", "sku", "col_9"]
    assert layout_signature(a) == layout_signature(b)


def test_signature_ignores_period_named_columns() -> None:
    # Makro-style pivot: the week columns change every file, the layout does not.
    wk1 = ["Site", "Article", "Vendor Prod Code", "MAC", "SOH", "49-2025", "50-2025", "01-2026"]
    wk14 = ["Site", "Article", "Vendor Prod Code", "MAC", "SOH", "10-2026", "11-2026", "12-2026", "13-2026"]
    assert layout_signature(wk1) == layout_signature(wk14)
    # Game-style wide week: measure + week band, and "week 14" / "2026-W14" / "Jan 2026" style names.
    assert layout_signature(["Article", "Sales U TY 027.2026", "Sales U TY 028.2026"]) == layout_signature(
        ["Article", "Sales U TY 031.2026"]
    )
    assert layout_signature(["SKU", "Week 14", "wk 15", "2026-W16", "Jan 2026"]) == layout_signature(["SKU", "W20"])


def test_signature_ignores_currency_and_unit_stubs() -> None:
    assert layout_signature(["EAN/UPC", "Sales U TY", "ZAR", "EA"]) == layout_signature(["EAN/UPC", "Sales U TY"])


def test_signature_differs_for_a_real_extra_column() -> None:
    # Takealot week 39 has "Supplier Stock" that week 31 does not: a different layout.
    base = ["Barcode", "Product ID", "Transaction Week", "sales"]
    assert layout_signature(base) != layout_signature(base + ["Supplier Stock"])


def test_sniff_finds_the_header_row_the_aliases_know() -> None:
    data = b"Amazon weekly report,,,\n,,,\nSKU,Week,Units,SOH\nA1,W12,3,10\nA2,W12,1,4\n"
    info = sniff_columns("amazon.csv", data, EXPECTED)
    assert info is not None
    assert info["columns"] == ["SKU", "Week", "Units", "SOH"]
    assert info["samples"]["SKU"] == ["A1", "A2"]


def test_sniff_still_lists_columns_of_a_layout_the_aliases_do_not_recognise() -> None:
    data = b"Item Code,Qty Sold,Current Stock,Web ID\nE1,3,10,w1\nE2,1,4,w2\n"
    info = sniff_columns("evetech.csv", data, EXPECTED)
    assert info is not None
    assert info["columns"] == ["Item Code", "Qty Sold", "Current Stock", "Web ID"]
    # The parser's own alias match finds nothing for these headers: the mapping step has to.
    assert detect_mapping(info["columns"], EXPECTED) == {}


def test_detect_mapping_uses_the_aliases_the_parser_would() -> None:
    # N-0111 (2026-10-19): the older single product column is never suggested; a header whose name
    # does not say what it is (SKU) is left for the uploader to map to a product identifier.
    assert detect_mapping(["SKU", "Week", "Units", "SOH", "Colour"], EXPECTED) == {
        "Week": "raw_period_ref",
        "Units": "units_sold",
        "SOH": "reported_soh",
    }


def test_detect_mapping_suggests_an_identifier_slot_only_by_a_name_that_says_what_it_is() -> None:
    cols = ["Part Number", "EAN/UPC", "Sales Model Name", "Units", "Description"]
    assert detect_mapping(cols, EXPECTED) == {
        "Part Number": "raw_part_number_token",
        "EAN/UPC": "raw_barcode_token",
        "Sales Model Name": "raw_sales_model_token",
        "Units": "units_sold",
    }
    # A header the template used to read as the product column ("barcode") is now the barcode slot.
    assert detect_mapping(["Barcode", "Units"], EXPECTED) == {"Barcode": "raw_barcode_token", "Units": "units_sold"}
    # Each slot is suggested once.
    assert detect_mapping(["EAN", "UPC", "Units"], EXPECTED) == {"EAN": "raw_barcode_token", "Units": "units_sold"}


def test_sniff_returns_none_for_an_unreadable_file() -> None:
    assert sniff_columns("junk.xlsx", b"not a workbook", EXPECTED) is None


def test_validate_field_mapping_keeps_the_files_own_header_text() -> None:
    clean = validate_field_mapping(["Item Code", "Qty Sold"], {"item code": "raw_product_token", "qty sold": "units_sold"})
    assert clean == {"Item Code": "raw_product_token", "Qty Sold": "units_sold"}


@pytest.mark.parametrize(
    "mapping, message",
    [
        ({"Qty Sold": "units_sold"}, "product"),
        ({"Item Code": "raw_product_token"}, "units sold or on-hand"),
        ({"Item Code": "raw_product_token", "Qty Sold": "bogus"}, "not a standard"),
        ({"Item Code": "raw_product_token", "Nope": "units_sold"}, "not in the file"),
    ],
)
def test_validate_field_mapping_refuses_gaps(mapping: dict, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_field_mapping(["Item Code", "Qty Sold"], mapping)


def test_every_standard_column_has_a_label_in_the_mapping_step() -> None:
    # The older single product column is not offered for a new mapping; every other column is.
    assert set(CANONICAL_LABELS) | {LEGACY_PRODUCT_TARGET} == set(CANONICAL_FIELDS)


def test_the_mapping_step_offers_warrens_columns_main_list_then_more_columns() -> None:
    assert list(CANONICAL_LABELS.values())[:13] == [
        "Period (sale date, week or month)",
        "Sales model / marketing name",
        "Part number",
        "Barcode (EAN or UPC)",
        "Customer product code",
        "Units sold",
        "On-hand (stock)",
        "Unit cost",
        "Unit sell price",
        "Total line cost",
        "Total revenue",
        "Store / site",
        "Listing ID (website listing, e.g. ASIN/TSIN)",
    ]
    targets = {t["value"]: t for t in mapping_targets()}
    more = sorted(t["label"] for t in targets.values() if t["group"] == "more" and not t.get("legacy"))
    assert more == sorted(["Unit MAC", "Marketplace", "On-hand value", "In-transit units", "On-order units"])
    # "Customer article code" is renamed in the UI only: the stored column keeps its name.
    assert targets["raw_article_token"]["label"] == "Customer product code"
    assert "Customer article code" not in CANONICAL_LABELS.values()
    assert targets[LEGACY_PRODUCT_TARGET]["legacy"] is True


@pytest.mark.parametrize(
    "slot", ["raw_part_number_token", "raw_barcode_token", "raw_sales_model_token", "raw_article_token", "raw_product_token"]
)
def test_any_one_product_identifier_satisfies_the_product_gate(slot: str) -> None:
    clean = validate_field_mapping(["Code", "Qty Sold"], {"Code": slot, "Qty Sold": "units_sold"})
    assert clean == {"Code": slot, "Qty Sold": "units_sold"}


def test_a_mapping_with_no_product_identifier_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one product identifier"):
        validate_field_mapping(["Code", "Qty Sold"], {"Qty Sold": "units_sold"})


def test_a_layout_with_only_the_older_product_column_is_flagged_for_re_mapping() -> None:
    assert uses_legacy_product_slot({"A": "raw_product_token", "B": "units_sold"})
    assert not uses_legacy_product_slot({"A": "raw_product_token", "C": "raw_barcode_token"})
    assert not uses_legacy_product_slot({"A": "raw_barcode_token"})
    assert not uses_legacy_product_slot({})


def test_one_header_mapped_two_ways_is_refused_for_one_job() -> None:
    a = SimpleNamespace(name="Weekly", field_mapping={"Qty": "units_sold", "SKU": "raw_product_token"})
    b = SimpleNamespace(name="History", field_mapping={"qty": "reported_soh", "Code": "raw_product_token"})
    with pytest.raises(ValueError, match="Upload these files separately"):
        _union_mapping([a, b])
    c = SimpleNamespace(name="Other", field_mapping={"Code": "raw_product_token", "On hand": "reported_soh"})
    assert _union_mapping([a, c]) == {
        "Qty": "units_sold",
        "SKU": "raw_product_token",
        "Code": "raw_product_token",
        "On hand": "reported_soh",
    }
