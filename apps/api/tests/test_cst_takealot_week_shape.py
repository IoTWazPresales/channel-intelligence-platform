"""N-0096 Part B: a one-week Takealot report lands in its one week.

The files carry both ``Transaction Week`` (the Monday of the one reported week) and ``Transaction
Month`` (``2025-12``, ``2026-01``). When the week crosses a month end, every product that sold on
both sides appears twice in the SAME week, once per calendar month, each row holding that month's
share of the week. Barcode, Product ID and the stock figure repeat on both halves. The month is not
a second period and must never become one. Shape taken from cip loads 1648, 1650, 1651 and 1652
(ASUS WEEK 31, 01, 14, 27); no data is read from them here.
"""

from __future__ import annotations

import io
from datetime import date

import pandas as pd
import pytest

from app.services.imports.parsers.customer_sell_through_flat import parse_flat_report

# The mapping the Takealot loads on cip used (import_job.field_mapping).
FIELD_MAPPING = {
    "sales": "units_sold",
    "Barcode": "raw_product_token",
    "Product ID": "listing_external_id",
    "Transaction Week": "raw_period_ref",
}


def _workbook(week: str, halves: list[tuple[str, list[tuple[int, int]]]]) -> bytes:
    """halves: [(transaction_month, [(barcode, units), ...]), ...] all inside one transaction week."""
    rows = []
    for month, items in halves:
        for barcode, units in items:
            rows.append(
                {
                    "Transaction Week": pd.Timestamp(week),
                    "Transaction Month": month,
                    "Barcode": barcode,
                    "Product ID": f" 222 {barcode % 1000:03d} 035",
                    "Tsin Title": f"Asus product {barcode}",
                    "Brand Name": "ASUS",
                    "sales": units,
                }
            )
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False, sheet_name="Sheet1")
    return buf.getvalue()


@pytest.mark.parametrize(
    "week,filename,halves",
    [
        # Mon 2025-12-29 .. Sun 2026-01-04: December and January share ISO week 1 of 2026.
        ("2025-12-29", "ASUS WEEK 01.xlsx", [("2025-12", [(4711387849071, 2), (4711387114063, 3)]), ("2026-01", [(4711387849071, 4), (4711387559666, 1)])]),
        # Mon 2026-07-27 .. Sun 2026-08-02: July and August.
        ("2026-07-27", "ASUS WEEK 31.xlsx", [("2026-07", [(4711387849071, 20)]), ("2026-08", [(4711387849071, 5), (4711636007108, 2)])]),
        # A week that does not cross a month end: one half only.
        ("2025-09-22", "ASUS WEEK 39.xlsx", [("2025-09", [(4711387849071, 7)])]),
    ],
)
def test_a_one_week_file_lands_in_its_one_week_whatever_the_month_column_says(week, filename, halves):
    result = parse_flat_report(_workbook(week, halves), filename, dict(FIELD_MAPPING), 1)
    assert result.error is None, result.error
    expected_units = sum(units for _month, items in halves for _bc, units in items)
    assert sum(float(r["units_sold"]) for r in result.rows) == expected_units  # no half is dropped
    assert len(result.rows) == sum(len(items) for _m, items in halves)

    monday = date.fromisoformat(week)
    assert {r["period_start_date"] for r in result.rows} == {monday}
    assert {r["period_grain"] for r in result.rows} == {"week"}
    assert {r["period_type"] for r in result.rows} == {"weekly"}
    assert {r["week_start_date"] for r in result.rows} == {monday}  # the week is dated, from the file's own column
    assert result.period_start_date == monday
    # the month column is kept as source data, never turned into a period
    assert not any(str(r["period_start_date"]).startswith(("2026-01", "2026-08", "2026-04")) for r in result.rows)
    months = {r["raw_row_payload"]["Transaction Month"] for r in result.rows}
    assert months == {m for m, _items in halves}


def test_the_month_column_is_never_picked_as_the_period_even_when_the_week_column_is_unmapped():
    """With no mapping for the week column, the file name states the week; Transaction Month ('2026-01')
    must not be read as a date (it would land on the Monday before 1 January)."""
    halves = [("2025-12", [(4711387849071, 2)]), ("2026-01", [(4711387849071, 4)])]
    result = parse_flat_report(
        _workbook("2025-12-29", halves),
        "ASUS WEEK 01.xlsx",
        {"sales": "units_sold", "Barcode": "raw_product_token"},
        1,
    )
    assert result.error is None, result.error
    assert {r["period_start_date"] for r in result.rows} == {date(2025, 12, 29)}
    assert {r["period_type"] for r in result.rows} == {"weekly"}
