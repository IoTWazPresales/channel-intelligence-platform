"""N-0111 (Warren 2026-10-19): the flat sell-through parser stores each product identifier apart.

Part number, barcode and sales model are read only from an explicit mapping (so a layout with the
older single product column reads exactly as before); at least one identifier must be mapped; unit
price and cost are derived from the totals when the unit figure is missing. Pure: no database.
"""

from __future__ import annotations

import pytest

from app.services.imports.parsers.customer_sell_through_flat import (
    EXPECTED_COLUMNS_META_KEY,
    parse_flat_report,
)

# The customer sell-through template's aliases for the older single product column.
TEMPLATE = {
    "raw_product_token": {"aliases": ["sku", "item_code", "barcode", "ean"], "required": True},
    "units_sold": {"aliases": ["units", "qty"], "required": True},
}


def _csv(header: list[str], rows: list[list]) -> bytes:
    return ("\n".join(",".join("" if c is None else str(c) for c in r) for r in [header, *rows]) + "\n").encode()


def _parse(data: bytes, mapping: dict[str, str]):
    return parse_flat_report(data, "weekly.csv", {**mapping, EXPECTED_COLUMNS_META_KEY: TEMPLATE}, 1)


SLOTS = {
    "PN": "raw_part_number_token",
    "Strekkode": "raw_barcode_token",
    "Modelnaam": "raw_sales_model_token",
    "Kode": "raw_article_token",
    "Stuks": "units_sold",
    "Voorraad": "reported_soh",
    "Datum": "raw_period_ref",
}
HEADER = ["PN", "Strekkode", "Modelnaam", "Kode", "Stuks", "Voorraad", "Datum"]


def test_each_identifier_is_stored_in_its_own_slot() -> None:
    res = _parse(_csv(HEADER, [["90NB1", "4711000000011", "X1", "ART-7", 3, 20, "2026-03-02"]]), SLOTS)
    assert res.error is None and len(res.rows) == 1
    row = res.rows[0]
    assert row["raw_part_number_token"] == "90NB1"
    assert row["raw_barcode_token"] == "4711000000011"
    assert row["raw_sales_model_token"] == "X1"
    assert row["raw_article_token"] == "ART-7"
    # The older single column is empty for a layout that names its identifiers.
    assert row["raw_product_token"] is None
    assert row["units_sold"] == 3.0


def test_a_row_needs_only_one_identifier_and_a_row_with_none_is_not_staged() -> None:
    res = _parse(
        _csv(
            HEADER,
            [
                [None, "4711000000011", None, None, 3, 20, "2026-03-02"],  # barcode only
                [None, None, "X1", None, 2, 10, "2026-03-02"],  # sales model only
                [None, None, None, None, 5, 10, "2026-03-02"],  # no identifier at all
            ],
        ),
        SLOTS,
    )
    assert [r["raw_barcode_token"] for r in res.rows] == ["4711000000011", None]
    assert res.skipped_rows == {"missing_product_or_units": 1}


def test_a_barcode_cell_loses_excels_point_zero_and_inner_spaces() -> None:
    res = _parse(_csv(HEADER, [[None, "4711 0000 00011.0", None, None, 1, 1, "2026-03-02"], [None, "4711000000028.0", None, None, 1, 1, "2026-03-02"]]), SLOTS)
    assert [r["raw_barcode_token"] for r in res.rows] == ["4711000000011", "4711000000028"]


def test_no_identifier_mapped_is_refused() -> None:
    res = _parse(_csv(["Stuks", "Voorraad"], [[1, 2]]), {"Stuks": "units_sold", "Voorraad": "reported_soh"})
    assert res.error and "product identifier could not be mapped" in res.error


def test_the_slots_are_never_guessed_from_header_names() -> None:
    # An older layout: one mapped product column. A column headed Barcode that is NOT mapped to a slot
    # must not become the barcode slot.
    header = ["Item", "Barcode", "Stuks", "Voorraad"]
    res = _parse(_csv(header, [["90NB1", "4711000000011", 3, 20]]), {"Item": "raw_product_token", "Stuks": "units_sold", "Voorraad": "reported_soh"})
    row = res.rows[0]
    assert row["raw_product_token"] == "90NB1"
    assert row["raw_barcode_token"] is None and row["raw_part_number_token"] is None and row["raw_sales_model_token"] is None


def test_once_a_slot_is_mapped_the_older_alias_guess_does_not_add_a_second_copy() -> None:
    # "Barcode" is a template alias of the older product column. With the barcode slot mapped
    # explicitly it must not also be read as the older single column.
    header = ["Barcode", "Stuks", "Voorraad"]
    res = _parse(_csv(header, [["4711000000011", 3, 20]]), {"Barcode": "raw_barcode_token", "Stuks": "units_sold", "Voorraad": "reported_soh"})
    row = res.rows[0]
    assert row["raw_barcode_token"] == "4711000000011" and row["raw_product_token"] is None


def test_an_older_layout_keeps_its_row_rule_the_product_cell_must_be_filled() -> None:
    mapping = {"Item": "raw_product_token", "Kode": "raw_article_token", "Stuks": "units_sold", "Voorraad": "reported_soh"}
    res = _parse(_csv(["Item", "Kode", "Stuks", "Voorraad"], [["90NB1", "A1", 3, 20], [None, "A2", 4, 20]]), mapping)
    assert [r["raw_product_token"] for r in res.rows] == ["90NB1"]
    assert res.skipped_rows == {"missing_product_or_units": 1}


