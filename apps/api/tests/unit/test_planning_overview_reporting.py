"""Lane A: the /lineup overview and the Execution vs plan screen count reporting customers only.

Warren 2026-11-20: the overview header counts, the Plan units tile, the shipped-vs-plan chart and the
Plan coverage tile (Execution vs plan) use the shared reporting definition
(``app.services.customer_reporting``: reports expected true AND not merged away). Execution vs plan
takes it through the opt-in ``reporting_only`` argument of ``collect_execution_rows``. Rows with no
customer are shown as ONE separate "Unattributed" line: not mixed into a customer, not dropped.

Unit tests only (mocks, no database).

Generic platform rule: nothing here names a customer, retailer, distributor, site or product.
"""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import planning_overview as overview
from app.services.commercial_planner import plan_vs_executed as pve
from sqlalchemy.dialects import postgresql

FLAG = "reports_expected is true"
NOT_MERGED = "merged_into_customer_id is null"


def _sql(stmt: Any) -> str:
    return str(stmt.compile(dialect=postgresql.dialect())).lower()


class _Result:
    def __init__(self, *, scalar=None, scalars=None, mapping=None):
        self._scalar = scalar
        self._scalars = scalars
        self._mapping = mapping

    def scalar(self):
        return self._scalar

    def scalars(self):
        m = MagicMock()
        m.all.return_value = list(self._scalars or [])
        return m

    def mappings(self):
        m = MagicMock()
        m.one.return_value = self._mapping
        return m


def _overview_db(reporting_ids: list[int]) -> MagicMock:
    line_row = {
        "lines": 4,
        "plan_units": 40,
        "sku_ok": 4,
        "terms_ok": 4,
        "dist_ok": 4,
        "cost_ok": 4,
        "not_ready": 0,
    }
    results = [
        _Result(scalar="cip_test"),  # current_database()
        _Result(scalars=reporting_ids),  # reporting customer ids
        _Result(scalar=2),  # case count
        _Result(scalars=["26Q1"]),  # period labels
        _Result(mapping=line_row),  # line scan
        _Result(mapping={"plan_lines": 0, "flagged": 0}),
    ]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=results)
    return db


def _run_overview(db: MagicMock) -> dict[str, Any]:
    execution = {
        "period": "26Q1",
        "fill_rate": None,
        "planned_units_execution": 0.0,
        "shipped_units_in_plan": 0.0,
        "by_customer": [],
    }
    with patch.object(overview, "_shipped_vs_plan", AsyncMock(return_value=execution)):
        return asyncio.run(overview.planning_overview(db, None))


# ---------------------------------------------------------------- overview counts


def test_overview_case_count_and_period_labels_carry_the_reporting_predicate():
    db = _overview_db([7, 9])
    out = _run_overview(db)
    assert out["cases"] == 2
    # statements: 0 current_database (text), 1 reporting ids, 2 case count, 3 period labels
    ids_sql = _sql(db.execute.await_args_list[1].args[0])
    assert FLAG in ids_sql and NOT_MERGED in ids_sql
    for idx in (2, 3):
        sql = _sql(db.execute.await_args_list[idx].args[0])
        assert "exists" in sql, sql
        assert "commercial_lineup_line.customer_id in (select" in sql, sql
        assert FLAG in sql, sql
        assert NOT_MERGED in sql, sql
        # the existing active-case filters are kept
        assert "superseded_by_case_id is null" in sql, sql
        assert "commercial_status not in" in sql, sql


def test_overview_line_scan_is_restricted_to_the_reporting_ids():
    db = _overview_db([7, 9])
    _run_overview(db)
    stmt = db.execute.await_args_list[4].args[0]
    params = db.execute.await_args_list[4].args[1]
    text_sql = str(stmt).lower()
    assert "l.customer_id = any(:reporting_ids)" in text_sql
    assert "l.row_status is distinct from 'superseded'" in text_sql  # existing filter kept
    assert params == {"reporting_ids": [7, 9]}


def test_overview_with_no_reporting_customers_counts_nothing_instead_of_everything():
    db = _overview_db([])
    _run_overview(db)
    params = db.execute.await_args_list[4].args[1]
    assert params == {"reporting_ids": []}


def test_overview_shipped_vs_plan_asks_for_reporting_only_rows():
    collect = AsyncMock(return_value=[])
    cov = AsyncMock(return_value={"groups": []})
    with (
        patch.object(pve, "collect_execution_rows", collect),
        patch.object(pve, "lineup_linked_year_quarters", AsyncMock(return_value=set())),
        patch.object(pve, "periods_from_coverage", MagicMock(return_value=[])),
        patch.object(pve, "resolve_default_period", MagicMock(return_value="26Q1")),
        patch("app.services.commercial_planner.po_management.coverage", cov),
    ):
        out = asyncio.run(overview._shipped_vs_plan(MagicMock()))
    assert collect.await_count == 1
    assert collect.await_args.kwargs["reporting_only"] is True
    assert out["by_customer"] == []


# ---------------------------------------------------------------- chart buckets


def test_customer_less_rows_are_one_separate_unattributed_line():
    rows = [
        {"customer_id": 1, "customer_label": "Acme", "planned_units": 10, "shipped_units": 4},
        {"customer_id": None, "customer_label": "", "planned_units": 3, "shipped_units": 1},
        {"customer_id": None, "customer_label": "Unattributed", "planned_units": 2, "shipped_units": 0},
    ]
    out = overview._customer_plan_shipped(rows)
    unattributed = [r for r in out if r["customer_id"] is None]
    assert len(unattributed) == 1
    assert unattributed[0]["customer"] == "Unattributed"
    assert unattributed[0]["plan"] == 5
    assert unattributed[0]["shipped"] == 1
    acme = next(r for r in out if r["customer"] == "Acme")
    assert acme["plan"] == 10 and acme["shipped"] == 4  # not mixed into a customer


