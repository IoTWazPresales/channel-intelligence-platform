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
    _union_mapping,
    detect_mapping,
    layout_signature,
    sniff_columns,
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
    assert detect_mapping(["SKU", "Week", "Units", "SOH", "Colour"], EXPECTED) == {
        "SKU": "raw_product_token",
        "Week": "raw_period_ref",
        "Units": "units_sold",
        "SOH": "reported_soh",
    }


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
    assert set(CANONICAL_LABELS) == set(CANONICAL_FIELDS)


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
