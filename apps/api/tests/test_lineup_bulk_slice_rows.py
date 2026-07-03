"""Unit tests for bulk lineup slice row → parser source_row_number mapping."""

from __future__ import annotations

import io

import pandas as pd

from app.services.commercial_planner.lineup_bulk_slice_rows import (
    map_slice_rows_to_source_row_numbers,
    row_match_key,
)


def _minimal_xlsx(rows: list[list]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="NB", index=False, header=False)
    return buf.getvalue()


def test_map_slice_rows_to_parser_source_row_numbers():
    xlsx = _minimal_xlsx(
        [
            ["SKU", "Qty", "Customer"],
            ["sku-a", "10", "Amazon"],
            ["sku-b", "5", "Amazon"],
        ]
    )
    from app.services.commercial_planner.lineup_bulk_slice_rows import parser_row_dicts_for_sheet

    ctx = {
        "product_map": {},
        "customer_map": {},
        "distributor_map": {},
        "customer_alias_map": {},
        "customers_by_id": {},
    }
    parser_rows = parser_row_dicts_for_sheet("t.xlsx", xlsx, sheet_name="NB", parser_ctx=ctx)
    slice_rows = [
        {"sku_raw": "sku-a", "quantity_units": 10, "customer_token": "Amazon"},
    ]
    nums = map_slice_rows_to_source_row_numbers(slice_rows, parser_rows)
    assert nums == [1]
    assert row_match_key(slice_rows[0]) == row_match_key(parser_rows[0])
