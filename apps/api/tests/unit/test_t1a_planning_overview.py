"""T1a: planning overview reads the lineup lines once (readiness + not-ready in one scan)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import planning_overview as mod


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


def _db():
    results = [
        _Result(scalar="cip_test"),  # current_database()
        _Result(scalars=[1, 2]),  # reporting customer ids (the shared definition)
        _Result(scalar=3),  # active case count (reporting customers only)
        _Result(scalars=["26Q1", "26Q2"]),  # period labels
        _Result(
            mapping={
                "lines": 100,
                "plan_units": 5000,
                "sku_ok": 90,
                "terms_ok": 80,
                "dist_ok": 70,
                "cost_ok": 60,
                "not_ready": 35,
            }
        ),
        _Result(mapping={"plan_lines": 10, "flagged": 2}),
    ]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=results)
    return db


def test_not_ready_comes_from_the_single_line_scan():
    db = _db()
    execution = {
        "period": "26Q2",
        "fill_rate": 0.5,
        "planned_units_execution": 10.0,
        "shipped_units_in_plan": 5.0,
        "by_customer": [],
    }
    with patch.object(mod, "_shipped_vs_plan", AsyncMock(return_value=execution)):
        out = asyncio.run(mod.planning_overview(db, None))
    assert out["data_unavailable"] is False
    # was 6 before T1a (a second full scan of the lines for "not ready"); +1 for the one
    # reporting-customer-ids read the reporting-only rule needs.
    assert db.execute.await_count == 6
    assert out["readiness_missing"] == 35
    assert out["readiness_ok"] == 65
    assert out["lines"] == 100
    assert out["economics_ok"] == 8
    assert out["fill_rate_pct"] == 50
