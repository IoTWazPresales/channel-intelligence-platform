"""Lineup case supersession restore helpers (winner delete + orphan repair)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.commercial_lineup import CommercialLineupCase

# Bulk backfill losers are created as superseded shells; active pre-supersession state is draft.
_RESTORE_COMMERCIAL_STATUS = "draft_imported"


def find_superseded_children(db: Session, winner_case_id: int) -> list[CommercialLineupCase]:
    return list(
        db.scalars(
            select(CommercialLineupCase).where(
                CommercialLineupCase.superseded_by_case_id == int(winner_case_id)
            )
        ).all()
    )


def superseded_child_summaries(cases: list[CommercialLineupCase]) -> list[dict[str, Any]]:
    return [
        {
            "id": int(c.id),
            "file_name": c.file_name,
            "period_label": c.period_label,
            "product_line": c.product_line,
            "commercial_status": c.commercial_status,
        }
        for c in cases
    ]


def restore_superseded_cases(db: Session, cases: list[CommercialLineupCase]) -> list[dict[str, Any]]:
    """Clear supersession pointer and restore active status (no delete)."""
    restored: list[dict[str, Any]] = []
    for case in cases:
        before = {
            "id": int(case.id),
            "commercial_status": case.commercial_status,
            "superseded_by_case_id": case.superseded_by_case_id,
        }
        case.superseded_by_case_id = None
        case.commercial_status = _RESTORE_COMMERCIAL_STATUS
        restored.append(
            {
                **before,
                "after_commercial_status": case.commercial_status,
                "after_superseded_by_case_id": case.superseded_by_case_id,
            }
        )
    if restored:
        db.flush()
    return restored


def find_orphan_superseded_cases(db: Session) -> list[CommercialLineupCase]:
    """Cases stuck superseded with no valid winner (pointer null after winner delete)."""
    return list(
        db.scalars(
            select(CommercialLineupCase).where(
                CommercialLineupCase.commercial_status == "superseded",
                CommercialLineupCase.superseded_by_case_id.is_(None),
            )
        ).all()
    )


def delete_lineup_case_restoring_children(db: Session, case: CommercialLineupCase) -> dict[str, Any]:
    """Restore superseded children, then delete the case (same transaction)."""
    children = find_superseded_children(db, int(case.id))
    restored = restore_superseded_cases(db, children)
    case_id = int(case.id)
    db.delete(case)
    db.flush()
    return {
        "deleted_case_id": case_id,
        "restored_children": restored,
        "restored_child_count": len(restored),
    }
