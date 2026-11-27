"""T1b: the supply overview runs its independent reads together and counts POs in SQL.

Before: current database, headline, last import, PO-by-distributor, plan-unit coverage and the PO
totals ran one after another on one session; the PO totals came from ``po_management.coverage``,
which reads every (PO, product) group of every live shipment line, builds per-quarter groups in
Python and returns totals nobody here needs. Now: the five reads overlap (``gather_reads``) and the
PO totals are two distinct counts in one statement. Numbers are unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.services import supply_overview as mod


@pytest.fixture(autouse=True)
def _tenant_reporting_timezone(monkeypatch):
    # Warren 2026-11-27 decisions: the reporting timezone comes from the tenant profile.
    monkeypatch.setattr(mod, "reporting_timezone", lambda _tenant: "Europe/London")


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def test_po_totals_are_two_distinct_counts_not_a_group_load() -> None:
    sql = _sql(mod.po_totals_stmt()).lower()
    assert sql.count("count(distinct fact_inbound_shipment.purchase_order_id)") == 2
    assert "filter (where" in sql
    assert "group by" not in sql
    assert "purchase_order_id is not null" in sql and "product_id is not null" in sql
    assert "commercial_lineup_case_po" in sql and "superseded_by_case_id is null" in sql


class _Mappings:
    def __init__(self, rows):
        self._rows = rows

    def one(self):
        return self._rows[0]

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _Result:
    def __init__(self, rows=(), scalar=None):
        self._rows, self._scalar = list(rows), scalar

    def scalar(self):
        return self._scalar

    def mappings(self):
        return _Mappings(self._rows)

    def one(self):
        return self._rows[0]

    def all(self):
        return list(self._rows)


HEADLINE = {
    "tenant_id": "default",
    "open_lines": 10,
    "open_units": 55.5,
    "eta_past_no_pod_lines": 2,
    "oldest_eta_past": date(2098, 1, 2),
    "oldest_days_past_eta": 30,
    "landed_pod_iso_week": 3,
    "landed_lines": 7,
    "landed_units": 70,
    "pipeline_lines": 4,
    "pipeline_units": 40,
    "shipped_lines": 3,
    "shipped_units": 30,
    "arrived_lines": 1,
    "arrived_units": 5,
    "overdue_commercial_lines": 1,
}


class _Db:
    def __init__(self, *, fail_headline=False):
        self.fail_headline = fail_headline
        self.sql: list[str] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.sql.append(sql)
        if "current_database" in sql:
            return _Result(scalar="cip_test")
        if "WITH twin_rem" in sql:
            if self.fail_headline:
                raise RuntimeError("boom")
            return _Result([HEADLINE])
        if "FROM import_job" in sql:
            return _Result([{"file_name": "f.xlsx", "created_at": datetime(2098, 1, 1, tzinfo=timezone.utc), "status": "done", "stage": "applied"}])
        if "FROM purchase_order po" in sql:
            return _Result([{"distributor": "Dist A", "observed_pos": 4, "linked_pos": 1}])
        if "commercial_lineup_line" in sql:
            return _Result([(7, "Dist A", 100, 40)])
        if "count(DISTINCT" in sql:
            return _Result([(8, 2)])
        raise AssertionError(f"unexpected statement: {sql[:200]}")


def test_overview_numbers_and_shape_are_unchanged() -> None:
    out = asyncio.run(mod.supply_overview(_Db(), {"tenant_id": "default"}))
    assert out["database"] == "cip_test" and out["data_unavailable"] is False
    assert (out["open_lines"], out["open_units"]) == (10, 55.5)
    assert out["oldest_eta_past"] == "2098-01-02" and out["oldest_days_past_eta"] == 30
    assert out["po_observed"] == 8 and out["po_linked"] == 2 and out["po_coverage_ratio"] == 0.25
    assert out["po_data_unavailable"] is False
    assert out["po_by_distributor"] == [{"distributor": "Dist A", "observed_pos": 4, "linked_pos": 1, "covered": 0.25}]
    assert out["plan_unit_po_by_distributor"][0]["backlog_units"] == 60.0
    assert out["captions"]["po_coverage"].startswith("2 of 8 purchase orders linked")
    assert "Last shipment file f.xlsx (applied, 2098-01-01T00:00:00+00:00)" in out["captions"]["landed_pod_iso_week"]


def test_the_five_reads_are_issued_together(monkeypatch) -> None:
    seen: list[int] = []
    real = mod.gather_reads

    async def spy(db, *readers):
        seen.append(len(readers))
        return await real(db, *readers)

    monkeypatch.setattr(mod, "gather_reads", spy)
    asyncio.run(mod.supply_overview(_Db(), {"tenant_id": "default"}))
    assert seen == [5]


def test_a_failed_headline_still_returns_the_empty_overview(caplog) -> None:
    with caplog.at_level(logging.ERROR):
        out = asyncio.run(mod.supply_overview(_Db(fail_headline=True), {"tenant_id": "default"}))
    assert out["data_unavailable"] is True and out["labels"] == {} and out["captions"] == {}
    assert out["database"] == "cip_test"
    assert any("supply overview read failed" in r.message for r in caplog.records)


def test_a_failed_po_total_is_flagged_not_fatal() -> None:
    class Db(_Db):
        async def execute(self, stmt, params=None):
            if "count(DISTINCT" in str(stmt):
                raise RuntimeError("boom")
            return await super().execute(stmt, params)

    out = asyncio.run(mod.supply_overview(Db(), {"tenant_id": "default"}))
    assert out["po_observed"] == 0 and out["po_linked"] == 0
    assert out["po_data_unavailable"] is True and out["po_coverage_ratio"] is None


def test_the_week_and_today_use_the_tenant_reporting_timezone() -> None:
    db = _Db()
    out = asyncio.run(mod.supply_overview(db, {"tenant_id": "default"}))
    headline_sql = next(s for s in db.sql if "WITH twin_rem" in s)
    assert ":reporting_tz" in headline_sql and "Africa/Johannesburg" not in headline_sql
    assert "Europe/London time" in out["captions"]["landed_pod_iso_week"]


def test_an_unset_reporting_timezone_is_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(mod, "reporting_timezone", lambda _tenant: None)
    db = _Db()
    out = asyncio.run(mod.supply_overview(db, {"tenant_id": "default"}))
    assert out["data_unavailable"] is True and out["reporting_timezone_not_configured"] is True
    assert not any("WITH twin_rem" in s for s in db.sql)
