"""Unit tests for CPOR money-ceiling reapproval helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.cpor import budget_reapproval as mod


def test_should_require_reapproval_when_over_or_flagged(monkeypatch):
    monkeypatch.setattr(mod.tenant_profile, "CONSTRAINT_AXIS", "money")
    monkeypatch.setattr(mod.tenant_profile, "OVER_BUDGET_ACTION", "require_reapproval")
    assert mod.should_require_reapproval({"money_over": True, "needs_reapproval": False}) is True
    assert mod.should_require_reapproval({"money_over": False, "needs_reapproval": True}) is True
    assert mod.should_require_reapproval({"money_over": False, "needs_reapproval": False}) is False


def test_apply_reapproval_flag_sets_when_over(monkeypatch):
    monkeypatch.setattr(mod.tenant_profile, "CONSTRAINT_AXIS", "money")
    case = SimpleNamespace(needs_reapproval=False)
    assert mod.apply_reapproval_flag(MagicMock(), case, money_over=True) is True
    assert case.needs_reapproval is True


def test_evaluate_money_position_over_ceiling(monkeypatch):
    monkeypatch.setattr(mod.tenant_profile, "CONSTRAINT_AXIS", "money")
    monkeypatch.setattr(mod.tenant_profile, "OVER_BUDGET_ACTION", "require_reapproval")
    monkeypatch.setattr(mod.tenant_profile, "HARD_ENFORCE_BUDGET", True)
    monkeypatch.setattr(mod.tenant_profile, "MONEY_CEILING_USD", 50.0)
    monkeypatch.setattr(mod, "case_support_usd", lambda _s, _cid: 80.0)
    monkeypatch.setattr(mod, "portfolio_committed_usd", lambda _s, include_case_id=None: 80.0)

    case = SimpleNamespace(id=1, status="proposed", needs_reapproval=False)
    session = MagicMock()
    session.get.return_value = case
    pos = mod.evaluate_money_position(session, case_id=1, include_this_case=True)
    assert pos["money_over"] is True
    assert pos["status"] == "over"
    assert pos["case_support_usd"] == 80.0
    assert pos["money_ceiling_usd"] == 50.0
