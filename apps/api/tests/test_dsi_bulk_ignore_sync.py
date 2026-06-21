"""DSI bulk ignore — single-commit batch writer."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.imports.dsi_bulk_ignore_sync import run_dsi_bulk_ignore_sync


def _cand(
    cid: int,
    *,
    job_id: int = 43,
    entity_type: str = "product_identifier",
    status: str = "open",
    row_count: int = 5,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=cid,
        import_job_id=job_id,
        entity_type=entity_type,
        status=status,
        row_count=row_count,
        total_units=2.0,
        total_reported_value=10.0,
        context={},
    )



def test_bulk_ignore_single_commit_for_many_candidates() -> None:
    session = MagicMock()
    cands = {1: _cand(1), 2: _cand(2), 3: _cand(3)}

    def _get(model, cid: int):
        if getattr(model, "__name__", "") == "ImportJob":
            return SimpleNamespace(id=43)
        return cands.get(int(cid))

    session.get.side_effect = _get

    with patch(
        "app.services.imports.dsi_bulk_ignore_sync.commit_session_with_transient_retry"
    ) as mock_commit:
        out = run_dsi_bulk_ignore_sync(session, 43, [1, 2, 3], notes="batch note")

    assert out["applied"] == 3
    assert out["failed"] == 0
    mock_commit.assert_called_once_with(session)
    assert cands[1].status == "ignored"
    assert cands[1].context["steward_ignore_notes"] == "batch note"


def test_bulk_ignore_skips_terminal_and_not_found() -> None:
    session = MagicMock()
    open_cand = _cand(10)
    terminal = _cand(11, status="ignored")

    def _get(model, cid: int):
        if getattr(model, "__name__", "") == "ImportJob":
            return SimpleNamespace(id=43)
        if cid == 10:
            return open_cand
        if cid == 11:
            return terminal
        return None

    session.get.side_effect = _get

    with patch(
        "app.services.imports.dsi_bulk_ignore_sync.commit_session_with_transient_retry"
    ) as mock_commit:
        out = run_dsi_bulk_ignore_sync(session, 43, [10, 11, 99])

    assert out["applied"] == 1
    assert out["failed"] == 2
    mock_commit.assert_called_once_with(session)
    by_id = {r["candidate_id"]: r for r in out["results"]}
    assert by_id[10]["ok"] is True
    assert by_id[10]["entity_type"] == "product_identifier"
    assert by_id[10]["row_count"] == 5
    assert by_id[11]["detail"] == "Candidate already terminal"
    assert by_id[99]["detail"] == "Candidate not found for this job"


def test_bulk_ignore_no_commit_when_nothing_pending() -> None:
    session = MagicMock()

    def _get(model, cid: int):
        if getattr(model, "__name__", "") == "ImportJob":
            return SimpleNamespace(id=43)
        return None

    session.get.side_effect = _get

    with patch(
        "app.services.imports.dsi_bulk_ignore_sync.commit_session_with_transient_retry"
    ) as mock_commit:
        out = run_dsi_bulk_ignore_sync(session, 43, [404])

    assert out["applied"] == 0
    mock_commit.assert_not_called()
