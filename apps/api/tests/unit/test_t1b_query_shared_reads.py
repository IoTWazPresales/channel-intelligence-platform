"""T1b: the dashboard's widget calls share the heavy read they have in common.

Six widgets mean six POST /query/execute calls. Each A1 metric re-ran the whole plan-vs-executed
read model for the same filters, and each A2 metric re-ran the portfolio roll-up. The handlers now
share one load per (scope, filters) for the length of the query cache's own TTL.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.my_accounts import request_my_account_ids
from app.query import shared_reads
from app.query.handlers import a1_pve, a2_cpor
from app.query.types import QueryRequest


@pytest.fixture(autouse=True)
def _clean():
    shared_reads.clear_shared_reads()
    yield
    shared_reads.clear_shared_reads()


def test_concurrent_identical_reads_compute_once() -> None:
    calls = 0

    async def compute():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return {"n": calls}

    async def run():
        return await asyncio.gather(
            *(shared_reads.shared_read("pve", {"a": 1}, "t1", compute) for _ in range(6))
        )

    out = asyncio.run(run())
    assert calls == 1
    assert all(o == {"n": 1} for o in out)


def test_different_arguments_tenants_or_namespaces_do_not_share() -> None:
    calls: list[str] = []

    def make(tag):
        async def compute():
            calls.append(tag)
            return tag

        return compute

    async def run():
        return [
            await shared_reads.shared_read("pve", {"a": 1}, "t1", make("a")),
            await shared_reads.shared_read("pve", {"a": 2}, "t1", make("b")),
            await shared_reads.shared_read("pve", {"a": 1}, "t2", make("c")),
            await shared_reads.shared_read("a2", {"a": 1}, "t1", make("d")),
        ]

    assert asyncio.run(run()) == ["a", "b", "c", "d"]


def test_my_accounts_scope_is_part_of_the_key() -> None:
    async def run():
        async def a():
            return "wide"

        async def b():
            return "mine"

        first = await shared_reads.shared_read("pve", {}, "t1", a)
        token = request_my_account_ids.set(frozenset({7}))
        try:
            second = await shared_reads.shared_read("pve", {}, "t1", b)
        finally:
            request_my_account_ids.reset(token)
        return first, second

    assert asyncio.run(run()) == ("wide", "mine")


def test_a_failed_shared_load_falls_back_to_the_callers_own_read() -> None:
    attempts = 0

    async def compute():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("the first caller's session went away")
        return "ok"

    assert asyncio.run(shared_reads.shared_read("pve", {}, "t1", compute)) == "ok"
    assert attempts == 2


def _pve_payload() -> dict:
    return {
        "scorecard": {"fill_rate": 0.8, "line_hit_rate": 0.5, "short_exposure_units": 12},
        "period_range": {"from": "2098Q1", "to": "2098Q1"},
        "drill_rows": [{}, {}],
        "trend": [],
    }


def test_a1_widgets_with_the_same_filters_run_the_read_model_once(monkeypatch) -> None:
    calls = 0

    async def fake_read_model(db, **kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return _pve_payload()

    monkeypatch.setattr(a1_pve, "plan_vs_executed_read_model", fake_read_model)

    def req(metric):
        return QueryRequest(metric=metric, grains=[], filters={"period": "2098Q1"}, tenant_id="t1")

    async def run():
        return await asyncio.gather(
            *(
                a1_pve.handle_a1(object(), req(m), metric_key=m)
                for m in ("fill_rate", "line_hit_rate", "short_exposure", "fill_rate", "line_hit_rate", "short_exposure")
            )
        )

    out = asyncio.run(run())
    assert calls == 1
    assert [r.value for r in out] == [0.8, 0.5, 12, 0.8, 0.5, 12]
    assert all(r.status == "ok" for r in out)


def test_a1_different_filters_still_read_separately(monkeypatch) -> None:
    seen: list[dict] = []

    async def fake_read_model(db, **kwargs):
        seen.append(kwargs)
        return _pve_payload()

    monkeypatch.setattr(a1_pve, "plan_vs_executed_read_model", fake_read_model)

    async def run():
        for bu in (None, "x"):
            await a1_pve.handle_a1(
                object(),
                QueryRequest(metric="fill_rate", grains=[], filters={"bu": bu} if bu else {}, tenant_id="t1"),
                metric_key="fill_rate",
            )

    asyncio.run(run())
    assert [k["product_line"] for k in seen] == [None, "x"]


def test_a2_widgets_with_the_same_filters_run_the_portfolio_roll_up_once(monkeypatch) -> None:
    calls = 0

    class Db:
        async def run_sync(self, fn, **kwargs):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.01)
            return {
                "totals": {"support_usd": 10.0, "delivery_rate": 0.9, "support_per_unit_sold_usd": 0.5},
                "cases_in_scope": 3,
                "lines_included": 9,
            }

    def req(metric):
        return QueryRequest(metric=metric, grains=[], filters={}, tenant_id="t1")

    async def run():
        return await asyncio.gather(
            *(
                a2_cpor.handle_a2(Db(), req(m), metric_key=m)
                for m in ("support_spend", "delivery_rate", "support_cost_per_unit_sold")
            )
        )

    out = asyncio.run(run())
    assert calls == 1
    assert [r.value for r in out] == [10.0, 0.9, 0.5]
