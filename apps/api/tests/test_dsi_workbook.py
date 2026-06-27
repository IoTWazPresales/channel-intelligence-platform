"""DSI multi-sheet workbook helpers."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from app.services.imports.dsi_workbook import (
    DSI_SINGLE_SHEET_KEY,
    build_combined_dsi_dataframe,
    build_dsi_workbook_structure,
    is_nested_dsi_field_mapping,
    load_dsi_workbook_sheet_frames,
)


def test_single_sheet_mapping_unchanged_shape() -> None:
    assert is_nested_dsi_field_mapping({"Qty": "quantity_sold", "SKU": "product_identifier"}) is False


def test_nested_mapping_detected() -> None:
    assert is_nested_dsi_field_mapping({"Sheet1": {"Qty": "quantity_sold"}}) is True


def test_two_sheet_workbook_combined_stages_both_canonicals() -> None:
    sell = pd.DataFrame(
        {
            "Dist": ["D1"],
            "SKU": ["P1"],
            "Qty": [5],
            "TxDate": ["2024-01-01"],
            "Cust": ["C1"],
        }
    )
    soh = pd.DataFrame(
        {
            "Dist": ["D1"],
            "SKU": ["P1"],
            "SOH": [100],
            "Snap": ["2024-01-31"],
        }
    )
    frames = [
        (
            "Sellout",
            sell,
            {
                "Dist": "distributor_token",
                "SKU": "product_identifier",
                "Qty": "quantity_sold",
                "TxDate": "transaction_date",
                "Cust": "customer_dealer_token",
            },
        ),
        (
            "SOH",
            soh,
            {
                "Dist": "distributor_token",
                "SKU": "product_identifier",
                "SOH": "stock_on_hand",
                "Snap": "snapshot_date",
            },
        ),
    ]
    combined, mapping, skipped = build_combined_dsi_dataframe(frames)
    assert skipped == []
    assert len(combined) == 2
    assert "quantity_sold" in combined.columns
    assert "stock_on_hand" in combined.columns
    assert mapping["quantity_sold"] == "quantity_sold"
    assert mapping["stock_on_hand"] == "stock_on_hand"


def test_extra_unmapped_sheet_skipped() -> None:
    frames = [
        (
            "Data",
            pd.DataFrame({"Dist": ["D1"], "SKU": ["P1"], "Qty": [1]}),
            {"Dist": "distributor_token", "SKU": "product_identifier", "Qty": "quantity_sold"},
        ),
        ("Notes", pd.DataFrame({"A": ["ignore"]}), {}),
    ]
    _combined, _mapping, skipped = build_combined_dsi_dataframe(frames)
    assert any(s["sheet_name"] == "Notes" for s in skipped)


def test_xlsx_loads_multiple_sheets() -> None:
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        pd.DataFrame({"A": [1]}).to_excel(writer, sheet_name="Sellout", index=False)
        pd.DataFrame({"B": [2]}).to_excel(writer, sheet_name="Inventory", index=False)
    frames = load_dsi_workbook_sheet_frames("test.xlsx", bio.getvalue())
    assert len(frames) == 2
    structure = build_dsi_workbook_structure("test.xlsx", bio.getvalue())
    assert structure["multi_sheet"] is True
    assert structure["sheet_count"] == 2
