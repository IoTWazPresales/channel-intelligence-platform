"""Unit tests for the PO Management surface (Session C Unit 3). Mock-based."""
import asyncio
import datetime as dt
from unittest.mock import AsyncMock, MagicMock

from app.services.commercial_planner import po_management as mod


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


def _db(results):
    db = MagicMock()
    db.execute = AsyncMock(side_effect=list(results))
    return db


def test_coverage_first_run_groups_by_quarter_and_product_line():
    results = [
        _R([(500, 10, 100.0, 1000.0, dt.date(2026, 2, 15))]),  # observed shipment aggregate
        _R([(10, "Laptops", "PC")]),                            # product line
        _R([(10, 18.5)]),                                       # fx
        _R([]),                                                 # linked po ids -> none (first run)
    ]
    out = asyncio.run(mod.coverage(_db(results)))
    assert out["data_unavailable"] is False
    assert out["total_pos_observed"] == 1
    assert out["total_pos_linked"] == 0
    assert out["first_run"] is True
    g = out["groups"][0]
    assert g["product_line"] == "Laptops"
    assert g["quarter_label"] == "26Q1"
    assert g["shipped_units"] == 100.0
    assert g["shipped_value_plan"] == 1000.0 * 18.5
    assert g["fx_complete"] is True


def test_coverage_fx_partial_when_assumption_missing():
    results = [
        _R([(500, 10, 100.0, 1000.0, dt.date(2026, 2, 15))]),
        _R([(10, "Laptops", "PC")]),
        _R([]),  # no fx assumption
        _R([]),  # linked
    ]
    out = asyncio.run(mod.coverage(_db(results)))
    assert out["groups"][0]["fx_complete"] is False


def test_backlog_unlinked_group_has_upload_prompt():
    results = [
        _R([(500, 10, 100.0, 1000.0, dt.date(2026, 2, 15))]),  # observed
        _R([(10, "Laptops", "PC")]),                            # product line
        _R([(10, 18.5)]),                                       # fx
        _R([]),                                                 # linked po ids
        _R([]),                                                 # case links
    ]
    out = asyncio.run(mod.backlog(_db(results)))
    g = out["groups"][0]
    assert g["status"] == "unlinked"
    assert g["upload_prompt"]["product_line"] == "Laptops"
    assert g["upload_prompt"]["period_label"] == "26Q1"
