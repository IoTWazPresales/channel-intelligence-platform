"""Unit tests for CST unit ↔ total derivation (generic)."""

from __future__ import annotations

from app.services.imports.parsers.customer_sell_through_measures import apply_unit_total_derivation


def test_derive_unit_sell_from_total() -> None:
    row = {
        "raw_row_payload": {},
        "units_sold": 10.0,
        "unit_sell_price": None,
        "total_sell_amount": 1500.0,
    }
    apply_unit_total_derivation(row)
    assert row["unit_sell_price"] == 150.0
    assert "total_sell_amount" not in row
    assert row["raw_row_payload"]["_cst_derived"]["unit_sell_price_from_total"] is True
    assert row["raw_row_payload"]["_cst_derived"]["total_sell_amount"] == 1500.0


def test_derive_total_cost_from_unit() -> None:
    row = {
        "raw_row_payload": {},
        "units_sold": 4.0,
        "unit_cost": 25.0,
        "total_cost_amount": None,
    }
    apply_unit_total_derivation(row)
    assert row["unit_cost"] == 25.0
    assert row["raw_row_payload"]["_cst_derived"]["total_cost_amount"] == 100.0
    assert row["raw_row_payload"]["_cst_derived"]["total_cost_amount_from_unit"] is True


def test_derive_unit_mac_from_soh_value() -> None:
    row = {
        "raw_row_payload": {},
        "units_sold": 1.0,
        "reported_soh": 5.0,
        "total_soh_value": 500.0,
        "unit_mac": None,
        "unit_cost": None,
    }
    apply_unit_total_derivation(row)
    assert row["unit_mac"] == 100.0
    assert row["unit_cost"] == 100.0


def test_zero_qty_does_not_divide() -> None:
    row = {
        "raw_row_payload": {},
        "units_sold": 0.0,
        "total_sell_amount": 100.0,
        "unit_sell_price": None,
    }
    apply_unit_total_derivation(row)
    assert row["unit_sell_price"] is None
