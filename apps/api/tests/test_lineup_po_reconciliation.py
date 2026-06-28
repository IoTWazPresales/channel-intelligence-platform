"""Unit tests for PO reconciliation (Session C Unit 3) — units-primary flags + FX-bridged value.

Mock-based (commercial_lineup_case_po migration not yet applied to cip). Each test sequences the
deterministic db.execute() results for one (case x product) scenario and asserts the primary units
flag. Covers all 7 flags (matched/short/over/unshipped/unplanned/amended/po_no_match) plus the
FX-missing value path and the eaches UoM warning.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.commercial_planner import lineup_po_reconciliation as mod


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _R:
    def __init__(self, rows, scalar_rows=None):
        self._rows = rows
        self._scalar = scalar_rows if scalar_rows is not None else rows

    def all(self):
        return list(self._rows)

    def scalars(self):
        return _Scalars(self._scalar)


def _db(case, results):
    db = MagicMock()
    db.get = AsyncMock(return_value=case)
    db.execute = AsyncMock(side_effect=list(results))
    return db


def _case(**kw):
    return SimpleNamespace(
        id=kw.get("id", 1),
        commercial_status=kw.get("status", "po_issued"),
        currency_code=kw.get("currency", "ZAR"),
        product_line=kw.get("product_line", "Laptops"),
    )


def _with_product_results(planned, shipped, *, po_shipped=True, meta=None, fx=18.5, uom="ea"):
    """Standard 7-call sequence for a single product 10 under PO 500."""
    meta = meta if meta is not None else [(10, "Laptop X", "Laptops", "PC")]
    return [
        _R([(500, "PO-1", "1")]),                       # po_rows
        _R(planned),                                    # planned_rows
        _R([(10, uom)]),                                # uom_rows
        _R(shipped),                                    # shipped_rows
        _R([], scalar_rows=([500] if po_shipped else [])),  # po_with_shipments
        _R(meta),                                       # product meta
        _R([(10, fx)] if fx is not None else []),       # fx
    ]


def _flag(out, product_id=10):
    return next(p["units_flag"] for p in out["products"] if p["product_id"] == product_id)


def test_matched():
    out = asyncio.run(
        mod.reconcile_case(_db(_case(), _with_product_results([(10, 100.0, 5000.0)], [(10, 100.0, 1000.0)])), 1)
    )
    assert out["data_unavailable"] is False
    assert _flag(out) == "matched"
    assert out["summary"]["matched"] == 1


def test_short():
    out = asyncio.run(
        mod.reconcile_case(_db(_case(), _with_product_results([(10, 100.0, 5000.0)], [(10, 60.0, 600.0)])), 1)
    )
    assert _flag(out) == "short"


def test_over():
    out = asyncio.run(
        mod.reconcile_case(_db(_case(), _with_product_results([(10, 100.0, 5000.0)], [(10, 150.0, 1500.0)])), 1)
    )
    assert _flag(out) == "over"


def test_unshipped():
    # PO shipped something (po_shipped=True) but not this product -> unshipped, not po_no_match.
    out = asyncio.run(
        mod.reconcile_case(_db(_case(), _with_product_results([(10, 100.0, 5000.0)], [], po_shipped=True)), 1)
    )
    assert _flag(out) == "unshipped"
    assert out["summary"]["po_no_match"] == 0


def test_amended_same_product_line():
    # Not in lineup (planned empty), shipped under case PO, same product line as case -> amended.
    out = asyncio.run(
        mod.reconcile_case(
            _db(_case(product_line="Laptops"), _with_product_results([], [(10, 30.0, 300.0)], meta=[(10, "X", "Laptops", "PC")])),
            1,
        )
    )
    assert _flag(out) == "amended"
    assert out["summary"]["amended"] == 1


def test_unplanned_different_product_line():
    out = asyncio.run(
        mod.reconcile_case(
            _db(_case(product_line="Laptops"), _with_product_results([], [(10, 30.0, 300.0)], meta=[(10, "X", "Monitors", "Display")])),
            1,
        )
    )
    assert _flag(out) == "unplanned"
    assert out["summary"]["unplanned"] == 1


def test_po_no_match_no_shipments_anywhere():
    # Confirmed PO with zero shipment lines anywhere; no planned/shipped products.
    results = [
        _R([(500, "PO-1", "1")]),     # po_rows
        _R([]),                       # planned_rows (empty)
        _R([]),                       # uom_rows
        _R([]),                       # shipped_rows
        _R([], scalar_rows=[]),       # po_with_shipments -> none
    ]
    out = asyncio.run(mod.reconcile_case(_db(_case(), results), 1))
    assert out["summary"]["po_no_match"] == 1
    assert out["po_flags"][0]["purchase_order_id"] == 500
    assert out["po_flags"][0]["flag"] == "po_no_match"


def test_value_fx_unavailable_does_not_block_units_flag():
    out = asyncio.run(
        mod.reconcile_case(
            _db(_case(), _with_product_results([(10, 100.0, 5000.0)], [(10, 100.0, 1000.0)], fx=None)),
            1,
        )
    )
    prod = out["products"][0]
    assert prod["units_flag"] == "matched"  # units flag still computed
    assert prod["value"]["value_status"] == "fx_unavailable"
    assert prod["value"]["shipped_value_plan"] is None


def test_value_bridged_when_fx_present():
    out = asyncio.run(
        mod.reconcile_case(
            _db(_case(), _with_product_results([(10, 100.0, 5000.0)], [(10, 100.0, 1000.0)], fx=18.5)),
            1,
        )
    )
    prod = out["products"][0]
    assert prod["value"]["value_status"] == "ok"
    assert prod["value"]["shipped_value_plan"] == pytest.approx(1000.0 * 18.5)


def test_uom_non_eaches_emits_warning():
    out = asyncio.run(
        mod.reconcile_case(
            _db(_case(), _with_product_results([(10, 100.0, 5000.0)], [(10, 100.0, 1000.0)], uom="box")),
            1,
        )
    )
    assert out["products"][0]["warnings"]  # non-empty warning for non-each unit


def test_case_not_found_raises():
    db = _db(None, [])
    with pytest.raises(mod.CaseNotFoundError):
        asyncio.run(mod.reconcile_case(db, 999))
