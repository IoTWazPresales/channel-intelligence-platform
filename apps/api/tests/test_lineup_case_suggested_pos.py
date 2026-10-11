"""Unit tests for lineup case suggested POs (read-only overlap ranking)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.commercial_planner import lineup_case_suggested_pos as mod
from app.services.commercial_planner.lineup_case_po_confirm import CaseNotFoundError


class _Res:
    def __init__(self, scalar_list=None, rows=None):
        self._scalar_list = scalar_list or []
        self._rows = rows or []

    def scalars(self):
        return self

    def all(self):
        if self._rows:
            return list(self._rows)
        return list(self._scalar_list)

    def first(self):
        items = self.all()
        return items[0] if items else None


def test_suggest_pos_case_not_found():
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(CaseNotFoundError):
        asyncio.run(mod.suggest_pos_for_case(db, 99))


def test_suggest_pos_empty_when_no_resolved_products():
    case = SimpleNamespace(id=3)
    db = MagicMock()
    db.get = AsyncMock(return_value=case)
    db.execute = AsyncMock(
        side_effect=[
            _Res(scalar_list=[]),  # product ids
            _Res(scalar_list=[7]),  # infer distributor
            _Res(scalar_list=[7]),  # line distributors
            _Res(scalar_list=[]),  # linked po ids
        ]
    )
    out = asyncio.run(mod.suggest_pos_for_case(db, 3))
    assert out["case_id"] == 3
    assert out["suggestions"] == []


def test_suggest_pos_ranks_by_overlap_and_flags_linked():
    case = SimpleNamespace(id=5)
    row_a = (100, "PO-A", "A", 7, "observed", "D1", "Dist One", 3, 120.0)
    row_b = (101, "PO-B", "B", 7, "observed", "D1", "Dist One", 1, 40.0)
    db = MagicMock()
    db.get = AsyncMock(return_value=case)
    db.execute = AsyncMock(
        side_effect=[
            _Res(scalar_list=[10, 11, 12]),  # product ids
            _Res(scalar_list=[7]),  # single distributor
            _Res(scalar_list=[7]),
            _Res(scalar_list=[100]),  # already linked PO 100
            _Res(rows=[row_a, row_b]),
        ]
    )
    out = asyncio.run(mod.suggest_pos_for_case(db, 5))
    suggestions = out["suggestions"]
    assert len(suggestions) == 2
    assert suggestions[0]["po_number"] == "PO-A"
    assert suggestions[0]["matched_product_count"] == 3
    assert suggestions[0]["total_shipped_units"] == 120.0
    assert suggestions[0]["already_linked"] is True
    assert suggestions[1]["already_linked"] is False


def test_suggest_pos_excludes_wrong_distributor():
    case = SimpleNamespace(id=6)
    row_match = (200, "PO-OK", "OK", 7, "observed", "D1", "Dist", 2, 50.0)
    row_wrong = (201, "PO-BAD", "BAD", 99, "observed", "DX", "Other", 2, 50.0)
    db = MagicMock()
    db.get = AsyncMock(return_value=case)
    db.execute = AsyncMock(
        side_effect=[
            _Res(scalar_list=[10, 11]),
            _Res(scalar_list=[7]),
            _Res(scalar_list=[7]),
            _Res(scalar_list=[]),
            _Res(rows=[row_match, row_wrong]),
        ]
    )
    out = asyncio.run(mod.suggest_pos_for_case(db, 6))
    norms = {s["po_number_norm"] for s in out["suggestions"]}
    assert norms == {"OK"}


# --- N-0071 round 4: "Shipped units" counts shipped evidence lines only ------------------------
#
# Real SQL on an isolated in-memory SQLite copy of the evidence read model, purchase_order and
# dim_distributor (no cip access). Open-order lines, with or without a strict shipped twin
# (same operating unit + order + item), are not shipped units; the PO stays suggested and keeps
# its matched-product count. The distributor list is ordered by matched products, then shipped units.


def _sqlite_session():
    from sqlalchemy import create_engine
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.orm import Session

    @compiles(JSONB, "sqlite")
    def _jsonb_as_json_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL rendering only
        return "JSON"

    engine = create_engine("sqlite://")
    for model in (mod.DimDistributor, mod.PurchaseOrder, mod.EV):
        model.__table__.create(engine, checkfirst=True)
    return Session(engine)


class _AsyncOverSync:
    def __init__(self, session, case):
        self._s = session
        self._case = case

    async def get(self, _model, _ident):
        return self._case

    async def execute(self, stmt, *args, **kwargs):
        return self._s.execute(stmt, *args, **kwargs)


def _ev_row(n: int, state: str, *, po: int, product: int, qty: float, order_no: str):
    from datetime import datetime, timezone

    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    kw = dict(
        id=n, import_job_id=1, source_key=f"k{n}", source_row_number=n, report_type="test", line_state=state,
        raw_source_row={}, operating_unit="ACZA", order_no=order_no, item_code=f"ITEM-{product}", quantity=qty,
        purchase_order_id=po, product_id=product, product_resolution_status="resolved",
        distributor_resolution_status="resolved",
    )
    if hasattr(mod.EV, "line_identity_key"):  # shipment_evidence_current (default read model)
        kw.update(line_identity_key=f"L{n}", source_row_hash="h", valid_from=now, observed_at=now)
    return mod.EV(**kw)


def test_shipped_units_count_shipped_lines_only_and_order_distributors(monkeypatch):
    db = _sqlite_session()
    db.add_all([
        mod.DimDistributor(id=1, code="D1", name="Dist One"),
        mod.DimDistributor(id=2, code="D2", name="Dist Two"),
    ])
    db.flush()
    db.add_all([
        mod.PurchaseOrder(id=7, po_number_raw="PO-A", po_number_norm="A", distributor_id=1),
        mod.PurchaseOrder(id=8, po_number_raw="PO-B", po_number_norm="B", distributor_id=2),
        mod.PurchaseOrder(id=9, po_number_raw="PO-C", po_number_norm="C", distributor_id=1),
    ])
    db.flush()
    db.add_all([
        # PO-A: shipped 10 + 5; an open line covered by its shipped twin (SO-1) and an open line
        # with no twin (SO-2). The all-states sum would be 75.
        _ev_row(1, "shipped", po=7, product=3, qty=10, order_no="SO-1"),
        _ev_row(2, "open_order", po=7, product=3, qty=10, order_no="SO-1"),
        _ev_row(3, "open_order", po=7, product=3, qty=50, order_no="SO-2"),
        _ev_row(4, "shipped", po=7, product=4, qty=5, order_no="SO-3"),
        # PO-B: shipped only, 40 + 2.
        _ev_row(5, "shipped", po=8, product=3, qty=40, order_no="SO-4"),
        _ev_row(6, "shipped", po=8, product=4, qty=2, order_no="SO-5"),
        # PO-C: open only (no twin).
        _ev_row(7, "open_order", po=9, product=3, qty=30, order_no="SO-6"),
    ])
    db.flush()

    async def _products(_db, _cid):
        return [3, 4]

    async def _none(_db, _cid):
        return None

    async def _empty_list(_db, _cid):
        return []

    async def _empty_set(_db, _cid):
        return set()

    monkeypatch.setattr(mod, "_case_product_ids", _products)
    monkeypatch.setattr(mod, "_infer_case_distributor_id", _none)
    monkeypatch.setattr(mod, "_case_line_distributor_ids", _empty_list)
    monkeypatch.setattr(mod, "_linked_po_ids", _empty_set)
    adb = _AsyncOverSync(db, SimpleNamespace(id=1))

    pos = asyncio.run(mod.suggest_pos_for_case(adb, 1))["suggestions"]
    by_po = {s["po_number"]: s for s in pos}
    assert [s["po_number"] for s in pos] == ["PO-A", "PO-B", "PO-C"]  # matched products, then PO number
    assert by_po["PO-A"]["total_shipped_units"] == 15.0  # not 75: open lines with and without a twin excluded
    assert by_po["PO-B"]["total_shipped_units"] == 42.0
    assert by_po["PO-C"]["total_shipped_units"] == 0.0  # open-only PO stays suggested, 0 shipped
    assert by_po["PO-A"]["matched_product_count"] == 2
    assert by_po["PO-C"]["matched_product_count"] == 1

    dist = asyncio.run(mod.suggest_distributors_for_case(adb, 1))["suggested_distributors"]
    # Both distributors match 2 products; shipped units order them (Dist Two 42 > Dist One 15).
    # Summing every line_state would give Dist One 105 and put it first.
    assert [(d["distributor_id"], d["total_shipped_units"]) for d in dist] == [(2, 42.0), (1, 15.0)]
    assert [d["matched_product_count"] for d in dist] == [2, 2]
    assert [d["po_count"] for d in dist] == [1, 2]
    db.close()