def test_unit_price_and_cost_are_derived_from_the_totals_and_marked() -> None:
    header = ["PN", "Stuks", "Voorraad", "Datum", "Omset", "Koste", "Prys"]
    mapping = {
        "PN": "raw_part_number_token",
        "Stuks": "units_sold",
        "Voorraad": "reported_soh",
        "Datum": "raw_period_ref",
        "Omset": "total_sell_amount",
        "Koste": "total_cost_amount",
        "Prys": "unit_sell_price",
    }
    res = _parse(
        _csv(
            header,
            [
                ["A", 4, 10, "2026-03-02", 400, 300, None],  # both unit figures missing -> derived
                ["B", 0, 10, "2026-03-02", 50, 30, None],  # zero units: nothing to divide by
                ["C", 2, 10, "2026-03-02", 999, 100, 120],  # a given unit price is never overwritten
            ],
        ),
        mapping,
    )
    a, b, c = res.rows
    assert (a["unit_sell_price"], a["unit_cost"]) == (100.0, 75.0)
    assert a["raw_row_payload"]["_cst_derived"]["unit_sell_price_from_total"] is True
    assert a["raw_row_payload"]["_cst_derived"]["unit_cost_from_total"] is True
    # The totals stay as given (also in the untouched source cells).
    assert a["raw_row_payload"]["_cst_derived"]["total_sell_amount"] == 400.0
    assert a["raw_row_payload"]["Omset"] == "400"
    assert b["unit_sell_price"] is None and b["unit_cost"] is None
    assert "unit_sell_price_from_total" not in (b["raw_row_payload"].get("_cst_derived") or {})
    assert c["unit_sell_price"] == 120.0
    assert "unit_sell_price_from_total" not in c["raw_row_payload"]["_cst_derived"]
    assert c["unit_cost"] == 50.0 and c["raw_row_payload"]["_cst_derived"]["unit_cost_from_total"] is True


@pytest.mark.parametrize("units", [0, 0.0])
def test_zero_units_never_derive_a_unit_figure(units: float) -> None:
    mapping = {"PN": "raw_part_number_token", "Stuks": "units_sold", "Omset": "total_sell_amount", "Voorraad": "reported_soh"}
    res = _parse(_csv(["PN", "Stuks", "Omset", "Voorraad"], [["A", units, 80, 1]]), mapping)
    assert res.rows[0]["unit_sell_price"] is None


def test_a_layout_that_maps_only_the_customers_product_code_stages_its_rows() -> None:
    mapping = {"Kode": "raw_article_token", "Stuks": "units_sold", "Voorraad": "reported_soh"}
    res = _parse(_csv(["Kode", "Stuks", "Voorraad"], [["ART-7", 3, 20], [None, 2, 5]]), mapping)
    assert res.error is None
    assert [(r["raw_article_token"], r["raw_product_token"]) for r in res.rows] == [("ART-7", None)]
    assert res.skipped_rows == {"missing_product_or_units": 1}


# --- N-0111 (Warren 2026-10-19): several columns mapped to one identifier target --------------------

EAN_UPC = {
    "EAN": "raw_barcode_token",
    "UPC": "raw_barcode_token",
    "ModelNumber": "raw_sales_model_token",
    "ASIN": "raw_article_token",
    "Units": "units_sold",
}


def test_ean_and_upc_both_mapped_to_barcode_use_the_first_one_that_has_a_value() -> None:
    res = _parse(
        _csv(
            ["EAN", "UPC", "ModelNumber", "ASIN", "Units"],
            [
                ["4711000000011", "", "X1", "B0A", 2],  # EAN present
                ["", "123456789012", "X1", "B0B", 3],  # only the UPC: used as the barcode
                ["", "", "X1", "B0C", 4],  # neither: still staged on its sales model
            ],
        ),
        EAN_UPC,
    )
    assert res.error is None and len(res.rows) == 3
    assert [r["raw_barcode_token"] for r in res.rows] == ["4711000000011", "123456789012", None]
    assert all(r["raw_sales_model_token"] == "X1" for r in res.rows)


def test_the_barcode_column_that_comes_first_in_the_file_wins_when_both_are_filled() -> None:
    mapping = {**EAN_UPC}
    swapped = _parse(
        _csv(["UPC", "EAN", "ModelNumber", "ASIN", "Units"], [["123456789012", "4711000000011", "X1", "B0A", 2]]),
        mapping,
    )
    assert swapped.rows[0]["raw_barcode_token"] == "123456789012"


def test_a_row_with_only_a_upc_is_staged_even_when_the_ean_column_is_the_resolved_one() -> None:
    # Previously the later header overwrote the earlier one and the empty column hid the value.
    res = _parse(_csv(["EAN", "UPC", "Units"], [["", "123456789012", 5]]), {"EAN": "raw_barcode_token", "UPC": "raw_barcode_token", "Units": "units_sold"})
    assert res.error is None and len(res.rows) == 1
    assert res.rows[0]["raw_barcode_token"] == "123456789012"
