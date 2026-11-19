"""T1a: plan-vs-executed collects once - one batched reconciliation, trend derived from the rows."""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from app.services.commercial_planner import plan_vs_executed as mod


def _recon(case_id: int, *, planned: float, shipped: float) -> dict[str, Any]:
    prod = {
        "product_id": 10,
        "customer_id": 1,
        "product_name": "P",
        "product_line": "NB",
        "business_unit": "NB",
        "planned_units": planned,
        "shipped_units": shipped,
        "pipeline_units": 0.0,
        "units_flag": "matched" if planned == shipped else "short",
        "awaiting_po": False,
        "value": {"planned_value_plan": planned, "shipped_value_cost": shipped},
        "warnings": [],
    }
    return {
        "case_id": case_id,
        "products": [prod],
        "customers": [{"customer_id": 1, "label": "Cust"}],
        "po_flags": [],
        "summary": {},
        "data_unavailable": False,
    }


def _case(case_id: int, start: date | None):
    return SimpleNamespace(id=case_id, inferred_period_start=start)


def test_collect_execution_rows_reconciles_in_range_cases_in_one_batch():
    cases = [
        _case(1, date(2026, 1, 1)),  # 26Q1 - in range
        _case(2, date(2026, 4, 1)),  # 26Q2 - in range
        _case(3, date(2026, 7, 1)),  # 26Q3 - out of range
        _case(4, None),  # undated - skipped
    ]
    batch = AsyncMock(
        return_value={
            1: _recon(1, planned=10, shipped=5),
            2: _recon(2, planned=10, shipped=10),
        }
    )

    async def _run():
        with (
            patch.object(mod, "_linked_cases", AsyncMock(return_value=cases)),
            patch.object(mod, "reconcile_cases", batch),
            patch.object(mod, "_attach_product_catalog_fields", AsyncMock()),
        ):
            return await mod.collect_execution_rows(
                AsyncMock(), period_from="26Q1", period_to="26Q2"
            )

    rows = asyncio.run(_run())
    assert batch.await_count == 1
    assert sorted(batch.await_args.args[1]) == [1, 2]
    assert [(r["case_id"], r["quarter_label"]) for r in rows] == [(1, "26Q1"), (2, "26Q2")]
    assert rows[0]["customer_label"] == "Cust"


def test_collect_execution_rows_skips_unavailable_and_missing_cases():
    cases = [_case(1, date(2026, 1, 1)), _case(2, date(2026, 1, 1)), _case(3, date(2026, 1, 1))]
    unavailable = {**_recon(2, planned=1, shipped=1), "data_unavailable": True}
    batch = AsyncMock(return_value={1: _recon(1, planned=10, shipped=10), 2: unavailable})

    async def _run():
        with (
            patch.object(mod, "_linked_cases", AsyncMock(return_value=cases)),
            patch.object(mod, "reconcile_cases", batch),
            patch.object(mod, "_attach_product_catalog_fields", AsyncMock()),
        ):
            return await mod.collect_execution_rows(AsyncMock())

    rows = asyncio.run(_run())
    assert [r["case_id"] for r in rows] == [1]


def _qrow(label: str, *, planned: float, shipped: float) -> dict[str, Any]:
    r = {**_recon(1, planned=planned, shipped=shipped)["products"][0]}
    r.update(
        case_id=int(label[-1]),
        year=2000 + int(label[:2]),
        quarter=int(label[-1]),
        quarter_label=label,
        customer_label="Cust",
        business_unit_label="NB",
    )
    return r


@pytest.fixture
def _quiet(monkeypatch):
    async def _empty(_db):
        return []

    async def _no_quarters(_db):
        return set()

    async def _noop(_db, rows):
        return None

    monkeypatch.setattr(mod, "_load_duplicate_ingestion_samples", _empty)
    monkeypatch.setattr(mod, "lineup_linked_year_quarters", _no_quarters)
    monkeypatch.setattr(mod, "attach_ship_quarters", _noop)


def test_read_model_collects_once_and_trend_matches_per_quarter_scorecards(_quiet):
    rows = [_qrow("26Q1", planned=10, shipped=5), _qrow("26Q2", planned=10, shipped=10)]
    groups = [
        {
            "year": 2026,
            "quarter": q,
            "quarter_label": f"26Q{q}",
            "status": "linked",
            "linked_po_count": 1,
        }
        for q in (1, 2)
    ]
    collect = AsyncMock(return_value=rows)

    async def _run():
        with (
            patch.object(
                mod,
                "coverage",
                AsyncMock(return_value={"data_unavailable": False, "groups": groups}),
            ),
            patch.object(mod, "collect_execution_rows", collect),
        ):
            return await mod.plan_vs_executed_read_model(
                AsyncMock(), period_from="26Q1", period_to="26Q2"
            )

    out = asyncio.run(_run())
    assert collect.await_count == 1  # trend no longer re-collects (and re-reconciles) per quarter
    by_label = {t["period_label"]: t for t in out["trend"]}
    assert set(by_label) == {"26Q1", "26Q2"}
    assert by_label["26Q1"]["fill_rate"] == pytest.approx(0.5)
    assert by_label["26Q2"]["fill_rate"] == pytest.approx(1.0)
    expected = mod.compute_scorecard_from_execution_rows([rows[0]])
    assert by_label["26Q1"]["planned_units"] == expected["planned_units"]
    assert by_label["26Q1"]["line_hit_rate"] == expected["line_hit_rate"]
    assert by_label["26Q1"]["no_po_planned_units"] == expected["no_po_blind_spot"]["planned_units"]


def test_duplicate_ingestion_audit_overlaps_the_collection_and_runs_once(monkeypatch):
    """The audit is started before the (slow) collection finishes, and only once per request."""
    events: list[str] = []

    async def _audit(_db):
        events.append("audit_started")
        return []

    async def _collect(*_a, **_k):
        await asyncio.sleep(0)  # let the already-scheduled audit task start
        events.append("collect_done")
        return [_qrow("26Q1", planned=10, shipped=5)]

    async def _no_quarters(_db):
        return set()

    async def _noop(_db, rows):
        return None

    monkeypatch.setattr(mod, "_load_duplicate_ingestion_samples", _audit)
    monkeypatch.setattr(mod, "lineup_linked_year_quarters", _no_quarters)
    monkeypatch.setattr(mod, "attach_ship_quarters", _noop)
    monkeypatch.setattr(mod, "collect_execution_rows", _collect)
    groups = [
        {
            "year": 2026,
            "quarter": 1,
            "quarter_label": "26Q1",
            "status": "linked",
            "linked_po_count": 1,
        }
    ]

    async def _run():
        with patch.object(
            mod, "coverage", AsyncMock(return_value={"data_unavailable": False, "groups": groups})
        ):
            return await mod.plan_vs_executed_read_model(
                AsyncMock(), period_from="26Q1", period_to="26Q1"
            )

    asyncio.run(_run())
    assert events == ["audit_started", "collect_done"]
