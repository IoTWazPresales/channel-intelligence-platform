"""Unit tests for lineup distributor suggestion (shipment corroboration) + case assignment."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.commercial_planner import lineup_case_distributor_assign as assign_mod
from app.services.commercial_planner import lineup_case_suggested_pos as suggest_mod


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


# --- suggest_distributors_for_case -------------------------------------------------


def test_suggest_distributors_case_not_found():
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(suggest_mod.CaseNotFoundError):
        asyncio.run(suggest_mod.suggest_distributors_for_case(db, 1))


def test_suggest_distributors_empty_when_no_products():
    db = MagicMock()
    db.get = AsyncMock(return_value=SimpleNamespace(id=2))
    db.execute = AsyncMock(
        side_effect=[
            _Res(scalar_list=[]),  # product ids
            _Res(scalar_list=[]),  # already-assigned line distributors
        ]
    )
    out = asyncio.run(suggest_mod.suggest_distributors_for_case(db, 2))
    assert out["converged"] is False
    assert out["suggested_distributors"] == []
    assert out["distinct_count"] == 0


def test_suggest_distributors_converged_single():
    # row shape: (dist_id, code, name, matched_count, shipped_units, po_count)
    row = (7, "MUSTEK", "Mustek", 3, 240.0, 2)
    db = MagicMock()
    db.get = AsyncMock(return_value=SimpleNamespace(id=5))
    db.execute = AsyncMock(
        side_effect=[
            _Res(scalar_list=[10, 11, 12]),  # product ids
            _Res(scalar_list=[]),  # already-assigned
            _Res(rows=[row]),  # rollup
        ]
    )
    out = asyncio.run(suggest_mod.suggest_distributors_for_case(db, 5))
    assert out["converged"] is True
    assert out["converged_distributor_id"] == 7
    assert out["distinct_count"] == 1
    assert out["suggested_distributors"][0]["distributor_code"] == "MUSTEK"
    assert out["suggested_distributors"][0]["matched_product_count"] == 3
    assert out["suggested_distributors"][0]["already_assigned"] is False


def test_suggest_distributors_ambiguous_multiple():
    rows = [
        (7, "MUSTEK", "Mustek", 3, 240.0, 2),
        (8, "RECTRON", "Rectron", 2, 90.0, 1),
    ]
    db = MagicMock()
    db.get = AsyncMock(return_value=SimpleNamespace(id=6))
    db.execute = AsyncMock(
        side_effect=[
            _Res(scalar_list=[10, 11]),  # product ids
            _Res(scalar_list=[8]),  # already-assigned includes 8
            _Res(rows=rows),
        ]
    )
    out = asyncio.run(suggest_mod.suggest_distributors_for_case(db, 6))
    assert out["converged"] is False
    assert out["converged_distributor_id"] is None
    assert out["distinct_count"] == 2
    flags = {s["distributor_id"]: s["already_assigned"] for s in out["suggested_distributors"]}
    assert flags == {7: False, 8: True}


# --- assign_case_distributor -------------------------------------------------------


def _line(**kw):
    base = dict(
        distributor_id=None,
        customer_id=1,
        customer_token=None,
        product_id=10,
        raw_row_payload={},
        diagnostic_codes=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_assign_existing_distributor_to_unassigned_lines():
    case = SimpleNamespace(id=5, commercial_status="draft_imported")
    dim = SimpleNamespace(id=7, code="MUSTEK", name="Mustek")
    lines = [_line(), _line(), _line(distributor_id=99)]  # third already assigned
    db = MagicMock()
    db.get = AsyncMock(side_effect=[case, dim])
    db.execute = AsyncMock(return_value=_Res(scalar_list=lines))
    db.commit = AsyncMock()
    out = asyncio.run(assign_mod.assign_case_distributor(db, 5, distributor_id=7))
    assert out["distributor_id"] == 7
    assert out["distributor_created"] is False
    assert out["updated_lines"] == 2  # only the two unassigned
    assert lines[0].distributor_id == 7
    assert lines[1].distributor_id == 7
    assert lines[2].distributor_id == 99  # untouched
    db.commit.assert_awaited_once()


def test_assign_creates_distributor_when_requested():
    case = SimpleNamespace(id=5, commercial_status="draft_imported")
    lines = [_line()]
    created_rows = []
    db = MagicMock()
    db.get = AsyncMock(return_value=case)
    db.scalar = AsyncMock(return_value=0)  # code does not exist
    db.add = MagicMock(side_effect=lambda r: created_rows.append(r))

    async def _flush():
        created_rows[0].id = 42

    db.flush = AsyncMock(side_effect=_flush)
    db.execute = AsyncMock(return_value=_Res(scalar_list=lines))
    db.commit = AsyncMock()
    out = asyncio.run(
        assign_mod.assign_case_distributor(db, 5, new_code="MUSTEK", new_name="Mustek")
    )
    assert out["distributor_created"] is True
    assert out["distributor_id"] == 42
    assert out["updated_lines"] == 1
    assert lines[0].distributor_id == 42


def test_assign_rejects_duplicate_code():
    case = SimpleNamespace(id=5, commercial_status="draft_imported")
    db = MagicMock()
    db.get = AsyncMock(return_value=case)
    db.scalar = AsyncMock(return_value=1)  # code exists
    with pytest.raises(assign_mod.DistributorCodeExistsError):
        asyncio.run(assign_mod.assign_case_distributor(db, 5, new_code="MUSTEK", new_name="Mustek"))


def test_assign_rejects_unknown_distributor():
    case = SimpleNamespace(id=5, commercial_status="draft_imported")
    db = MagicMock()
    db.get = AsyncMock(side_effect=[case, None])  # dim lookup returns None
    with pytest.raises(assign_mod.DistributorNotFoundError):
        asyncio.run(assign_mod.assign_case_distributor(db, 5, distributor_id=999))


def test_assign_rejects_non_resolvable_status():
    case = SimpleNamespace(id=5, commercial_status="po_issued")
    db = MagicMock()
    db.get = AsyncMock(return_value=case)
    with pytest.raises(assign_mod.CaseStatusNotResolvableError):
        asyncio.run(assign_mod.assign_case_distributor(db, 5, distributor_id=7))


def test_assign_case_not_found():
    db = MagicMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(assign_mod.CaseNotFoundError):
        asyncio.run(assign_mod.assign_case_distributor(db, 1, distributor_id=7))