def test_unattributed_line_survives_the_top_customer_cap():
    rows = [
        {"customer_id": n, "customer_label": f"C{n:02d}", "planned_units": 100 + n, "shipped_units": 1}
        for n in range(1, 13)
    ]
    rows.append({"customer_id": None, "customer_label": None, "planned_units": 1, "shipped_units": 0})
    out = overview._customer_plan_shipped(rows)
    assert len(out) == 9  # 8 customers + the one Unattributed line
    assert out[-1]["customer"] == "Unattributed"
    assert out[-1]["customer_id"] is None
    assert all(r["customer_id"] is not None for r in out[:-1])


def test_no_unattributed_line_when_every_row_has_a_customer():
    rows = [{"customer_id": 1, "customer_label": "Acme", "planned_units": 1, "shipped_units": 0}]
    out = overview._customer_plan_shipped(rows)
    assert [r["customer"] for r in out] == ["Acme"]


# ---------------------------------------------------------------- Execution vs plan


def _row(customer_id: int | None, label: str = "x") -> dict[str, Any]:
    return {
        "customer_id": customer_id,
        "customer_label": label,
        "planned_units": 5,
        "shipped_units": 1,
        "product_id": 1,
    }


def test_apply_reporting_only_keeps_reporting_drops_others_keeps_customer_less():
    rows = [_row(1, "Rep"), _row(2, "Other"), _row(None, "")]
    kept = pve.apply_reporting_only(rows, {1})
    assert [r["customer_id"] for r in kept] == [1, None]
    assert kept[1]["customer_label"] == "Unattributed"
    assert rows[2]["customer_label"] == ""  # input rows are not mutated


def test_apply_reporting_only_with_no_reporting_customers_keeps_only_unattributed():
    kept = pve.apply_reporting_only([_row(1), _row(None)], set())
    assert [r["customer_id"] for r in kept] == [None]


def _collect(reporting_only: bool | None, reporting_ids: list[int]) -> list[dict[str, Any]]:
    case = SimpleNamespace(id=11, inferred_period_start=date(2026, 4, 1))
    products = [
        {"customer_id": 1, "planned_units": 5, "shipped_units": 1, "product_id": 1},
        {"customer_id": 2, "planned_units": 6, "shipped_units": 2, "product_id": 2},
        {"customer_id": None, "planned_units": 7, "shipped_units": 3, "product_id": 3},
    ]
    recon = {11: {"customers": [{"customer_id": 1, "label": "Rep"}, {"customer_id": 2, "label": "Other"}], "products": products}}
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result(scalars=reporting_ids))
    kwargs: dict[str, Any] = {}
    if reporting_only is not None:
        kwargs["reporting_only"] = reporting_only
    with (
        patch.object(pve, "_linked_cases", AsyncMock(return_value=[case])),
        patch.object(pve, "reconcile_cases", AsyncMock(return_value=recon)),
        patch.object(pve, "_attach_product_catalog_fields", AsyncMock()),
    ):
        rows = asyncio.run(pve.collect_execution_rows(db, **kwargs))
    return rows


def test_collect_execution_rows_is_unfiltered_by_default():
    rows = _collect(None, [1])
    assert sorted(r["customer_id"] or 0 for r in rows) == [0, 1, 2]


def test_collect_execution_rows_reporting_only_filters_and_keeps_one_unattributed():
    rows = _collect(True, [1])
    by_customer = {r["customer_id"]: r for r in rows}
    assert set(by_customer) == {1, None}
    assert by_customer[1]["customer_label"] == "Rep"
    assert by_customer[None]["customer_label"] == "Unattributed"


def test_reporting_only_reads_the_shared_reporting_definition():
    case = SimpleNamespace(id=11, inferred_period_start=date(2026, 4, 1))
    recon = {11: {"customers": [], "products": [{"customer_id": 1, "planned_units": 5, "shipped_units": 1}]}}
    db = MagicMock()
    db.execute = AsyncMock(return_value=_Result(scalars=[1]))
    with (
        patch.object(pve, "_linked_cases", AsyncMock(return_value=[case])),
        patch.object(pve, "reconcile_cases", AsyncMock(return_value=recon)),
        patch.object(pve, "_attach_product_catalog_fields", AsyncMock()),
    ):
        asyncio.run(pve.collect_execution_rows(db, reporting_only=True))
    sql = _sql(db.execute.await_args.args[0])
    assert FLAG in sql and NOT_MERGED in sql


def test_read_model_passes_reporting_only_to_collect():
    collect = AsyncMock(return_value=[])
    with (
        patch.object(pve, "coverage", AsyncMock(return_value={"groups": []})),
        patch.object(pve, "lineup_linked_year_quarters", AsyncMock(return_value=set())),
        patch.object(pve, "periods_from_coverage", MagicMock(return_value=[])),
        patch.object(pve, "resolve_default_period", MagicMock(return_value="26Q1")),
        patch.object(pve, "collect_execution_rows", collect),
        patch.object(pve, "_load_duplicate_ingestion_samples", AsyncMock(return_value=[])),
        patch.object(pve, "attach_ship_quarters", AsyncMock()),
        patch.object(pve, "customer_labels", AsyncMock(return_value={})),
    ):
        asyncio.run(pve.plan_vs_executed_read_model(MagicMock(), reporting_only=True))
        asyncio.run(pve.plan_vs_executed_read_model(MagicMock()))
    flags = [c.kwargs["reporting_only"] for c in collect.await_args_list]
    assert flags == [True, False]
