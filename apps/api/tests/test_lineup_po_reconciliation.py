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


def _with_product_results(
    planned,
    shipped,
    *,
    po_shipped=True,
    meta=None,
    fx=18.5,
    uom="ea",
    customers=None,
):
    """Standard execute sequence for customer x product reconciliation under PO 500.

    planned/shipped tuples: (customer_id, product_id, units, value).
    """
    meta = meta if meta is not None else [(10, "Laptop X", "Laptops", "PC")]
    cust_ids: set[int] = set()
    for row in planned:
        if row[0] is not None:
            cust_ids.add(int(row[0]))
    for row in shipped:
        if row[0] is not None:
            cust_ids.add(int(row[0]))
    if customers is None:
        customers = [(cid, f"Customer {cid}") for cid in sorted(cust_ids)]
    resolved_scalar = sorted({int(r[0]) for r in shipped if r[0] is not None})
    return [
        _R([(500, "PO-1", "1")]),  # po_rows
        _R(planned),  # planned_rows (customer_id, product_id, units, value)
        _R([(10, uom)]),  # uom_rows
        _R(shipped),  # shipped_rows (resolved_customer_id, product_id, units, value)
        _R([], scalar_rows=resolved_scalar),  # resolved_customers on POs
        _R([], scalar_rows=([500] if po_shipped else [])),  # po_with_shipments
        _R(meta),  # product meta
        _R([(10, fx)] if fx is not None else []),  # fx
        _R(customers),  # customer names
    ]


def _flag(out, product_id=10, customer_id=5):
    return next(
        p["units_flag"]
        for p in out["products"]
        if p["product_id"] == product_id and p.get("customer_id") == customer_id
    )


def test_matched():
    out = asyncio.run(
        mod.reconcile_case(
            _db(_case(), _with_product_results([(5, 10, 100.0, 5000.0)], [(5, 10, 100.0, 1000.0)])),
            1,
        )
    )
    assert out["data_unavailable"] is False
    assert _flag(out) == "matched"
    assert out["summary"]["matched"] == 1
    assert len(out["customers"]) == 1
    assert out["customers"][0]["label"] == "Customer 5"


def test_short():
    out = asyncio.run(
        mod.reconcile_case(_db(_case(), _with_product_results([(5, 10, 100.0, 5000.0)], [(5, 10, 60.0, 600.0)])), 1)
    )
    assert _flag(out) == "short"


def test_over():
    out = asyncio.run(
        mod.reconcile_case(_db(_case(), _with_product_results([(5, 10, 100.0, 5000.0)], [(5, 10, 150.0, 1500.0)])), 1)
    )
    assert _flag(out) == "over"


def test_unshipped():
    # PO shipped for this customer on another product -> unshipped for planned product, not awaiting_po.
    out = asyncio.run(
        mod.reconcile_case(
            _db(
                _case(),
                _with_product_results(
                    [(5, 10, 100.0, 5000.0)],
                    [(5, 99, 10.0, 100.0)],
                    po_shipped=True,
                    meta=[(10, "Laptop X", "Laptops", "PC"), (99, "Dock", "Laptops", "PC")],
                ),
            ),
            1,
        )
    )
    assert _flag(out) == "unshipped"
    assert out["summary"]["po_no_match"] == 0
    assert out["customers"][0]["awaiting_po"] is False


def test_amended_same_product_line():
    out = asyncio.run(
        mod.reconcile_case(
            _db(
                _case(product_line="Laptops"),
                _with_product_results([], [(5, 10, 30.0, 300.0)], meta=[(10, "X", "Laptops", "PC")], customers=[(5, "Acme")]),
            ),
            1,
        )
    )
    assert _flag(out) == "amended"
    assert out["summary"]["amended"] == 1


def test_unplanned_different_product_line():
    out = asyncio.run(
        mod.reconcile_case(
            _db(
                _case(product_line="Laptops"),
                _with_product_results([], [(5, 10, 30.0, 300.0)], meta=[(10, "X", "Monitors", "Display")], customers=[(5, "Acme")]),
            ),
            1,
        )
    )
    assert _flag(out) == "unplanned"
    assert out["summary"]["unplanned"] == 1


