"""Unit coverage for the bounded promo_not_activated worklist count (Codex P2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.brief_signals import _promo_not_activated_worklist_count


def test_promo_worklist_count_scopes_then_uses_latest_flags_only() -> None:
    """Tenant/account scope first; ready+not_activated from aggregates + latest flags."""
    now = datetime.now(timezone.utc)
    early = now - timedelta(days=20)
    late = now - timedelta(days=1)

    session = MagicMock()

    # 1) tenant customers -> [10, 20]; account filter keeps 10
    # 2) listings for customer 10 -> listing 101
    # 3) stats execute -> one listing with 2 obs spanning 19d
    # 4) latest flags execute -> not_activated
    scalars_returns = [
        [10, 20],  # customers
        [101],  # listing ids
    ]

    def scalars(stmt):  # noqa: ANN001
        return SimpleNamespace(all=lambda: scalars_returns.pop(0))

    session.scalars.side_effect = scalars

    execute_returns = [
        [(101, 2, early, late)],  # aggregates
        [(101, {"cpor_activation": {"status": "not_activated", "case_id": 7}})],  # latest flags
    ]

    def execute(stmt):  # noqa: ANN001
        return SimpleNamespace(all=lambda: execute_returns.pop(0))

    session.execute.side_effect = execute

    n = _promo_not_activated_worklist_count(
        session, tenant_id="t1", account_ids=frozenset({10})
    )
    assert n == 1
    assert session.scalars.call_count == 2
    assert session.execute.call_count == 2


def test_promo_worklist_count_empty_when_no_scoped_customers() -> None:
    session = MagicMock()
    session.scalars.return_value = SimpleNamespace(all=lambda: [])
    n = _promo_not_activated_worklist_count(
        session, tenant_id="t1", account_ids=frozenset({99})
    )
    assert n == 0
    session.execute.assert_not_called()


def test_promo_worklist_count_skips_short_history() -> None:
    now = datetime.now(timezone.utc)
    session = MagicMock()
    scalars_returns = [[10], [101]]

    def scalars(stmt):  # noqa: ANN001
        return SimpleNamespace(all=lambda: scalars_returns.pop(0))

    session.scalars.side_effect = scalars
    execute_returns = [
        [(101, 2, now - timedelta(days=3), now)],  # span 3 < 14
        [(101, {"cpor_activation": {"status": "not_activated"}})],
    ]

    def execute(stmt):  # noqa: ANN001
        return SimpleNamespace(all=lambda: execute_returns.pop(0))

    session.execute.side_effect = execute
    assert _promo_not_activated_worklist_count(session, tenant_id="t1", account_ids=None) == 0
