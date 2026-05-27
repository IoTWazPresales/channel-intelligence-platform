"""Unit tests for DSI fact source_key builders."""

from __future__ import annotations

from datetime import date

from app.services.imports.dsi_fact_source_keys import (
    dsi_inventory_source_key,
    dsi_reconciliation_source_key,
    dsi_return_source_key,
    dsi_sellout_source_key,
    normalize_dsi_invoice_no,
)


def test_normalize_dsi_invoice_no_empty_sentinel() -> None:
    assert normalize_dsi_invoice_no(None) == ""
    assert normalize_dsi_invoice_no("") == ""
    assert normalize_dsi_invoice_no("   ") == ""


def test_sellout_source_key_stable_with_empty_invoice() -> None:
    tx = date(2024, 6, 1)
    a = dsi_sellout_source_key(
        distributor_id=1,
        product_id=2,
        customer_id=3,
        transaction_date=tx,
        invoice_no=None,
    )
    b = dsi_sellout_source_key(
        distributor_id=1,
        product_id=2,
        customer_id=3,
        transaction_date=tx,
        invoice_no="",
    )
    assert a == b
    assert a.startswith("dsi-sellout:")


def test_return_and_sellout_share_grain_different_prefix() -> None:
    tx = date(2024, 6, 2)
    sell = dsi_sellout_source_key(
        distributor_id=10,
        product_id=20,
        customer_id=30,
        transaction_date=tx,
        invoice_no="INV-1",
    )
    ret = dsi_return_source_key(
        distributor_id=10,
        product_id=20,
        customer_id=30,
        transaction_date=tx,
        invoice_no="INV-1",
    )
    assert sell != ret
    assert ret.startswith("dsi-return:")
    assert sell.startswith("dsi-sellout:")


def test_two_invoices_same_day_distinct_keys() -> None:
    tx = date(2024, 6, 3)
    k1 = dsi_sellout_source_key(
        distributor_id=1,
        product_id=1,
        customer_id=1,
        transaction_date=tx,
        invoice_no="A",
    )
    k2 = dsi_sellout_source_key(
        distributor_id=1,
        product_id=1,
        customer_id=1,
        transaction_date=tx,
        invoice_no="B",
    )
    assert k1 != k2


def test_inventory_source_key_format() -> None:
    assert dsi_inventory_source_key(distributor_id=5, product_id=9, as_of_date=date(2024, 1, 15)) == (
        "dsi-soh:5:9:2024-01-15"
    )


def test_reconciliation_source_key_customer_and_open_channel() -> None:
    pe = date(2024, 6, 30)
    assert dsi_reconciliation_source_key(
        distributor_id=1, product_id=2, customer_id=42, period_end_date=pe
    ) == "dsi-recon:1:2:42:2024-06-30"
    assert dsi_reconciliation_source_key(
        distributor_id=1, product_id=2, customer_id=None, period_end_date=pe
    ) == "dsi-recon:1:2:0:2024-06-30"
