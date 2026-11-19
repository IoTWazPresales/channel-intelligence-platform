"""T1b: sharing the heavy read between widget calls leaves every number unchanged (cip_test).

Read-only. A2: each metric through the handler (shared roll-up) equals the same totals read directly
from ``build_portfolio_intelligence``; a second call is served from the shared load and still equal.
A1: the handler's scorecard equals the read model's own scorecard for the same filters.
Real session inside an outer transaction rolled back at the end (``tests/rolled_back_async_session.py``).

Not run by the author: the coordinator runs it on cip_test.
"""

from __future__ import annotations

import asyncio

import pytest
from app.query import shared_reads
from app.query.handlers import a1_pve, a2_cpor
from app.query.types import QueryRequest
from app.services.commercial_planner.plan_vs_executed import plan_vs_executed_read_model
from app.services.cpor.portfolio_intelligence import build_portfolio_intelligence
from tests.rolled_back_async_session import rolled_back_async_session

TENANT = "default"


@pytest.fixture(autouse=True)
def _clean():
    shared_reads.clear_shared_reads()
    yield
    shared_reads.clear_shared_reads()


@pytest.mark.anyio
async def test_a2_shared_roll_up_equals_the_direct_roll_up():
    async with rolled_back_async_session() as db:
        direct = await db.run_sync(
            build_portfolio_intelligence, tenant_id=TENANT, customer_id=None, bu=None, include_incremental=False
        )
        totals = direct.get("totals") or {}
        expected = {
            "support_spend": totals.get("support_usd"),
            "delivery_rate": totals.get("delivery_rate"),
            "support_cost_per_unit_sold": totals.get("support_per_unit_sold_usd"),
        }
        for _ in range(2):  # the second round is served from the shared load
            for metric, want in expected.items():
                req = QueryRequest(metric=metric, grains=[], filters={}, tenant_id=TENANT)
                res = await a2_cpor.handle_a2(db, req, metric_key=metric)
                assert res.status == "ok"
                assert res.value == want, metric
                assert res.scorecard == totals


@pytest.mark.anyio
async def test_a1_shared_read_model_scorecard_equals_the_direct_read():
    async with rolled_back_async_session() as db:
        direct = await plan_vs_executed_read_model(db, period_from=None, period_to=None, product_line=None, drill_bu=None)
        if direct.get("data_unavailable"):
            pytest.skip("no plan-vs-executed data in this database")
        req = QueryRequest(metric="fill_rate", grains=[], filters={}, tenant_id=TENANT)
        first = await a1_pve.handle_a1(db, req, metric_key="fill_rate")
        second = await a1_pve.handle_a1(db, req, metric_key="fill_rate")
        assert first.scorecard == (direct.get("scorecard") or {})
        assert second.scorecard == first.scorecard
        assert second.value == first.value
        await asyncio.sleep(0)
