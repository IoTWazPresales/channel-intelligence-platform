"""Unit 6a — PO-link unlink service helpers (no DB)."""

from __future__ import annotations

from app.services.commercial_planner.lineup_case_po_unlink import (
    _carried_under_d032,
    commercial_status_after_po_unlink,
)


def test_carried_under_d032_prefix():
    assert _carried_under_d032("supersession_carry:from_case=9") is True
    assert _carried_under_d032("manual note") is False
    assert _carried_under_d032(None) is False


def test_status_after_unlink_reverts_po_pending_only():
    assert commercial_status_after_po_unlink("po_pending", remaining_po_count=0) == "draft_imported"
    assert commercial_status_after_po_unlink("po_pending", remaining_po_count=1) == "po_pending"
    assert commercial_status_after_po_unlink("po_issued", remaining_po_count=0) == "po_issued"
    assert commercial_status_after_po_unlink("draft_imported", remaining_po_count=0) == "draft_imported"
