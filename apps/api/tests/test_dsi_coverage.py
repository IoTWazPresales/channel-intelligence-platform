"""DSI weekly coverage read model tests."""

from __future__ import annotations

from datetime import date

from app.services.imports.dsi_coverage import (
    compute_dsi_coverage,
    iso_week_start,
    signal_coverage,
    trailing_iso_weeks,
)


def test_iso_week_start_is_monday() -> None:
    # 2026-07-16 is Thursday
    assert iso_week_start(date(2026, 7, 16)) == date(2026, 7, 13)


def test_trailing_iso_weeks_count() -> None:
    weeks = trailing_iso_weeks(end=date(2026, 7, 16), count=4)
    assert len(weeks) == 4
    assert weeks[-1] == iso_week_start(date(2026, 7, 16))


def test_signal_coverage_missed_only_when_weekly_active() -> None:
    window = trailing_iso_weeks(end=date(2026, 7, 16), count=6)
    covered = {window[0], window[2], window[4]}
    active, _cov, missed = signal_coverage(covered, window)
    assert active is True
    assert len(missed) == 3


def test_signal_coverage_sparse_not_active() -> None:
    window = trailing_iso_weeks(end=date(2026, 7, 16), count=8)
    covered = {window[0], window[3]}
    active, _cov, missed = signal_coverage(covered, window)
    assert active is False
    assert missed == []


def test_compute_dsi_coverage_no_tables() -> None:
    from unittest.mock import MagicMock, patch

    mock_session = MagicMock()
    with patch("app.services.imports.dsi_coverage._table_exists", return_value=False):
        payload = compute_dsi_coverage(mock_session, weeks=8, as_of=date(2026, 7, 16))
    assert payload["data_unavailable"] is True
    assert payload["flags"] == []
