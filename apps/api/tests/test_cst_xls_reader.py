"""CST workbook reader accepts legacy .xls via xlrd (parity with DSI)."""

from pathlib import Path

import pytest

from app.services.imports.parsers.customer_sell_through_flat import (
    _excel_engine_for_filename,
    _read_workbook_sheets,
)


def test_excel_engine_selects_xlrd_for_xls():
    assert _excel_engine_for_filename("report.XLS") == "xlrd"
    assert _excel_engine_for_filename("report.xlsx") == "openpyxl"
    assert _excel_engine_for_filename("report.csv") is None


def test_read_workbook_sheets_native_xls_if_fixture_present():
    """Optional live fixture — skip when OneDrive sample not on this machine."""
    candidates = [
        Path(r"C:\Users\warren_eliason\OneDrive - ASUS\ACZA Consumer - Sales\Retail\Client RAW Report\Makro\Dispo.XLSX"),
    ]
    # Prefer a true OLE .xls (xlrd). Many Makro files are mis-suffixed xlsx.
    root = Path(r"C:\Users\warren_eliason\OneDrive - ASUS\ACZA Consumer - Sales\Retail\Client RAW Report\Makro")
    if root.is_dir():
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() == ".xls" and p.stat().st_size < 3_000_000:
                candidates.insert(0, p)
                break

    path = next((p for p in candidates if p.is_file()), None)
    if path is None:
        pytest.skip("No Makro .xls sample available")

    data = path.read_bytes()
    # OLE Compound Document magic — true .xls
    if not data[:8].startswith(b"\xd0\xcf\x11\xe0"):
        pytest.skip(f"{path.name} is not OLE .xls (likely xlsx with .xls suffix)")

    sheets = _read_workbook_sheets(data, path.name)
    assert sheets
    assert sheets[0][1] is not None
    assert len(sheets[0][1].columns) >= 1
