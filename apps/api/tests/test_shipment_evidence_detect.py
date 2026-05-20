"""Pure unit tests for shipment evidence report detection (no database)."""

from __future__ import annotations

from app.services.imports.shipment_evidence_report_detect import (
    LINE_OPEN_ORDER,
    LINE_SHIPPED,
    REPORT_ACZA_SHIPPED,
    REPORT_ACZA_UNSHIP,
    REPORT_XXOMRPT0025,
    REPORT_XXOMRPT0027,
    _ean_upc_str,
    detect_report_type,
)


def test_detect_xxomrpt0025() -> None:
    cols = {
        "Operating Unit",
        "Bill To",
        "Delivery No",
        "Invoice Line",
        "Sales Model Name",
        "Item",
    }
    rt, ls = detect_report_type(cols, sheet_name=None, file_name="XXOMRPT0025_Shipment.csv")
    assert rt == REPORT_XXOMRPT0025
    assert ls == LINE_SHIPPED


def test_detect_xxomrpt0027() -> None:
    cols = {"OU NAME", "Bill To", "Order No.", "Order Line", "Item", "Sales Model Name"}
    rt, ls = detect_report_type(cols, sheet_name=None, file_name="order.csv")
    assert rt == REPORT_XXOMRPT0027
    assert ls == LINE_OPEN_ORDER


def test_detect_acza_sheet_names() -> None:
    shipped_cols = {"Bill To", "Ship To", "Delivery No", "Invoice Line", "Sales Model Name", "Item"}
    rt, ls = detect_report_type(shipped_cols, sheet_name="Shipped", file_name="ACZA.xlsx")
    assert rt == REPORT_ACZA_SHIPPED
    assert ls == LINE_SHIPPED

    rt2, ls2 = detect_report_type(set(), sheet_name="Unship", file_name="ACZA.xlsx")
    assert rt2 == REPORT_ACZA_UNSHIP
    assert ls2 == LINE_OPEN_ORDER


def test_ean_upc_float() -> None:
    assert _ean_upc_str(4.711388e12) is not None
    assert _ean_upc_str(4711388000000.0) == "4711388000000"
