"""Warren 2026-11-19: the aged-stock card shows a money value, computed on the API (BACKLOG-254).

Cost source: the customer's reported unit MAC, else unit cost, ex-VAT, SOH-weighted (the CST cost
the SOH check and the CPOR cost suggestion use; ``customer_soh_check`` -> ``soh_unit_cost``).
A line with no cost is counted as "no cost" and is never priced at zero. No database here.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import app.services.store_dc.stock_actions as actions
from app.services.store_dc.stock_actions import summarise_aged_value, value_aged_lines


def _line(pid: int, soh: float | None, *, cid: int = 3, executed: bool = False) -> dict[str, Any]:
    return {
        "customer_id": cid,
        "product_id": pid,
        "stock_on_hand": soh,
        "suggestions": ["promote"],
        "suggestion_executed": executed,
        "executed_actions": ["promote"] if executed else [],
    }


COSTS = {(3, 1): ("unit_mac", 10.0), (3, 2): ("unit_cost", 2.5)}


def _lookup(customer_id: int, product_id: int) -> tuple[str | None, float | None]:
    return COSTS.get((customer_id, product_id), (None, None))


def test_each_line_gets_unit_cost_field_and_stock_value_computed_on_the_api():
    lines = value_aged_lines([_line(1, 4), _line(2, 10)], _lookup)
    assert lines[0]["unit_cost"] == 10.0 and lines[0]["unit_cost_field"] == "unit_mac"
    assert lines[0]["stock_value"] == 40.0
    assert lines[1]["unit_cost_field"] == "unit_cost" and lines[1]["stock_value"] == 25.0


def test_a_line_with_no_cost_has_no_value_never_zero():
    [line] = value_aged_lines([_line(9, 5)], _lookup)
    assert line["unit_cost"] is None and line["stock_value"] is None
    assert line["unit_cost_field"] is None


def test_a_line_with_no_reported_stock_has_no_value():
    [line] = value_aged_lines([_line(1, None)], _lookup)
    assert line["stock_value"] is None


def test_the_cost_is_looked_up_once_per_customer_and_product():
    calls: list[tuple[int, int]] = []

    def counting(cid: int, pid: int):
        calls.append((cid, pid))
        return _lookup(cid, pid)

    value_aged_lines([_line(1, 1), _line(1, 2), _line(1, 3)], counting)
    assert calls == [(3, 1)]


def test_summary_splits_priced_and_unpriced_lines_and_counts_units_for_both():
    lines = value_aged_lines([_line(1, 4), _line(2, 10), _line(9, 5)], _lookup)
    s = summarise_aged_value(lines)["unplanned"]
    assert s["lines"] == 3 and s["units"] == 19.0
    assert s["lines_with_cost"] == 2 and s["lines_without_cost"] == 1
    assert s["value"] == 65.0
    assert s["units_without_cost"] == 5.0


def test_unplanned_summary_leaves_out_lines_with_an_executed_action_but_all_keeps_them():
    lines = value_aged_lines([_line(1, 4), _line(2, 10, executed=True)], _lookup)
    out = summarise_aged_value(lines)
    assert out["unplanned"]["lines"] == 1 and out["unplanned"]["value"] == 40.0
    assert out["all"]["lines"] == 2 and out["all"]["value"] == 65.0


def test_summary_with_only_unpriced_lines_has_no_value_rather_than_zero():
    s = summarise_aged_value(value_aged_lines([_line(9, 5)], _lookup))["unplanned"]
    assert s["value"] is None and s["lines_without_cost"] == 1


def test_summary_states_the_cost_basis():
    basis = summarise_aged_value([])["cost_basis"]
    assert "unit_mac" in basis and "unit_cost" in basis and "ex_vat" in basis


def test_list_aged_stock_prices_only_when_asked(monkeypatch):
    rows = [_line(1, 4), _line(9, 5)]
    monkeypatch.setattr(actions, "build_lead_index", lambda *_a, **_k: {})
    monkeypatch.setattr(
        actions,
        "build_customer_view",
        lambda *_a, **_k: {
            "account": {"site_label": None, "customer_id": 3, "lines": rows},
            "sites": [],
            "dc_sections": [],
        },
    )
    monkeypatch.setattr(actions, "_unit_cost_lookup", lambda _session, **_k: _lookup)
    plain = actions.list_aged_stock(SimpleNamespace(), tenant_id="t", customer_id=3)
    assert "valuation" not in plain and "stock_value" not in plain["lines"][0]
    priced = actions.list_aged_stock(
        SimpleNamespace(), tenant_id="t", customer_id=3, with_value=True, as_of=date(2026, 11, 19)
    )
    assert priced["valuation"]["unplanned"]["value"] == 40.0
    assert priced["valuation"]["unplanned"]["lines_without_cost"] == 1
    assert [ln["stock_value"] for ln in priced["lines"]] == [40.0, None]


def test_the_aged_stock_endpoint_asks_for_the_valuation(monkeypatch):
    from app.api.v1.endpoints import cpor_cases as ep

    seen: dict[str, Any] = {}

    def fake_list(_session, **kwargs):
        seen.update(kwargs)
        return {"lines": [], "truncated": False}

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return None

    monkeypatch.setattr(ep, "list_aged_stock", fake_list)
    monkeypatch.setattr(ep, "SessionLocal", lambda: _Session())
    ep.cpor_aged_stock(customer_id=None, user={"sub": "u", "tenant_id": "tenant-a"})
    assert seen["with_value"] is True and seen["tenant_id"] == "tenant-a"
