"""Unit tests for lineup case status semantics."""
import pytest

from app.services.commercial_planner.lineup_case_status import commercial_status_after_po_link


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        ("draft_imported", "po_pending"),
        ("validated", "po_pending"),
        ("accepted", "po_pending"),
        ("po_pending", "po_pending"),
        ("po_issued", "po_issued"),
        ("in_fulfillment", "in_fulfillment"),
        ("received_closed", "received_closed"),
        ("work_closed", "work_closed"),
        ("cancelled", "cancelled"),
    ],
)
def test_commercial_status_after_po_link(current: str, expected: str):
    assert commercial_status_after_po_link(current) == expected
