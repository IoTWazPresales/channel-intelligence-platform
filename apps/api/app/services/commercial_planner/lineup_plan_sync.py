"""Persist lineup → plan sync linkage on CommercialLineupLine without schema migrations.

Uses a namespaced key inside ``raw_row_payload`` so audit/upload columns stay intact.
"""

from __future__ import annotations

from typing import Any

from app.models.commercial_lineup import CommercialLineupLine

# Stable namespace — avoid collisions with parser ``uploaded`` / staging keys.
CAP_COMMERCIAL_PLAN_SYNC_KEY: str = "_cip_commercial_plan_sync"


def synced_commercial_plan_line_id(raw_row_payload: dict[str, Any] | list | None) -> int | None:
    """Return linked ``commercial_plan_line.id`` when this lineup row was synced to a plan."""
    if not isinstance(raw_row_payload, dict):
        return None
    block = raw_row_payload.get(CAP_COMMERCIAL_PLAN_SYNC_KEY)
    if not isinstance(block, dict):
        return None
    lid = block.get("commercial_plan_line_id")
    if lid is None:
        return None
    try:
        return int(lid)
    except (TypeError, ValueError):
        return None


def attach_plan_line_sync_to_lineup_row(
    ln: CommercialLineupLine,
    *,
    commercial_plan_id: int,
    commercial_plan_line_id: int,
) -> None:
    """Merge sync linkage into ``raw_row_payload`` (mutates ``ln`` in memory; caller commits)."""
    base: dict[str, Any] = dict(ln.raw_row_payload) if isinstance(ln.raw_row_payload, dict) else {}
    base[CAP_COMMERCIAL_PLAN_SYNC_KEY] = {
        "commercial_plan_id": int(commercial_plan_id),
        "commercial_plan_line_id": int(commercial_plan_line_id),
    }
    ln.raw_row_payload = base
