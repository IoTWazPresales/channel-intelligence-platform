"""T1b: the Brief signals read is bounded (no open-case load, no full-table count) and the slow
sell-through / listing counts are shared, not recomputed by every request."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy.dialects import postgresql

from app.services import brief_signals
from app.services.brief_swr_cache import StaleWhileRevalidate


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_settlement_counts_are_one_aggregate_not_a_case_load() -> None:
    stmt = brief_signals.open_case_fx_counts_stmt(None)
    sql = _sql(stmt).lower()
    assert "count(*)" in sql
    assert "filter (where" in sql
    # no per-case columns come back: the roe/mode tests run inside the database
    assert "cpor_case.id" not in sql.split(" from ")[0]
    assert "cpor_case.status in" in sql


def test_settlement_aggregates_reads_counts_from_one_row() -> None:
    class Result:
        def __init__(self, row=None, scalar=None) -> None:
            self._row, self._scalar = row, scalar

        def one(self):
            return self._row

        def scalar(self):
            return self._scalar

        def scalars(self):  # the old path loaded every open case through here
            raise AssertionError("open cases must not be loaded")

    class Db:
        def __init__(self) -> None:
            self.results = [Result(row=(5, 1, 2)), Result(scalar=7)]

        async def execute(self, _stmt):
            return self.results.pop(0)

    with patch.object(brief_signals, "commercial_planner_enabled", return_value=True):
        out = asyncio.run(brief_signals._settlement_aggregates(Db(), None))
    assert out["open_cases"] == 5
    assert out["fx_blocked_cases"] == 1
    assert out["fx_rate_missing_cases"] == 2
    assert out["missing_assumption_skus"] == 7
    assert out["fx_blocked_zar"] == 0.0
    assert out["data_unavailable"] is False


def test_recon_run_check_is_an_existence_probe_not_a_table_count() -> None:
    sql = _sql(brief_signals.recon_rows_exist_stmt()).lower()
    assert "exists" in sql
    assert "count(" not in sql


def test_swr_concurrent_cold_calls_share_one_load() -> None:
    calls = 0

    async def loader():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return {"n": 1}

    async def run():
        cache = StaleWhileRevalidate(fresh_seconds=300, stale_seconds=1800)
        return await asyncio.gather(*(cache.get("k", loader) for _ in range(5)))

    out = asyncio.run(run())
    assert calls == 1
    assert all(o == {"n": 1} for o in out)


def test_swr_fresh_hit_does_not_load_again() -> None:
    calls = 0

    async def loader():
        nonlocal calls
        calls += 1
        return calls

    async def run():
        cache = StaleWhileRevalidate(fresh_seconds=300, stale_seconds=1800)
        return [await cache.get("k", loader), await cache.get("k", loader)]

    assert asyncio.run(run()) == [1, 1]


def test_swr_stale_value_is_served_while_it_refreshes() -> None:
    clock = SimpleNamespace(t=1000.0)
    calls = 0

    async def loader():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return calls

    async def run():
        cache = StaleWhileRevalidate(fresh_seconds=10, stale_seconds=100, clock=lambda: clock.t)
        first = await cache.get("k", loader)
        clock.t += 50  # past fresh, inside stale
        second = await cache.get("k", loader)  # served from cache, refresh starts behind it
        await asyncio.sleep(0.05)
        third = await cache.get("k", loader)  # refreshed value, now fresh
        return first, second, third

    assert asyncio.run(run()) == (1, 1, 2)
    assert calls == 2


def test_swr_beyond_the_stale_window_waits_for_a_fresh_load() -> None:
    clock = SimpleNamespace(t=0.0)
    calls = 0

    async def loader():
        nonlocal calls
        calls += 1
        return calls

    async def run():
        cache = StaleWhileRevalidate(fresh_seconds=10, stale_seconds=100, clock=lambda: clock.t)
        a = await cache.get("k", loader)
        clock.t += 500
        b = await cache.get("k", loader)
        return a, b

    assert asyncio.run(run()) == (1, 2)


def test_swr_never_caches_a_failed_load() -> None:
    results = iter([None, {"ok": True}])

    async def loader():
        return next(results)

    async def run():
        cache = StaleWhileRevalidate(fresh_seconds=300, stale_seconds=1800)
        return [await cache.get("k", loader), await cache.get("k", loader)]

    assert asyncio.run(run()) == [None, {"ok": True}]


def test_swr_keys_are_independent() -> None:
    async def run():
        cache = StaleWhileRevalidate(fresh_seconds=300, stale_seconds=1800)

        async def a():
            return "a"

        async def b():
            return "b"

        return [await cache.get(("t", ()), a), await cache.get(("t", (1,)), b)]

    assert asyncio.run(run()) == ["a", "b"]
