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
