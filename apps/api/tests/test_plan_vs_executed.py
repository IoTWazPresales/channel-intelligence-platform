"""Unit tests for Plan vs Executed read model (derived-on-read)."""
import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.services.commercial_planner import plan_vs_executed as mod


@pytest.fixture(autouse=True)
def _no_live_duplicate_ingestion_audit(monkeypatch):
    async def _empty(_db):
        return []

    monkeypatch.setattr(mod, "_load_duplicate_ingestion_samples", _empty)


def _cov_for_periods(period_labels: list[str]) -> dict[str, Any]:
    groups = []
    for p in period_labels:
        y = 2000 + int(p[:2])
        q = int(p[-1])
        groups.append(
            {
                "year": y,
                "quarter": q,
                "quarter_label": p,
                "status": "linked",
                "linked_po_count": 1,
            }
        )
    return {"data_unavailable": False, "groups": groups}


def _row(
    *,
    planned: float,
    shipped: float,
    flag: str | None = "matched",
    awaiting_po: bool = False,
    customer_id: int = 1,
    product_id: int = 10,
    value_plan: float = 100.0,
    pipeline: float = 0.0,
) -> dict:
    return {
        "planned_units": planned,
        "shipped_units": shipped,
        "pipeline_units": pipeline,
        "units_flag": flag,
        "awaiting_po": awaiting_po,
        "customer_id": customer_id,
        "product_id": product_id,
        "product_name": f"SKU-{product_id}",
        "product_line": "NB",
        "business_unit": "NB",
        "value": {
            "planned_value_plan": value_plan if planned > 0 else 0,
            "shipped_value_cost": shipped * 10,
            "shipped_value_plan": shipped * 10 if shipped > 0 else 0,
            "value_status": "ok",
        },
    }


def test_fill_rate_over_ship_does_not_reduce_fill_rate():
    """Over-ship capped at plan per line — headline fill rate must not drop."""
    rows = [
        _row(planned=100, shipped=150, flag="over"),
        _row(planned=100, shipped=50, flag="short", customer_id=2, product_id=11),
    ]
    sc = mod.compute_scorecard_from_execution_rows(rows)
    # sum_min = min(150,100) + min(50,100) = 100 + 50 = 150; sum_p = 200
    assert sc["fill_rate"] == 0.75
    assert sc["deal_stock_units"] == 50
    assert sc["short_exposure_units"] == 50


def test_pipeline_excluded_from_fill_included_in_pipeline_tile():
    """open_order (pipeline) inbound must never enter fill; it surfaces as its own tile and
    splits the pending story into inbound/pipeline vs cold."""
    rows = [
        # planned 100, shipped 60 (short), plus 40 inbound pipeline — fill uses 60 only.
        _row(planned=100, shipped=60, flag="short", pipeline=40),
        # planned 50, nothing shipped, 30 inbound pipeline -> "inbound/pipeline" pending.
        _row(planned=50, shipped=0, flag="unshipped", customer_id=2, product_id=11, pipeline=30),
        # planned 20, nothing shipped, no pipeline -> "cold" pending.
        _row(planned=20, shipped=0, flag="unshipped", customer_id=3, product_id=12, pipeline=0),
    ]
    sc = mod.compute_scorecard_from_execution_rows(rows)
    # fill = (min(60,100)+min(0,50)+min(0,20)) / (100+50+20) = 60 / 170
    assert sc["fill_rate"] == pytest.approx(60 / 170)
    assert sc["shipped_units_in_plan"] == 60  # pipeline NOT summed in
    assert sc["pipeline_units_in_plan"] == 70  # 40 + 30 (open_order on in-plan rows)
    # pending_split counts only in-plan rows with nothing shipped (row2 inbound, row3 cold):
    assert sc["pending_split"]["inbound_pipeline_lines"] == 1
    assert sc["pending_split"]["inbound_pipeline_units"] == 30
    assert sc["pending_split"]["cold_lines"] == 1
    assert sc["pending_split"]["cold_planned_units"] == 20


