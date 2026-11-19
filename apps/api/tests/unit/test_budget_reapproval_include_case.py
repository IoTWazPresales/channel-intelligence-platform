"""B-1: the money ceiling counts the case being checked when the ledger has no commit for it.

The ledger only holds ``commit`` rows once a case is approved. A draft or proposed case
checked at the export gate, the propose/resend flag or the budget_gate has none, so its
own support must be added. A case that already has commit rows is in the ledger draw
and must not be counted twice. Fakes only; the DB twin is
``tests/test_budget_ledger_ceiling_include_case_db.py``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.services import budget_ledger
from app.services.cpor import budget_reapproval as mod


@pytest.fixture
def ledger(monkeypatch):
    """Ledger draw 900. The case under test has 500 of support."""
    state = {"draw": 900.0, "has_commit": False}
    monkeypatch.setattr(budget_ledger, "used_usd", lambda _s, landed_quarter=None: state["draw"])
    monkeypatch.setattr(budget_ledger, "case_has_commit_rows", lambda _s, _cid: state["has_commit"])
    monkeypatch.setattr(mod, "case_support_usd", lambda _s, _cid: 500.0)
    return state


def test_draft_case_support_is_added_when_included(ledger):
    assert mod.portfolio_committed_usd(MagicMock(), include_case_id=7) == 1400.0


def test_case_not_included_is_not_added(ledger):
    assert mod.portfolio_committed_usd(MagicMock(), include_case_id=None) == 900.0


def test_case_with_commit_rows_is_not_double_counted(ledger):
    ledger["has_commit"] = True
    assert mod.portfolio_committed_usd(MagicMock(), include_case_id=7) == 900.0


def test_no_ledger_table_keeps_pre_ledger_path(monkeypatch):
    monkeypatch.setattr(budget_ledger, "used_usd", lambda _s, landed_quarter=None: None)
    seen = {}

    def fake(_s, *, include_case_id=None):
        seen["include"] = include_case_id
        return 123.0

    monkeypatch.setattr(mod, "_portfolio_committed_from_cases", fake)
    assert mod.portfolio_committed_usd(MagicMock(), include_case_id=7) == 123.0
    assert seen["include"] == 7


def test_ceiling_1000_draw_900_draft_500_is_over(ledger, monkeypatch):
    """The export gate (cpor_exports) and the propose flag both read this position."""
    monkeypatch.setattr(mod.tenant_profile, "CONSTRAINT_AXIS", "money")
    monkeypatch.setattr(mod.tenant_profile, "OVER_BUDGET_ACTION", "require_reapproval")
    monkeypatch.setattr(mod.tenant_profile, "HARD_ENFORCE_BUDGET", True)
    monkeypatch.setattr(mod, "money_ceiling_usd", lambda: 1000.0)
    session = MagicMock()
    session.get.return_value = SimpleNamespace(id=7, status="draft", needs_reapproval=False)

    position = mod.evaluate_money_position(session, case_id=7, include_this_case=True)

    assert position["portfolio_committed_usd"] == 1400.0
    assert position["money_over"] is True
    assert mod.should_require_reapproval(position) is True


def test_export_gate_returns_409_for_draft_over_ceiling(ledger, monkeypatch):
    from app.api.v1.endpoints import cpor_exports
    from fastapi import HTTPException

    monkeypatch.setattr(mod.tenant_profile, "CONSTRAINT_AXIS", "money")
    monkeypatch.setattr(mod.tenant_profile, "OVER_BUDGET_ACTION", "require_reapproval")
    monkeypatch.setattr(mod.tenant_profile, "HARD_ENFORCE_BUDGET", True)
    monkeypatch.setattr(mod, "money_ceiling_usd", lambda: 1000.0)
    case = SimpleNamespace(id=7, status="draft", needs_reapproval=False)
    session = MagicMock()
    session.get.return_value = case

    class _Open:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(cpor_exports, "SessionLocal", lambda: _Open())
    monkeypatch.setattr(cpor_exports, "_load_case", lambda _s, _cid: case)

    with pytest.raises(HTTPException) as caught:
        cpor_exports.generate_export(7, {"id": "planner-1"})

    assert caught.value.status_code == 409
    assert caught.value.detail["budget"]["portfolio_committed_usd"] == 1400.0


def test_case_has_commit_rows_reads_across_product_lines(monkeypatch):
    """The commit check must see every product line, like the draw itself."""
    calls = []

    def fake_select(_session, stmt):
        calls.append(stmt)
        return [(1,)]

    monkeypatch.setattr(budget_ledger, "_select_across_product_lines", fake_select)
    assert budget_ledger.case_has_commit_rows(MagicMock(), 7) is True
    assert len(calls) == 1
    monkeypatch.setattr(budget_ledger, "_select_across_product_lines", lambda _s, _stmt: [])
    assert budget_ledger.case_has_commit_rows(MagicMock(), 7) is False
    monkeypatch.setattr(budget_ledger, "_select_across_product_lines", lambda _s, _stmt: None)
    assert budget_ledger.case_has_commit_rows(MagicMock(), 7) is False
