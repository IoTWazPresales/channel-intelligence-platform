"""One formula guard for every spreadsheet or CSV a user can download (GOV-008 review 2 Nov, minor).

The report export already writes text cells as literal strings (``report_export.build_xlsx_bytes``). The CPOR case workbook, the
lineup workbooks and the lineup CSV took names, labels and user-entered text with no guard, so a cell such as ``=HYPERLINK(...)``
or ``+cmd`` could run as a formula in Excel. These two helpers give them the same rule:

* ``force_text_cells(workbook)``: every string cell is stored as type ``s`` (the exact text, never a formula); numbers, dates,
  booleans and empty cells are left alone.
* ``guard_csv_text(value)``: a string that starts with ``=``, ``+``, ``-``, ``@``, a tab or a carriage return gets a leading
  apostrophe (the same rule as the web CSV export); any other value is returned unchanged.
"""

from __future__ import annotations

from typing import Any

_FORMULA_LEADS = ("=", "+", "-", "@", "\t", "\r")


def force_text_cells(workbook: Any) -> None:
    for worksheet in workbook.worksheets:
        for row in worksheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"


def guard_csv_text(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(_FORMULA_LEADS):
        return "'" + value
    return value