def test_line_hit_rate_secondary_metric():
    rows = [
        _row(planned=100, shipped=100, flag="matched"),
        _row(planned=100, shipped=50, flag="short", customer_id=2, product_id=11),
    ]
    sc = mod.compute_scorecard_from_execution_rows(rows)
    assert sc["line_hit_rate"] == 0.5


def test_no_po_blind_spot_kpi():
    rows = [
        _row(planned=40, shipped=0, flag=None, awaiting_po=True),
        _row(planned=60, shipped=60, flag="matched", customer_id=2, product_id=11),
    ]
    sc = mod.compute_scorecard_from_execution_rows(rows)
    assert sc["no_po_blind_spot"]["line_count"] == 1
    assert sc["no_po_blind_spot"]["planned_units"] == 40


def test_three_bucket_collapse():
    rows = [
        _row(planned=10, shipped=10, flag="matched"),
        _row(planned=10, shipped=5, flag="short", customer_id=2, product_id=11),
        _row(planned=10, shipped=15, flag="over", customer_id=3, product_id=12),
        _row(planned=0, shipped=5, flag="unplanned", customer_id=4, product_id=13),
        _row(planned=0, shipped=3, flag="amended", customer_id=5, product_id=14),
        _row(planned=8, shipped=0, flag="unshipped", customer_id=6, product_id=15),
        _row(planned=5, shipped=0, flag=None, awaiting_po=True, customer_id=7, product_id=16),
    ]
    sc = mod.compute_scorecard_from_execution_rows(rows)
    assert sc["buckets"]["executed_vs_plan"] == 3
    assert sc["buckets"]["off_plan"] == 2
    assert sc["buckets"]["pending"] == 2  # unshipped + awaiting_po line


def test_unplanned_intake_off_plan_only():
    rows = [
        _row(planned=0, shipped=20, flag="unplanned", customer_id=1, product_id=10, value_plan=0),
        _row(planned=100, shipped=100, flag="matched", customer_id=2, product_id=11),
    ]
    sc = mod.compute_scorecard_from_execution_rows(rows)
    assert sc["unplanned_intake_units"] == 20
    assert sc["planned_units"] == 100


def test_exception_value_unavailable_when_no_pricing_bridge():
    rows = [
        {
            **_row(planned=100, shipped=40, flag="short", customer_id=1, product_id=10),
            "customer_label": "Cust-1",
            "business_unit_label": "NB",
            "value": {
                "shipped_value_cost": 400,
                "value_status": "missing",
            },
        },
    ]
    exc = mod._aggregate_exceptions(rows, rank_by="units")
    item = exc["customer"]["short_ships"][0]
    assert item["units"] == 60
    assert item["value_plan"] is None
    assert item["value_cost"] is None


def test_aggregate_exceptions_customer_lens():
    rows = [
        _row(planned=100, shipped=40, flag="short", customer_id=1, product_id=10),
        _row(planned=50, shipped=80, flag="over", customer_id=2, product_id=11),
        _row(planned=0, shipped=30, flag="unplanned", customer_id=3, product_id=12, value_plan=0),
        _row(planned=25, shipped=0, flag=None, awaiting_po=True, customer_id=4, product_id=13),
    ]
    for r in rows:
        r["customer_label"] = f"Cust-{r['customer_id']}"
        r["business_unit_label"] = "NB"
    exc = mod._aggregate_exceptions(rows, rank_by="units")
    assert exc["customer"]["short_ships"][0]["units"] == 60
    assert exc["customer"]["over_ships"][0]["units"] == 30
    assert exc["customer"]["unplanned_intake"][0]["units"] == 30
    assert exc["customer"]["no_po_blind_spots"][0]["units"] == 25


