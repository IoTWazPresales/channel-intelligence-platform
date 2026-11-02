"""GOV-008 M3: a migrated v1 saved report exports and delivers exactly the rows the v1 report shows."""
from types import SimpleNamespace

import pytest


def _definition(*, migrated: bool):
    from app.services.dashboard_definitions import check_definition, definition_from_v1
    if migrated:
        checked, _visual = definition_from_v1(
            metric_key="sellout_units", grains=["product"], filters={}, period_grain=None,
            visual="table", tenant_id="default", at="2026-11-02T00:00:00Z",
        )
        return checked.definition
    return check_definition({"query": {"measures": ["dsi_sellout.units"], "breakdowns": ["product"]}},
                            tenant_id="default").definition


def _fake_execute(rows):
    async def execute_query(db, **kwargs):
        payload = {"ok": True, "status": "ok", "rows": list(rows), "value": sum(r["value"] for r in rows),
                   "data_vintage": {"as_of_utc": "2026-11-02T00:00:00+00:00"}}
        return SimpleNamespace(ok=True, as_dict=lambda: dict(payload))
    return execute_query


# The review's probe: 522 groups, v1 order is by product id ascending (not value descending).
ROWS = [{"product_id": i, "value": 1000 - (i % 7) * 3} for i in range(522)]


@pytest.mark.anyio
async def test_migrated_v1_report_keeps_all_522_rows_in_v1_order(monkeypatch):
    from app.services import report_delivery
    monkeypatch.setattr(report_delivery, "execute_query", _fake_execute(ROWS))
    definition = _definition(migrated=True)
    assert definition.get("migrated_from") and definition["v1_equivalent"]
    report = SimpleNamespace(definition_v2=definition, metric_key="sellout_units", grains=["product"],
                             filters={}, tenant_id="default", period_grain=None)
    payload = await report_delivery.saved_report_payload(None, report)
    assert [r["product_id"] for r in payload["rows"]] == list(range(522))
    assert not payload.get("truncated")
    assert payload["value"] == sum(r["value"] for r in ROWS)


@pytest.mark.anyio
async def test_v2_defined_equivalent_report_still_gets_the_v2_cap(monkeypatch):
    """Control: only migrated rows are exempt; a v2-authored v1-equivalent definition keeps its cap."""
    from app.services import report_delivery
    monkeypatch.setattr(report_delivery, "execute_query", _fake_execute(ROWS))
    definition = _definition(migrated=False)
    assert definition["v1_equivalent"] and not definition.get("migrated_from")
    report = SimpleNamespace(definition_v2=definition, metric_key="sellout_units", grains=["product"],
                             filters={}, tenant_id="default", period_grain=None)
    payload = await report_delivery.saved_report_payload(None, report)
    assert len(payload["rows"]) == 500 and payload["truncated"] is True
