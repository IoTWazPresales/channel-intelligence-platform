"""Unit coverage for the bounded promo_not_activated worklist count (Codex P2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.brief_signals import _promo_not_activated_worklist_count


def test_promo_worklist_count_uses_latest_flags_only() -> None:
    """Ready+not_activated from aggregates + latest flags (no full observation history)."""
    now = datetime.now(timezone.utc)
    early = now - timedelta(days=20)
    late = now - timedelta(days=1)

    session = MagicMock()
    execute_returns = [
        [(101, 2, early, late)],  # aggregates
        [(101, {"cpor_activation": {"status": "not_activated", "case_id": 7}})],  # latest flags
    ]

    def execute(_stmt):  # noqa: ANN001
        return SimpleNamespace(all=lambda: execute_returns.pop(0))

    session.execute.side_effect = execute

    n = _promo_not_activated_worklist_count(
        session, tenant_id="t1", account_ids=frozenset({10})
    )
    assert n == 1
    assert session.execute.call_count == 2
    session.scalars.assert_not_called()


def test_promo_worklist_count_empty_when_no_observation_stats() -> None:
    session = MagicMock()
    session.execute.return_value = SimpleNamespace(all=lambda: [])
    n = _promo_not_activated_worklist_count(
        session, tenant_id="t1", account_ids=frozenset({99})
    )
    assert n == 0
    assert session.execute.call_count == 1


def test_promo_worklist_count_skips_short_history() -> None:
    now = datetime.now(timezone.utc)
    session = MagicMock()
    execute_returns = [
        [(101, 2, now - timedelta(days=3), now)],  # span 3 < 14
        [(101, {"cpor_activation": {"status": "not_activated"}})],
    ]

    def execute(_stmt):  # noqa: ANN001
        return SimpleNamespace(all=lambda: execute_returns.pop(0))

    session.execute.side_effect = execute
    assert _promo_not_activated_worklist_count(session, tenant_id="t1", account_ids=None) == 0
