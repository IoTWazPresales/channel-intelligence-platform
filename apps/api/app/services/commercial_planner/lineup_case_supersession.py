"""Lineup case supersession: soft-supersede + PO-link carry, restore, orphan repair.

PO-link carry (BACKLOG-118 / D-031): when a loser is soft-superseded, COPY its
``commercial_lineup_case_po`` rows onto the winner. Loser rows stay as historical
record — never deleted, moved, or repointed. Idempotent on
``(case_id, purchase_order_id)``. All-or-nothing with the status change (caller
owns the transaction).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.commercial_lineup import (
    CommercialLineupCase,
    CommercialLineupCasePo,
    CommercialLineupLine,
)
from app.services.commercial_planner.lineup_case_po_confirm import insert_case_po_link_if_missing
from app.services.commercial_planner.lineup_case_status import commercial_status_after_po_link
from app.services.steward_audit import record_steward_audit_sync

# Bulk backfill losers are created as superseded shells; active pre-supersession state is draft.
_RESTORE_COMMERCIAL_STATUS = "draft_imported"

# Provenance on winner link.notes — existing Text column; no schema change.
_CARRY_NOTES_PREFIX = "supersession_carry:from_case="


def carry_case_po_links_on_supersession(
    db: Session,
    *,
    loser_case_id: int,
    winner_case_id: int,
) -> dict[str, Any]:
    """COPY loser's ``commercial_lineup_case_po`` rows onto the winner.

    - Does **not** delete/move/repoint loser rows.
    - Idempotent: skip POs already on the winner (unique constraint).
    - Reuses ``insert_case_po_link_if_missing`` (same insert path as
      ``link_case_to_existing_po``). Does not commit — caller owns the txn.
    - Raises on failure so the surrounding transaction rolls back (all-or-nothing
      with status change when used via ``soft_supersede_lineup_case``).
    """
    loser_id = int(loser_case_id)
    winner_id = int(winner_case_id)
    if loser_id == winner_id:
        raise ValueError("carry_case_po_links_on_supersession: loser and winner must differ")

    winner = db.get(CommercialLineupCase, winner_id)
    if winner is None:
        raise ValueError(f"winner case {winner_id} not found")
    loser = db.get(CommercialLineupCase, loser_id)
    if loser is None:
        raise ValueError(f"loser case {loser_id} not found")

    loser_links = list(
        db.scalars(
            select(CommercialLineupCasePo)
            .where(CommercialLineupCasePo.case_id == loser_id)
            .order_by(CommercialLineupCasePo.id.asc())
        ).all()
    )
    notes = f"{_CARRY_NOTES_PREFIX}{loser_id}"
    carried = 0
    skipped_existing = 0
    for link in loser_links:
        inserted = insert_case_po_link_if_missing(
            db,
            case_id=winner_id,
            purchase_order_id=int(link.purchase_order_id),
            notes=notes,
        )
        if inserted:
            carried += 1
        else:
            skipped_existing += 1

    if carried:
        winner.commercial_status = commercial_status_after_po_link(winner.commercial_status)

    db.flush()

    winner_count = int(
        db.scalar(
            select(func.count())
            .select_from(CommercialLineupCasePo)
            .where(CommercialLineupCasePo.case_id == winner_id)
        )
        or 0
    )
    loser_count = int(
        db.scalar(
            select(func.count())
            .select_from(CommercialLineupCasePo)
            .where(CommercialLineupCasePo.case_id == loser_id)
        )
        or 0
    )
    return {
        "loser_case_id": loser_id,
        "winner_case_id": winner_id,
        "loser_link_count": loser_count,
        "winner_link_count": winner_count,
        "carried": carried,
        "skipped_existing": skipped_existing,
        "winner_commercial_status": winner.commercial_status,
    }


def soft_supersede_lineup_case(
    db: Session,
    *,
    loser_case_id: int,
    winner_case_id: int,
) -> dict[str, Any]:
    """Soft-supersede loser → winner and carry PO links in the same transaction.

    Sets ``commercial_status='superseded'`` + ``superseded_by_case_id`` then
    ``carry_case_po_links_on_supersession``. Does not commit — caller owns the txn.
    Idempotent when already superseded by the same winner (still re-runs carry).
    """
    loser_id = int(loser_case_id)
    winner_id = int(winner_case_id)
    if loser_id == winner_id:
        raise ValueError("soft_supersede_lineup_case: loser and winner must differ")

    loser = db.get(CommercialLineupCase, loser_id)
    winner = db.get(CommercialLineupCase, winner_id)
    if loser is None:
        raise ValueError(f"loser case {loser_id} not found")
    if winner is None:
        raise ValueError(f"winner case {winner_id} not found")

    already = (
        loser.commercial_status == "superseded"
        and loser.superseded_by_case_id is not None
        and int(loser.superseded_by_case_id) == winner_id
    )
    if not already:
        loser.superseded_by_case_id = winner_id
        loser.commercial_status = "superseded"
        db.flush()

    carry = carry_case_po_links_on_supersession(
        db, loser_case_id=loser_id, winner_case_id=winner_id
    )
    return {
        "loser_case_id": loser_id,
        "winner_case_id": winner_id,
        "already_superseded": already,
        "loser_commercial_status": loser.commercial_status,
        "loser_superseded_by_case_id": int(loser.superseded_by_case_id)
        if loser.superseded_by_case_id is not None
        else None,
        "carry": carry,
    }


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
