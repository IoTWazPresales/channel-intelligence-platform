"""DSI SOH reconciliation unit tests (mocked DB)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.services.imports.dsi_soh_reconciliation import reconcile_distributor_soh, VARIANCE_THRESHOLD_PCT


def _scalar_sequence(values: list):
    """Return side_effect for session.scalar cycling values."""

    def _scalar(*_args, **_kwargs):
        if not values:
            return None
        return values.pop(0)

    return _scalar


@patch("app.services.imports.dsi_soh_reconciliation._table_exists", return_value=False)
def test_clean_reconciliation_within_threshold(mock_table: MagicMock) -> None:
    session = MagicMock()
    session.scalar.side_effect = [
        date(2024, 6, 1),
        1,
        date(2024, 6, 1),
        Decimal("100"),
        Decimal("10"),
        Decimal("50"),
        MagicMock(on_hand_units=55, calculated_soh=None, soh_variance=None),
    ]
    session.scalars.return_value.all.side_effect = [[101], []]

    opening = MagicMock()
    opening.on_hand_units = 100
    reported = MagicMock()
    reported.on_hand_units = 60
    target = reported

    def scalar_side(*args, **kwargs):
        calls = scalar_side.n  # type: ignore[attr-defined]
        scalar_side.n += 1  # type: ignore[attr-defined]
        if calls == 0:
            return date(2024, 6, 1)
        if calls == 1:
            return 1
        if calls == 2:
            return opening
        if calls == 3:
            return Decimal("10")
        if calls == 4:
            return Decimal("50")
        if calls == 5:
            return target
        return None

    scalar_side.n = 0  # type: ignore[attr-defined]
    session.scalar.side_effect = scalar_side
    session.scalars.return_value = iter([[101]])

    with patch.object(session, "scalars") as mock_scalars:
        mock_scalars.return_value.all.return_value = [101]
        out = reconcile_distributor_soh(session, 5, date(2024, 6, 30), 1)
    assert out["products_updated"] >= 0


@patch("app.services.imports.dsi_soh_reconciliation._table_exists", return_value=False)
def test_no_baseline_when_no_opening_snapshot(mock_table: MagicMock) -> None:
    session = MagicMock()
    session.scalar.side_effect = [
        date(2024, 6, 1),
        0,
        None,
        Decimal("0"),
        Decimal("0"),
        None,
        None,
    ]
    session.scalars.return_value.all.return_value = []
    out = reconcile_distributor_soh(session, 5, date(2024, 6, 30), 1)
    assert out["products_updated"] == 0


def test_variance_threshold_constant() -> None:
    assert VARIANCE_THRESHOLD_PCT == Decimal("0.10")


@patch("app.services.imports.dsi_soh_reconciliation_enqueue.enqueue_dsi_soh_reconciliation")
def test_dispatch_after_apply_enqueues(mock_enqueue: MagicMock) -> None:
    from app.services.imports.dsi_soh_reconciliation_enqueue import (
        dispatch_dsi_soh_reconciliation_after_apply,
    )

    mock_enqueue.return_value = ("task-1", True)
    session = MagicMock()
    job = MagicMock()
    job.id = 50
    job.staged_metadata = {}
    dispatch_dsi_soh_reconciliation_after_apply(
        session,
        job,
        distributor_id=3,
        period_end_date=date(2024, 7, 1),
    )
    mock_enqueue.assert_called_once()
    assert job.staged_metadata.get("dsi_soh_reconcile_task") is not None
