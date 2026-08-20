"""Leftover-repair constants and audit-match gate (no DB)."""

from app.services.customer_leftover_repair import (
    COMPUSPEED_LOSER_ID,
    EXPECTED_DIRTY_LOSERS,
    EXPECTED_LEFTOVER_ROWS,
    LeftoverRepairDriftError,
    assert_preview_matches_audit,
)


def test_audit_lock_matches_unit_spec() -> None:
    assert EXPECTED_DIRTY_LOSERS == 9
    assert EXPECTED_LEFTOVER_ROWS == 3266
    assert COMPUSPEED_LOSER_ID == 1152


def test_assert_preview_matches_audit_rejects_drift() -> None:
    try:
        assert_preview_matches_audit({"dirty_loser_count": 8, "total_leftover_rows": 3266})
    except LeftoverRepairDriftError as exc:
        assert "drift" in str(exc)
    else:
        raise AssertionError("expected LeftoverRepairDriftError")
