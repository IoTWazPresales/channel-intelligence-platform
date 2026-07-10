"""PO gap worklist excludes superseded lineup cases from coverage."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.services.commercial_planner import lineup_po_gap as mod


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _R:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def scalars(self):
        return _Scalars(self._rows)


def test_gap_covered_pairs_ignore_superseded_cases(monkeypatch):
    """Covered join must include active_lineup_case_filters (smoke: query builds)."""
    calls: list[str] = []

    async def _capture_execute(stmt):
        calls.append(str(stmt))
        if "purchase_order.dismiss_reason_code" in str(stmt):
            return _R([])
        if "fact_inbound_shipment" in str(stmt):
            return _R([(1, 10, 5.0, None)])
        if "dim_product" in str(stmt):
            return _R([(10, "Prod", "NB", "NB")])
        if "purchase_order.id" in str(stmt):
            return _R([(1, "PO-1")])
        return _R([])

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_capture_execute)
    out = asyncio.run(mod.po_gap_worklist(db))
    assert out["data_unavailable"] is False
    covered_sql = next(c for c in calls if "commercial_lineup_case" in c)
    assert "superseded_by_case_id" in covered_sql or "commercial_status" in covered_sql
