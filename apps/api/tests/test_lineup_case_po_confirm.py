"""Unit tests for Confirm-with-PO (Session C Unit 2d).

Mock-based: the commercial_lineup_case_po table is created by migration 20260628_0057, which
Warren applies to cip. These tests assert the orchestration (normalize -> upsert PO -> link ->
po_pending) and the idempotent / amendment-append semantics without touching the DB.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.commercial_lineup import CommercialLineupCasePo
from app.models.purchase_order import PurchaseOrder
from app.services.commercial_planner import lineup_case_po_confirm as mod


class _Res:
    def __init__(self, scalar_list=None, scalar_one_value=None):
        self._scalar_list = scalar_list or []
        self._scalar_one_value = scalar_one_value

    def scalars(self):
        return self

    def all(self):
        return list(self._scalar_list)

    def first(self):
        return self._scalar_list[0] if self._scalar_list else None

    def scalar_one(self):
        return self._scalar_one_value


def _make_db(case, execute_results):
    db = MagicMock()
    db.get = AsyncMock(return_value=case)
    db.execute = AsyncMock(side_effect=list(execute_results))
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    added: list = []
    counter = {"n": 5000}

    def _add(obj):
        added.append(obj)

    async def _flush():
        for obj in added:
            if isinstance(obj, PurchaseOrder) and getattr(obj, "id", None) is None:
                obj.id = counter["n"]
                counter["n"] += 1

    db.add = MagicMock(side_effect=_add)
    db.flush = AsyncMock(side_effect=_flush)
    db._added = added
    return db


def test_confirm_two_pos_creates_two_links_and_sets_po_pending():
    case = SimpleNamespace(id=3, commercial_status="accepted", iteration_number=1)
    results = [
        _Res(scalar_list=[7]),   # distributor inference -> single distributor
        _Res(scalar_list=[]),    # PO #1 lookup -> none -> create
        _Res(scalar_list=[]),    # PO #1 link check -> none -> add link
        _Res(scalar_list=[]),    # PO #2 lookup -> none -> create
        _Res(scalar_list=[]),    # PO #2 link check -> none -> add link
        _Res(scalar_one_value=2),  # final count
    ]
    db = _make_db(case, results)

    out = asyncio.run(
        mod.confirm_case_with_po(db, 3, po_numbers=["PO-1001", "PO-1002"], notes="batch")
    )

    assert case.commercial_status == "po_pending"
    assert out["po_count"] == 2
    assert out["newly_linked_count"] == 2
    # 2 PurchaseOrder + 2 CommercialLineupCasePo added
    assert sum(1 for o in db._added if isinstance(o, PurchaseOrder)) == 2
    assert sum(1 for o in db._added if isinstance(o, CommercialLineupCasePo)) == 2
    assert {p["po_number_norm"] for p in out["linked_pos"]} == {"1001", "1002"}
    assert all(p["distributor_id"] == 7 for p in out["linked_pos"])


def test_reconfirm_same_po_is_idempotent():
    case = SimpleNamespace(id=3, commercial_status="po_issued", iteration_number=2)
    existing_po = SimpleNamespace(id=500, po_number_raw="PO-1001", po_number_norm="1001",
                                  distributor_id=7, status="raised")
    existing_link = SimpleNamespace(id=9, case_id=3, purchase_order_id=500)
    results = [
        _Res(scalar_list=[7]),               # distributor inference
        _Res(scalar_list=[existing_po]),     # PO lookup -> found, reuse
        _Res(scalar_list=[existing_link]),   # link check -> already linked
        _Res(scalar_one_value=1),            # final count unchanged
    ]
    db = _make_db(case, results)

    out = asyncio.run(mod.confirm_case_with_po(db, 3, po_numbers=["po 1001"]))

    assert out["po_count"] == 1
    assert out["newly_linked_count"] == 0
    # No new PO and no new link added
    assert sum(1 for o in db._added if isinstance(o, PurchaseOrder)) == 0
    assert sum(1 for o in db._added if isinstance(o, CommercialLineupCasePo)) == 0
    assert out["linked_pos"][0]["newly_linked"] is False
    assert case.commercial_status == "po_issued"


def test_add_new_po_appends_link():
    case = SimpleNamespace(id=3, commercial_status="po_issued", iteration_number=2)
    results = [
        _Res(scalar_list=[7]),     # distributor inference
        _Res(scalar_list=[]),      # new PO lookup -> none -> create
        _Res(scalar_list=[]),      # link check -> none -> add
        _Res(scalar_one_value=2),  # final count now 2 (1 existing + 1 new)
    ]
    db = _make_db(case, results)

    out = asyncio.run(mod.confirm_case_with_po(db, 3, po_numbers=["PO-1002"]))

    assert out["po_count"] == 2
    assert out["newly_linked_count"] == 1
    assert sum(1 for o in db._added if isinstance(o, CommercialLineupCasePo)) == 1
    assert case.commercial_status == "po_issued"
    case = SimpleNamespace(id=3, commercial_status="draft_imported", iteration_number=1)
    results = [
        _Res(scalar_list=[7]),
        _Res(scalar_list=[]),
        _Res(scalar_list=[]),
        _Res(scalar_one_value=1),
    ]
    db = _make_db(case, results)
    out = asyncio.run(mod.confirm_case_with_po(db, 3, po_numbers=["PO-2001"]))
    assert case.commercial_status == "po_pending"
    assert out["po_count"] == 1


def test_confirm_rejected_for_cancelled_status():
    case = SimpleNamespace(id=3, commercial_status="cancelled", iteration_number=1)
    db = _make_db(case, [])
    with pytest.raises(mod.CaseStatusNotConfirmableError):
        asyncio.run(mod.confirm_case_with_po(db, 3, po_numbers=["PO-1"]))


def test_confirm_unresolved_distributor_does_not_mint_null_po():
    case = SimpleNamespace(id=3, commercial_status="accepted", iteration_number=1)
    results = [
        _Res(scalar_list=[]),  # distributor inference -> none / ambiguous
    ]
    db = _make_db(case, results)

    with pytest.raises(mod.UnresolvedCaseDistributorError):
        asyncio.run(mod.confirm_case_with_po(db, 3, po_numbers=["PO-3001"]))

    assert sum(1 for o in db._added if isinstance(o, PurchaseOrder)) == 0
    assert sum(1 for o in db._added if isinstance(o, CommercialLineupCasePo)) == 0
    db.commit.assert_not_called()


def test_confirm_case_not_found():
    db = _make_db(None, [])
    with pytest.raises(mod.CaseNotFoundError):
        asyncio.run(mod.confirm_case_with_po(db, 999, po_numbers=["PO-1"]))


def test_blank_po_numbers_raise_value_error():
    case = SimpleNamespace(id=3, commercial_status="accepted", iteration_number=1)
    db = _make_db(case, [])
    with pytest.raises(ValueError):
        asyncio.run(mod.confirm_case_with_po(db, 3, po_numbers=["   ", "PO-", "INV "]))
