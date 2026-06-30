"""Unit tests for the PO gap worklist (Session C Unit 3). Mock-based."""
import asyncio
import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

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


def _db(results):
    db = MagicMock()
    db.execute = AsyncMock(side_effect=list(results))
    return db


def test_shipment_quantity_source_is_fact_layer():
    assert mod.SHIPMENT_QUANTITY_SOURCE == "fact_inbound_shipment"


def test_gap_detected_for_uncovered_po_product():
    results = [
        _R([]),                                  # covered pairs -> none
        _R([]),                                  # dismissed POs -> none
        _R([(500, 10, 40.0, dt.date(2026, 2, 15))]),  # shipment (po, product) aggregate
        _R([(500, "PO-1")]),                     # po meta
        _R([(10, "Widget", "Laptops", "PC")]),   # product meta
    ]
    out = asyncio.run(mod.po_gap_worklist(_db(results)))
    assert out["data_unavailable"] is False
    assert out["total_gap_rows"] == 1
    assert out["groups"][0]["quarter_label"] == "26Q1"
    row = out["groups"][0]["rows"][0]
    assert row["purchase_order_id"] == 500
    assert row["product_id"] == 10
    assert row["product_line"] == "Laptops"


def test_covered_po_product_is_not_a_gap():
    results = [
        _R([(500, 10)]),                              # covered: PO 500 covers product 10
        _R([]),                                       # dismissed
        _R([(500, 10, 40.0, dt.date(2026, 2, 15))]),  # shipment aggregate (covered -> excluded)
    ]
    out = asyncio.run(mod.po_gap_worklist(_db(results)))
    assert out["total_gap_rows"] == 0
    assert out["groups"] == []


def test_dismissed_po_excluded_unless_included():
    # PO 500 is dismissed; gap pair exists but should be filtered out by default.
    base = [
        _R([]),                                            # covered
        _R([(500, "PO-1", "out_of_scope")]),               # dismissed rows
        _R([(500, 10, 40.0, dt.date(2026, 2, 15))]),       # shipment aggregate
        _R([(500, "PO-1")]),                               # po meta
        _R([(10, "Widget", "Laptops", "PC")]),             # product meta
    ]
    out = asyncio.run(mod.po_gap_worklist(_db(base)))
    assert out["total_gap_rows"] == 0
    assert out["dismissed"][0]["purchase_order_id"] == 500


def test_dismiss_and_restore_set_reason_code():
    po = SimpleNamespace(id=7, dismiss_reason_code=None)
    db = MagicMock()
    db.get = AsyncMock(return_value=po)
    db.commit = AsyncMock()
    out = asyncio.run(mod.dismiss_gap_po(db, 7, "no_lineup_needed"))
    assert out["dismiss_reason_code"] == "no_lineup_needed"
    assert po.dismiss_reason_code == "no_lineup_needed"

    out2 = asyncio.run(mod.restore_gap_po(db, 7))
    assert out2["dismiss_reason_code"] is None
    assert po.dismiss_reason_code is None


def test_dismiss_unknown_po_raises():
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(mod.PurchaseOrderNotFoundError):
        asyncio.run(mod.dismiss_gap_po(db, 999, "x"))
