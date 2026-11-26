"""Commercial lineup case status semantics — steward work vs PO link vs work-queue close.

PO linking advances to ``po_pending`` (never downgrades ``po_issued``+). Steward entity
resolution stays open until ``work_closed``. Closing work removes the case from the default
Current lineups list only; synced plan lines, PO links, and reconciliation remain in intelligence.
"""
from __future__ import annotations

# Entity resolution + distributor assign
STEWARD_WORK_OPEN_STATUSES: frozenset[str] = frozenset(
    {
        "draft_imported",
        "validated",
        "pending_review",
        "accepted",
        "po_pending",
        "po_issued",
        "in_fulfillment",
    }
)

RESOLUTION_ALLOWED_CASE_STATUSES = STEWARD_WORK_OPEN_STATUSES

# Steward signed off the active work queue (not archived from intelligence)
WORK_CLOSED_STATUSES: frozenset[str] = frozenset({"work_closed"})

# At least one PO linked (or beyond in fulfillment ladder)
PO_LINKED_STATUSES: frozenset[str] = frozenset(
    {
        "po_pending",
        "po_issued",
        "in_fulfillment",
        "received_closed",
        "work_closed",
    }
)

# An accepted case: ``accepted`` or any later step on the ladder (a PO raised against it, fulfilment,
# closed). ``validated`` and ``pending_review`` come BEFORE acceptance; ``cancelled`` / ``superseded``
# are off the ladder. Warren (26 Nov): "ONLY ACCEPTED ONES FFS" (line-up SRP). ASSUMPTION: "accepted"
# includes the later statuses, because po_pending / po_issued cases are accepted cases a PO was raised
# against (linking a PO never un-accepts a case); live cases are mostly po_pending.
ACCEPTED_OR_LATER_STATUSES: frozenset[str] = frozenset({"accepted"}) | PO_LINKED_STATUSES

# Default list on Current lineups — hidden unless include_work_closed=true
DEFAULT_LIST_EXCLUDED_STATUSES: frozenset[str] = frozenset(
    {
        "work_closed",
        "cancelled",
        "superseded",
    }
)

_STATUSES_AT_OR_BEYOND_PO_ISSUED: frozenset[str] = frozenset(
    {
        "po_issued",
        "in_fulfillment",
        "received_closed",
        "work_closed",
    }
)

CLOSE_WORK_ALLOWED_FROM: frozenset[str] = frozenset(
    {
        "po_pending",
        "po_issued",
        "in_fulfillment",
    }
)


def commercial_status_after_po_link(current: str) -> str:
    """Status after linking a PO. Preserves existing ``po_issued``+ rows; new links -> ``po_pending``."""
    if current in {"cancelled", "superseded"}:
        return current
    if current in _STATUSES_AT_OR_BEYOND_PO_ISSUED:
        return current
    return "po_pending"
