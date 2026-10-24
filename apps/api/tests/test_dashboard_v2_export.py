"""Fixed-window download contract plus rolled-back delivery proof on cip_test."""
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from openpyxl import load_workbook

from app.api.v1.endpoints import report_exports
from app.query.model import execute as v2_execute
from app.services.dashboard_definitions import check_definition


@pytest.mark.anyio
@pytest.mark.parametrize("fmt", ["xlsx", "pdf"])
async def test_saved_fixed_window_export_never_runs_the_all_time_v1_query(monkeypatch, fmt):
    fixed = {"from": "2026-01-01", "to": "2026-01-31"}
    definition = check_definition({"query": {"measures": ["dsi_sellout.units"]}, "dashboard": {"fixed_window": fixed}}, tenant_id="default")
    row = SimpleNamespace(tenant_id="default", owner_user_id=1, visibility="personal", shared_roles=[],
                          name="Fixed January", metric_key=definition.v1.metric_key, grains=[], filters={}, definition_v2=definition.definition)
    db = SimpleNamespace(get=AsyncMock(return_value=row))
    v1 = AsyncMock(side_effect=AssertionError("fixed-window download must not use v1"))
    v2 = AsyncMock(return_value={"ok": True, "rows": [], "totals": {"dsi_sellout.units": 13}, "truncated": False,
                                "explain": {"row_count": 0, "data_vintage": {"min": None, "max": None}}})
    monkeypatch.setattr(report_exports, "execute_query", v1)
    monkeypatch.setattr(v2_execute, "run_v2", v2)
    response = await report_exports.export_saved_report(1, format=fmt, db=db, user={"id": 1, "role": "viewer", "tenant_id": "default"})
    body = b"".join([part async for part in response.body_iterator])
    v1.assert_not_awaited()
    req = v2.await_args.args[1]
    assert (req.period_from, req.period_to) == (fixed["from"], fixed["to"])
    if fmt == "xlsx":
        cover = load_workbook(BytesIO(body))["Cover"]
        assert "13" in cover["A4"].value
        assert fixed["from"] in cover["A7"].value and fixed["to"] in cover["A7"].value
    else:
        assert body.startswith(b"%PDF") and b"2026-01-31" in body


@pytest.mark.anyio
async def test_fixed_window_delivery_excludes_outside_dates_on_cip_test(monkeypatch):
    import secrets
    from datetime import date
    from sqlalchemy import text
    from app.db.session import AsyncSessionLocal
    from app.models.dimensions import DimCustomer, DimProduct
    from app.models.facts import FactSalesSellout
    from app.models.iam import Tenant
    from app.models.saved_reports import SavedReport
    from app.query.cache import clear_query_cache
    from app.services.report_delivery import deliver_saved_report

    tag = secrets.token_hex(4)
    tid = f"n0116-fixed-{tag}"
    async with AsyncSessionLocal() as db:
        if (await db.execute(text('select current_database()'))).scalar_one() != 'cip_test':
            pytest.skip('cip_test only')
        try:
            monkeypatch.setattr(db, 'commit', db.flush)
            db.add(Tenant(id=tid, name='Fixed-window test tenant'))
            await db.flush()
            product = DimProduct(sku=f'n0116-fixed-{tag}', name='Fixed-window test product', tenant_id=tid)
            customer = DimCustomer(code=f'n0116-fixed-{tag}', name='Fixed-window test customer', tenant_id=tid)
            db.add_all([product, customer])
            await db.flush()
            for month, units in [(1, 13), (2, 900)]:
                day = date(2026, month, 5)
                db.add(FactSalesSellout(source_key=f'n0116-fixed-{tag}-{month}', tenant_id=tid, product_id=product.id, customer_id=customer.id,
                                       transaction_date=day, period_start=day, units=units, revenue=0))
            fixed = {'from': '2026-01-01', 'to': '2026-01-31'}
            checked = check_definition({'query': {'measures': ['dsi_sellout.units']}, 'dashboard': {'fixed_window': fixed}}, tenant_id=tid)
            report = SavedReport(tenant_id=tid, name='Fixed January delivery', visual='kpi', metric_key=checked.v1.metric_key,
                                 grains=[], filters={}, definition_v2=checked.definition)
            db.add(report)
            await db.flush()
            delivery = await deliver_saved_report(db, report=report, user=None, skip_cache=True)
            assert delivery.status == 'delivered' and float(delivery.value_preview) == 13
            assert delivery.data_vintage['period'] == fixed
        finally:
            await db.rollback()
            clear_query_cache()
