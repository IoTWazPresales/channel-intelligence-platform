"""Lineup case supersession restore helpers (winner delete + orphan repair)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.commercial_lineup import (
    CommercialLineupCase,
    CommercialLineupCasePo,
    CommercialLineupLine,
)
from app.services.steward_audit import record_steward_audit_sync

# Bulk backfill losers are created as superseded shells; active pre-supersession state is draft.
_RESTORE_COMMERCIAL_STATUS = "draft_imported"


def _lineup_case_delete_counts(db: Session, case_id: int) -> tuple[int, int]:
    line_count = int(
        db.scalar(
            select(func.count()).select_from(CommercialLineupLine).where(CommercialLineupLine.case_id == case_id)
        )
        or 0
    )
    po_link_count = int(
        db.scalar(
            select(func.count())
            .select_from(CommercialLineupCasePo)
            .where(CommercialLineupCasePo.case_id == case_id)
        )
        or 0
    )
    return line_count, po_link_count


def lineup_case_delete_audit_fields(
    case: CommercialLineupCase,
    *,
    line_count: int,
    po_link_count: int,
    reason: str,
) -> dict[str, Any]:
    """Build steward_audit kwargs for a lineup case hard-delete (no schema change — extras in payload)."""
    return {
        "action": "delete",
        "importer": "lineup",
        "entity_type": "lineup_case",
        "entity_token": str(int(case.id)),
        "import_job_id": int(case.import_job_id) if case.import_job_id is not None else None,
        "target_dim": "commercial_lineup_case",
        "target_id": int(case.id),
        "payload": {
            "case_id": int(case.id),
            "source_context": case.source_context,
            "period_label": case.period_label,
            "business_unit": case.business_unit,
            "product_line": case.product_line,
            "file_name": case.file_name,
            "commercial_status": case.commercial_status,
            "line_count": int(line_count),
            "po_link_count": int(po_link_count),
            "reason": reason,
        },
    }


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


def delete_lineup_case_restoring_children(
    db: Session,
    case: CommercialLineupCase,
    *,
    user: dict | None = None,
    reason: str = "supersession_winner_delete",
) -> dict[str, Any]:
    """Restore superseded children, then delete the case (same transaction)."""
    children = find_superseded_children(db, int(case.id))
    restored = restore_superseded_cases(db, children)
    case_id = int(case.id)
    line_count, po_link_count = _lineup_case_delete_counts(db, case_id)
    record_steward_audit_sync(
        user,
        db=db,
        **lineup_case_delete_audit_fields(
            case,
            line_count=line_count,
            po_link_count=po_link_count,
            reason=reason,
        ),
    )
    db.delete(case)
    db.flush()
    return {
        "deleted_case_id": case_id,
        "restored_children": restored,
        "restored_child_count": len(restored),
    }
