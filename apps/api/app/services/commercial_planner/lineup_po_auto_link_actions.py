"""Unit 4 — apply / dismiss actions for PO↔lineup auto-link proposals."""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupPoAutoLinkDismiss
from app.models.purchase_order import PurchaseOrder
from app.services.commercial_planner.lineup_case_po_confirm import (
    CaseNotFoundError,
    CaseStatusNotConfirmableError,
    link_case_to_existing_po,
)


class ProposalNotFoundError(Exception):
    pass


async def dismiss_auto_link_proposal(
    db: AsyncSession,
    *,
    proposal_key: str,
    case_id: int,
    purchase_order_id: int,
    reason_code: str,
) -> dict[str, Any]:
    key = (proposal_key or "").strip()
    if not key:
        raise ValueError("proposal_key is required")
    reason = (reason_code or "").strip()
    if not reason:
        raise ValueError("reason_code is required")

    existing = (
        await db.execute(
            select(CommercialLineupPoAutoLinkDismiss).where(
                CommercialLineupPoAutoLinkDismiss.proposal_key == key
            )
        )
    ).scalars().first()
    if existing is None:
        db.add(
            CommercialLineupPoAutoLinkDismiss(
                proposal_key=key,
                case_id=int(case_id),
                purchase_order_id=int(purchase_order_id),
                reason_code=reason,
            )
        )
    else:
        existing.reason_code = reason
    await db.commit()
    return {
        "proposal_key": key,
        "case_id": int(case_id),
        "purchase_order_id": int(purchase_order_id),
        "reason_code": reason,
        "dismissed": True,
    }


async def restore_auto_link_proposal(db: AsyncSession, *, proposal_key: str) -> dict[str, Any]:
    key = (proposal_key or "").strip()
    if not key:
        raise ValueError("proposal_key is required")
    row = (
        await db.execute(
            select(CommercialLineupPoAutoLinkDismiss).where(
                CommercialLineupPoAutoLinkDismiss.proposal_key == key
            )
        )
    ).scalars().first()
    if row is None:
        raise ProposalNotFoundError(key)
    await db.execute(
        delete(CommercialLineupPoAutoLinkDismiss).where(
            CommercialLineupPoAutoLinkDismiss.proposal_key == key
        )
    )
    await db.commit()
    return {"proposal_key": key, "restored": True}


async def apply_auto_link_proposals(
    db: AsyncSession,
    *,
    items: list[dict[str, Any]],
    notes: str | None = None,
) -> dict[str, Any]:
    """Link selected proposals via existing confirm path (one PO per case item)."""
    if not items:
        raise ValueError("At least one proposal item is required")

    applied: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for raw in items:
        case_id = int(raw["case_id"])
        purchase_order_id = int(raw["purchase_order_id"])
        item_notes = raw.get("notes") or notes
        try:
            po = await db.get(PurchaseOrder, purchase_order_id)
            if po is None:
                raise ValueError(f"Purchase order {purchase_order_id} not found")
            result = await link_case_to_existing_po(
                db,
                case_id,
                purchase_order_id,
                notes=item_notes,
                commit=True,
            )
            applied.append(
                {
                    "case_id": case_id,
                    "purchase_order_id": purchase_order_id,
                    "po_number": po.po_number_raw,
                    "commercial_status": result.get("commercial_status"),
                    "newly_linked": result.get("newly_linked"),
                }
            )
        except (CaseNotFoundError, CaseStatusNotConfirmableError, ValueError) as exc:
            errors.append(
                {
                    "case_id": case_id,
                    "purchase_order_id": purchase_order_id,
                    "error": str(exc),
                }
            )

    return {
        "applied": applied,
        "applied_count": len(applied),
        "error_count": len(errors),
        "errors": errors,
    }