def test_po_no_match_no_shipments_anywhere():
    results = [
        _R([(500, "PO-1", "1")]),
        _R([]),
        _R([]),
        _R([]),
        _R([], scalar_rows=[]),
        _R([], scalar_rows=[]),
    ]
    out = asyncio.run(mod.reconcile_case(_db(_case(), results), 1))
    assert out["summary"]["po_no_match"] == 1
    assert out["po_flags"][0]["purchase_order_id"] == 500
    assert out["po_flags"][0]["flag"] == "po_no_match"


def test_value_fx_unavailable_does_not_block_units_flag():
    out = asyncio.run(
        mod.reconcile_case(
            _db(_case(), _with_product_results([(5, 10, 100.0, 5000.0)], [(5, 10, 100.0, 1000.0)], fx=None)),
            1,
        )
    )
    prod = out["products"][0]
    assert prod["units_flag"] == "matched"
    assert prod["value"]["value_status"] == "fx_unavailable"
    assert prod["value"]["shipped_value_plan"] is None


def test_value_bridged_when_fx_present():
    out = asyncio.run(
        mod.reconcile_case(
            _db(_case(), _with_product_results([(5, 10, 100.0, 5000.0)], [(5, 10, 100.0, 1000.0)], fx=18.5)),
            1,
        )
    )
    prod = out["products"][0]
    assert prod["value"]["value_status"] == "ok"
    assert prod["value"]["shipped_value_plan"] == pytest.approx(1000.0 * 18.5)


def test_uom_non_eaches_emits_warning():
    out = asyncio.run(
        mod.reconcile_case(
            _db(_case(), _with_product_results([(5, 10, 100.0, 5000.0)], [(5, 10, 100.0, 1000.0)], uom="box")),
            1,
        )
    )
    assert out["products"][0]["warnings"]


def test_case_not_found_raises():
    db = _db(None, [])
    with pytest.raises(mod.CaseNotFoundError):
        asyncio.run(mod.reconcile_case(db, 999))


def test_awaiting_po_customer_not_counted_as_short():
    """One customer linked; another has plan but no PO evidence resolves to them."""
    meta = [(10, "P10", "Laptops", "NB"), (20, "P20", "Laptops", "NB")]
    customers = [(101, "Makro"), (102, "Game")]
    planned = [(101, 10, 100.0, 5000.0), (102, 20, 50.0, 2500.0)]
    shipped = [(101, 10, 100.0, 1000.0)]
    out = asyncio.run(
        mod.reconcile_case(
            _db(_case(), _with_product_results(planned, shipped, meta=meta, customers=customers)),
            1,
        )
    )
    makro = next(c for c in out["customers"] if c["customer_id"] == 101)
    game = next(c for c in out["customers"] if c["customer_id"] == 102)
    assert makro["summary"]["matched"] == 1
    assert game["awaiting_po"] is True
    assert game["summary"]["short"] == 0
    assert out["summary"]["matched"] == 1
    assert out["summary"]["short"] == 0


def test_multi_customer_parity_with_legacy_product_grain_when_fully_linked():
    """Distinct products per customer, all matched — customer rollup equals legacy product totals."""
    meta = [(10, "P10", "Laptops", "NB"), (20, "P20", "Laptops", "NB")]
    customers = [(101, "Makro"), (102, "Game")]
    planned = [(101, 10, 100.0, 5000.0), (102, 20, 80.0, 4000.0)]
    shipped = [(101, 10, 100.0, 1000.0), (102, 20, 80.0, 800.0)]
    out = asyncio.run(
        mod.reconcile_case(
            _db(_case(), _with_product_results(planned, shipped, meta=meta, customers=customers)),
            1,
        )
    )
    legacy_planned = {10: {"units": 100.0}, 20: {"units": 80.0}}
    legacy_shipped = {10: {"units": 100.0}, 20: {"units": 80.0}}
    legacy_meta = {10: {"product_line": "Laptops", "business_unit": "NB"}, 20: {"product_line": "Laptops", "business_unit": "NB"}}
    legacy_summary = mod.reconcile_case_legacy_product_grain_summary(
        legacy_planned, legacy_shipped, product_line="Laptops", meta=legacy_meta
    )
    for flag in mod.UNITS_FLAGS:
        if flag == "po_no_match":
            continue
        assert out["summary"][flag] == legacy_summary[flag]