def test_backlog_066_period_detection():
    rows = [{"year": 2025, "quarter": 1, "quarter_label": "25Q1"}]
    clusters = [{"inferred_period_start": "2025-01-01", "case_ids": [39, 40]}]
    assert mod._affected_duplicate_ingestion_labels(rows, clusters) == ["25Q1"]
    clean = [{"year": 2026, "quarter": 2, "quarter_label": "26Q2"}]
    assert mod._affected_duplicate_ingestion_labels(clean, clusters) == []
    assert mod._affected_duplicate_ingestion_labels(rows, []) == []


def test_enumerate_available_periods_full_span():
    cov_groups = [
        {"year": 2024, "quarter": 2, "quarter_label": "24Q2"},
        {"year": 2026, "quarter": 3, "quarter_label": "26Q3"},
        {"year": 2025, "quarter": 1, "quarter_label": "25Q1"},
    ]

    async def _run():
        with patch.object(mod, "coverage", AsyncMock(return_value={"groups": cov_groups, "data_unavailable": False})):
            return await mod.enumerate_available_periods(AsyncMock())

    out = asyncio.run(_run())
    labels = [p["label"] for p in out]
    assert labels == ["26Q3", "25Q1", "24Q2"]
    assert len(labels) == 3


def test_resolve_default_period_prefers_latest_linked_quarter():
    all_periods = [
        {"year": 2026, "quarter": 3, "label": "26Q3"},
        {"year": 2026, "quarter": 2, "label": "26Q2"},
        {"year": 2024, "quarter": 2, "label": "24Q2"},
    ]
    groups = [
        {"year": 2026, "quarter": 3, "status": "unlinked", "linked_po_count": 0},
        {"year": 2026, "quarter": 2, "status": "linked", "linked_po_count": 12},
        {"year": 2024, "quarter": 2, "status": "linked", "linked_po_count": 3},
    ]
    assert mod.resolve_default_period(all_periods, coverage_groups=groups) == "26Q2"


def test_resolve_default_period_coverage_groups_without_status():
    """``coverage()`` omits status — linked_po_count alone must drive the default."""
    all_periods = [
        {"year": 2026, "quarter": 3, "label": "26Q3"},
        {"year": 2026, "quarter": 2, "label": "26Q2"},
        {"year": 2026, "quarter": 1, "label": "26Q1"},
    ]
    groups = [
        {"year": 2026, "quarter": 3, "linked_po_count": 0},
        {"year": 2026, "quarter": 2, "linked_po_count": 28},
        {"year": 2026, "quarter": 1, "linked_po_count": 23},
    ]
    assert mod.resolve_default_period(all_periods, coverage_groups=groups) == "26Q2"


def test_resolve_default_period_prefers_lineup_linked_over_coverage_observation():
    """PO observed in 26Q3 but linked to 26Q2 lineup must not default empty 26Q3."""
    all_periods = [
        {"year": 2026, "quarter": 3, "label": "26Q3"},
        {"year": 2026, "quarter": 2, "label": "26Q2"},
        {"year": 2026, "quarter": 1, "label": "26Q1"},
    ]
    groups = [
        {"year": 2026, "quarter": 3, "linked_po_count": 40},
        {"year": 2026, "quarter": 2, "linked_po_count": 5},
    ]
    assert (
        mod.resolve_default_period(
            all_periods,
            coverage_groups=groups,
            lineup_linked_quarters={(2026, 2), (2026, 1)},
        )
        == "26Q2"
    )


