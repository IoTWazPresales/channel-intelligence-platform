"""GOV-008 minor: the CPOR, lineup and promo spreadsheets and the lineup CSV get the report export's formula guard.

A text cell that starts like a formula must be stored as the exact text (cell type ``s``), never as a formula (``f``).
"""

from __future__ import annotations

import asyncio
import csv
import io
from datetime import date
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from openpyxl import load_workbook

EVIL = '=HYPERLINK("http://example.invalid","x")'


def _text_cells(data: bytes, wanted: str = "=HYPERLINK"):
    wb = load_workbook(BytesIO(data))
    return [c for ws in wb for row in ws.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith(wanted)]


def test_cpor_case_workbook_stores_a_formula_looking_name_as_text():
    from app.services.cpor.export_xlsx import build_cpor_case_workbook_bytes

    case = SimpleNamespace(id=1, case_code="C26C99999", case_name=EVIL, customer_id=7, promotion_type="+cmd",
                           window_start=date(2026, 1, 1), window_end=date(2026, 1, 31), status="proposed", export_version=1,
                           roe_snapshot=18.5)
    line = SimpleNamespace(id=1, case_id=1, product_id=9, distributor_id=None, pod_quarter="26Q1", soh_snapshot=10, srp=13999,
                           vat_rate=0.15, dealer_margin_pct=0.15, dealer_price=10347.09, cost_basis=9585.07, cost_source="manual",
                           cost_evidence_json={"flags": []}, support_unit=250.96, estimate_qty=20, cap_qty=None, ttl_support=5019.2,
                           support_usd=13.5654, ttl_support_usd=271.308, result_qty=49, ttl_result=12297.18, ttl_result_usd=664.7124,
                           remark="@SUM(A1)")
    cust = SimpleNamespace(id=7, code="EV", name="Evetech")
    prod = SimpleNamespace(id=9, sku="SKU-1", name=EVIL, product_line="NB")
    session = MagicMock()
    session.get = MagicMock(side_effect=lambda model, pk: case if pk == 1 else cust)
    session.scalars = MagicMock(side_effect=[MagicMock(all=MagicMock(return_value=[line])), MagicMock(all=MagicMock(return_value=[prod]))])
    data, _digest, _meta = build_cpor_case_workbook_bytes(session, 1)
    cells = _text_cells(data)
    assert cells, "the formula-looking name must be in the file"
    assert all(c.data_type == "s" for c in cells), [(c.coordinate, c.data_type) for c in cells]
    wb = load_workbook(BytesIO(data))
    assert not [c for ws in wb for row in ws.iter_rows() for c in row if c.data_type == "f"], "no formula cell may be written"
    # Numbers stay numbers.
    assert any(isinstance(c.value, (int, float)) for c in wb["Reseller"][2])


def test_lineup_customer_slice_stores_feedback_as_text():
    from app.services.commercial_planner.lineup_customer_export import build_customer_lineup_slice_xlsx

    line = SimpleNamespace(quantity_units=10, msrp_local=1150, sku_raw="SKU-ALPHA-01", model_raw="ModelX", calc_dap_cost_currency=39.6,
                           calc_profit_total=None, pricing_chain_json={"inputs": {}, "outputs": {}}, customer_feedback=EVIL)
    db = MagicMock()
    case = SimpleNamespace(period_label="26Q1", product_line="NB", iteration_number=2, currency_code="ZAR")
    customer = SimpleNamespace(id=1001, code="CUST-1001", name="Acme")
    db.get = AsyncMock(side_effect=[case, customer])
    result = MagicMock()
    result.all.return_value = [(line, "SKU-ALPHA-01", "Alpha NB", "ModelX", "Disti A")]
    db.execute = AsyncMock(return_value=result)
    data, _name, n = asyncio.run(build_customer_lineup_slice_xlsx(db, 7, 1001))
    assert n == 1
    cells = _text_cells(data)
    assert cells and all(c.data_type == "s" for c in cells)


def test_lineup_net_requirement_workbook_and_csv_guard_the_business_unit():
    from app.services.lineup.export_apply import net_requirement_to_csv, net_requirement_to_xlsx_bytes

    payload = {"rows": [{"distributor_id": 1, "product_id": 2, "business_unit": EVIL, "net_requirement": -5}]}
    cells = _text_cells(net_requirement_to_xlsx_bytes(payload))
    assert cells and all(c.data_type == "s" for c in cells)
    rows = list(csv.reader(io.StringIO(net_requirement_to_csv(payload))))
    assert rows[1][2] == "'" + EVIL  # guarded text
    assert rows[1][10] == "-5"  # a negative number is not touched


def test_the_shared_helpers():
    from app.services.export_literal_guard import guard_csv_text

    for s in ("=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx"):
        assert guard_csv_text(s) == "'" + s
    assert guard_csv_text("Makro") == "Makro" and guard_csv_text(-5) == -5 and guard_csv_text(None) is None