def test_available_periods_independent_of_period_filter():
    all_periods = [
        {"year": 2026, "quarter": 3, "label": "26Q3"},
        {"year": 2026, "quarter": 2, "label": "26Q2"},
        {"year": 2024, "quarter": 2, "label": "24Q2"},
    ]
    fake_rows = [
        {
            **_row(planned=10, shipped=10),
            "case_id": 1,
            "year": 2026,
            "quarter": 3,
            "quarter_label": "26Q3",
            "customer_label": "A",
            "business_unit_label": "NB",
        }
    ]

    async def _run():
        cov = _cov_for_periods(["26Q3", "26Q2", "24Q2"])
        with patch.object(mod, "coverage", AsyncMock(return_value=cov)):
            with patch.object(mod, "collect_execution_rows", AsyncMock(return_value=fake_rows)):
                with patch.object(mod, "_compute_trend", AsyncMock(return_value=[])):
                    return await mod.plan_vs_executed_read_model(
                        AsyncMock(), period_from="26Q3", period_to="26Q3"
                    )

    out = asyncio.run(_run())
    assert len(out["available_periods"]) == 3
    assert out["available_periods"][0]["label"] == "26Q3"
    assert out["default_period"] == "26Q3"
    assert out["period_range"] == {"from": "26Q3", "to": "26Q3"}


def test_period_slots_in_range():
    all_periods = [
        {"year": 2026, "quarter": 3, "label": "26Q3"},
        {"year": 2026, "quarter": 2, "label": "26Q2"},
        {"year": 2024, "quarter": 2, "label": "24Q2"},
    ]
    slots = mod._period_slots_in_range(all_periods, period_from="24Q2", period_to="26Q2")
    assert [s[2] for s in slots] == ["24Q2", "26Q2"]


def test_plan_vs_executed_read_model_wires_scorecard():
    fake_rows = [
        {
            **_row(planned=10, shipped=10),
            "case_id": 1,
            "year": 2026,
            "quarter": 2,
            "quarter_label": "26Q2",
            "customer_label": "A",
            "business_unit_label": "NB",
        }
    ]

    async def _run():
        with patch.object(mod, "coverage", AsyncMock(return_value=_cov_for_periods(["26Q2"]))):
            with patch.object(mod, "collect_execution_rows", AsyncMock(return_value=fake_rows)):
                with patch.object(mod, "_compute_trend", AsyncMock(return_value=[])):
                    out = await mod.plan_vs_executed_read_model(AsyncMock(), period_from="26Q2", period_to="26Q2")
        return out

    out = asyncio.run(_run())
    assert out["data_unavailable"] is False
    assert out["scorecard"]["fill_rate"] == 1.0
    assert out["exceptions"]["customer"]["short_ships"] == []


def _period_row(period_label: str, *, planned: float, shipped: float, **extra) -> dict:
    year = 2000 + int(period_label[:2])
    quarter = int(period_label[-1])
    base = {
        **_row(planned=planned, shipped=shipped),
        "case_id": 1,
        "year": year,
        "quarter": quarter,
        "quarter_label": period_label,
        "customer_label": "A",
        "business_unit_label": "NB",
        "product_sku": "SKU-10",
        "product_sales_model": "Model-X",
        "product_description": "Desc-10",
    }
    base.update(extra)
    return base


CLEAN_GOLDEN_PERIODS = ["26Q3", "26Q2", "26Q1", "24Q3", "24Q2", "23Q1"]
FLAGGED_GOLDEN_PERIODS = ["25Q1", "24Q4"]


def test_golden_scorecard_tie_out_all_clean_periods():
    """Independently recompute scorecard from rows for every non-BACKLOG-066 period."""

    async def _run_period(period: str):
        rows = [
            _period_row(period, planned=100, shipped=60, flag="short", customer_id=1, product_id=10),
            _period_row(period, planned=50, shipped=80, flag="over", customer_id=2, product_id=11),
        ]
        manual = mod.scorecard_tie_out_fields(mod.compute_scorecard_from_execution_rows(rows))
        all_periods = [{"year": 2000 + int(period[:2]), "quarter": int(period[-1]), "label": period}]
        with patch.object(mod, "coverage", AsyncMock(return_value=_cov_for_periods([period]))):
            with patch.object(mod, "collect_execution_rows", AsyncMock(return_value=rows)):
                with patch.object(mod, "_compute_trend", AsyncMock(return_value=[])):
                    out = await mod.plan_vs_executed_read_model(
                        AsyncMock(), period_from=period, period_to=period
                    )
        return manual, out

    for period in CLEAN_GOLDEN_PERIODS:
        manual, out = asyncio.run(_run_period(period))
        assert out["data_quality"]["backlog_066_message"] is None, period
        assert mod.scorecard_tie_out_fields(out["scorecard"]) == manual, period


@pytest.mark.parametrize("period", FLAGGED_GOLDEN_PERIODS)
def test_backlog_066_flag_instead_of_golden_assertion(period: str):
    rows = [_period_row(period, planned=40, shipped=10, flag="short")]
    period_start = "2025-01-01" if period == "25Q1" else "2024-10-01"
    clusters = [{"inferred_period_start": period_start, "case_ids": [39, 40]}]

    async def _run():
        with patch.object(mod, "_load_duplicate_ingestion_samples", AsyncMock(return_value=clusters)):
            with patch.object(mod, "coverage", AsyncMock(return_value=_cov_for_periods([period]))):
                with patch.object(mod, "collect_execution_rows", AsyncMock(return_value=rows)):
                    with patch.object(mod, "_compute_trend", AsyncMock(return_value=[])):
                        return await mod.plan_vs_executed_read_model(
                            AsyncMock(), period_from=period, period_to=period
                        )

    out = asyncio.run(_run())
    assert out["data_quality"]["backlog_066_message"]
    assert period in out["data_quality"]["backlog_066_affected_periods"]


def test_product_lens_sales_model_groups_distinct_from_sku():
    rows = [
        {
            **_row(planned=10, shipped=5, flag="short", product_id=1),
            "customer_label": "A",
            "business_unit_label": "NB",
            "product_sku": "SKU-A",
            "product_sales_model": "Shared-Model",
            "product_name": "Name A",
        },
        {
            **_row(planned=20, shipped=10, flag="short", customer_id=2, product_id=2),
            "customer_label": "B",
            "business_unit_label": "NB",
            "product_sku": "SKU-B",
            "product_sales_model": "Shared-Model",
            "product_name": "Name B",
        },
    ]
    by_sku = mod._aggregate_exceptions(rows, rank_by="units", product_group_by="sku")
    by_model = mod._aggregate_exceptions(rows, rank_by="units", product_group_by="sales_model")
    assert len(by_sku["product"]["short_ships"]) == 2
    assert len(by_model["product"]["short_ships"]) == 1
    assert by_model["product"]["short_ships"][0]["units"] == 15


def test_drill_filter_does_not_change_scorecard():
    rows = [
        {
            **_row(planned=100, shipped=50, flag="short", customer_id=1, product_id=10),
            "case_id": 1,
            "year": 2026,
            "quarter": 2,
            "quarter_label": "26Q2",
            "customer_label": "A",
            "business_unit_label": "NB",
        },
        {
            **_row(planned=80, shipped=80, flag="matched", customer_id=2, product_id=11),
            "case_id": 1,
            "year": 2026,
            "quarter": 2,
            "quarter_label": "26Q2",
            "customer_label": "B",
            "business_unit_label": "NB",
        },
    ]
    portfolio_sc = mod.compute_scorecard_from_execution_rows(rows)

    async def _run():
        with patch.object(mod, "coverage", AsyncMock(return_value=_cov_for_periods(["26Q2"]))):
            with patch.object(mod, "collect_execution_rows", AsyncMock(return_value=rows)):
                with patch.object(mod, "_compute_trend", AsyncMock(return_value=[])):
                    return await mod.plan_vs_executed_read_model(
                        AsyncMock(),
                        period_from="26Q2",
                        period_to="26Q2",
                        drill_customer_id=1,
                    )

    out = asyncio.run(_run())
    assert out["scorecard"]["planned_units"] == portfolio_sc["planned_units"]
    assert len(out["drill_rows"]) == 1
    assert out["drill_rows"][0]["customer_label"] == "A"
