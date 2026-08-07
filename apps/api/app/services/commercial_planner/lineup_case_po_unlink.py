"""Steward unlink of active ``commercial_lineup_case_po`` rows (BACKLOG-109 / Unit 6a).

W6-2: refuse links whose case is ``superseded`` (historical D-032 trail).
W6-3: real DELETE; ``steward_audit`` is history (same transaction).
Protected cases require ``allow_protected`` (Unit 2); bulk callers must leave it false.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupCasePo
from app.models.purchase_order import PurchaseOrder
from app.services.commercial_planner.lineup_case_bulk_protection import (
    CaseProtectedError,
    evaluate_case_bulk_protection,
)
from app.services.commercial_planner.lineup_case_supersession import _CARRY_NOTES_PREFIX
from app.services.steward_audit import record_steward_audit

_CARRY_PREFIX = _CARRY_NOTES_PREFIX  # "supersession_carry:from_case="


class CasePoLinkNotFoundError(Exception):
    def __init__(self, case_id: int, purchase_order_id: int):
        self.case_id = case_id
        self.purchase_order_id = purchase_order_id
        super().__init__(f"No link case={case_id} po={purchase_order_id}")


class HistoricalCasePoLinkError(Exception):
    """W6-2: link sits on a superseded case — refuse (preserves D-032 audit trail)."""

    def __init__(self, case_id: int, purchase_order_id: int, link_id: int):
        self.case_id = case_id
        self.purchase_order_id = purchase_order_id
        self.link_id = link_id
        super().__init__(
            f"Refuse unlink: case {case_id} is superseded (historical link id={link_id})"
        )


def _carried_under_d032(notes: str | None) -> bool:
    return bool(notes and str(notes).startswith(_CARRY_PREFIX))


def commercial_status_after_po_unlink(current: str, *, remaining_po_count: int) -> str:
    """Recompute status after removing a PO link.

    Only ``po_pending`` with zero remaining links reverts to ``draft_imported``.
    Never downgrade ``po_issued``+.
    """
    if remaining_po_count > 0:
        return current
    if current == "po_pending":
        return "draft_imported"
    return current


async def list_active_case_po_links(
    db: AsyncSession,
    *,
    case_id: int | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Active (non-superseded-case) ``commercial_lineup_case_po`` rows for the worklist."""
    q = (
        select(CommercialLineupCasePo, CommercialLineupCase, PurchaseOrder)
        .join(CommercialLineupCase, CommercialLineupCase.id == CommercialLineupCasePo.case_id)
        .join(PurchaseOrder, PurchaseOrder.id == CommercialLineupCasePo.purchase_order_id)
        .where(CommercialLineupCase.commercial_status != "superseded")
        .order_by(CommercialLineupCasePo.id.desc())
        .limit(max(1, min(int(limit), 2000)))
    )
    if case_id is not None:
        q = q.where(CommercialLineupCasePo.case_id == int(case_id))

    rows = list((await db.execute(q)).all())

    # po_link_count per case for protection
    case_ids = sorted({int(c.id) for _, c, _ in rows})
    counts: dict[int, int] = {cid: 0 for cid in case_ids}
    if case_ids:
        for cid, n in (
            await db.execute(
                select(CommercialLineupCasePo.case_id, func.count(CommercialLineupCasePo.id))
                .where(CommercialLineupCasePo.case_id.in_(case_ids))
                .group_by(CommercialLineupCasePo.case_id)
            )
        ).all():
            counts[int(cid)] = int(n)

    links: list[dict[str, Any]] = []
    for link, case, po in rows:
        cid = int(case.id)
        protection = evaluate_case_bulk_protection(
            case_id=cid,
            commercial_status=case.commercial_status,
            po_link_count=counts.get(cid, 0),
        )
        links.append(
            {
                "link_id": int(link.id),
                "item_key": f"{cid}:{int(link.purchase_order_id)}",
                "case_id": cid,
                "case_period_label": case.period_label,
                "commercial_status": case.commercial_status,
                "purchase_order_id": int(link.purchase_order_id),
                "po_number": po.po_number_raw,
                "po_number_norm": po.po_number_norm,
                "notes": link.notes,
                "carried_under_d032": _carried_under_d032(link.notes),
                "row_class": "active",
                "po_link_count": counts.get(cid, 0),
                "bulk_protection": protection.as_dict(),
            }
        )

    return {"links": links, "total": len(links), "data_unavailable": False}


async def unlink_case_po_links(
    db: AsyncSession,
    *,
    items: list[dict[str, Any]],
    reason: str,
    allow_protected: bool = False,
    user: dict | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    """Delete active case↔PO link rows; audit each removal in the same transaction.

    Bulk callers must leave ``allow_protected=False``. Mid-batch failure rolls back all.
    """
    if not items:
        raise ValueError("items required")
    reason_s = (reason or "").strip()
    if not reason_s:
        raise ValueError("reason required")

    results: list[dict[str, Any]] = []
    for raw in items:
        case_id = int(raw["case_id"])
        purchase_order_id = int(raw["purchase_order_id"])
        item_allow = bool(raw.get("allow_protected")) or bool(allow_protected)

        link = (
            await db.execute(
                select(CommercialLineupCasePo).where(
                    CommercialLineupCasePo.case_id == case_id,
                    CommercialLineupCasePo.purchase_order_id == purchase_order_id,
                )
            )
        ).scalars().first()
        if link is None:
            raise CasePoLinkNotFoundError(case_id, purchase_order_id)

        case = await db.get(CommercialLineupCase, case_id)
        if case is None:
            raise CasePoLinkNotFoundError(case_id, purchase_order_id)

        if (case.commercial_status or "").strip() == "superseded":
            raise HistoricalCasePoLinkError(case_id, purchase_order_id, int(link.id))

        before_count = int(
            (
                await db.execute(
                    select(func.count(CommercialLineupCasePo.id)).where(
                        CommercialLineupCasePo.case_id == case_id
                    )
                )
            ).scalar_one()
            or 0
        )
        protection = evaluate_case_bulk_protection(
            case_id=case_id,
            commercial_status=case.commercial_status,
            po_link_count=before_count,
        )
        if protection.requires_allow_protected and not item_allow:
            raise CaseProtectedError(case_id, protection)

        po = await db.get(PurchaseOrder, purchase_order_id)
        po_number = po.po_number_raw if po is not None else None
        po_norm = po.po_number_norm if po is not None else None
        carried = _carried_under_d032(link.notes)
        link_id = int(link.id)
        before_status = case.commercial_status

        await db.execute(
            delete(CommercialLineupCasePo).where(CommercialLineupCasePo.id == link_id)
        )
        await db.flush()

        after_count = int(
            (
                await db.execute(
                    select(func.count(CommercialLineupCasePo.id)).where(
                        CommercialLineupCasePo.case_id == case_id
                    )
                )
            ).scalar_one()
            or 0
        )
        after_status = commercial_status_after_po_unlink(
            before_status or "", remaining_po_count=after_count
        )
        if after_status != before_status:
            case.commercial_status = after_status

        await record_steward_audit(
            db,
            user,
            action="lineup_case_po_unlink",
            importer="commercial_planner",
            entity_type="case_po_link",
            entity_token=f"{case_id}:{purchase_order_id}",
            target_dim="purchase_order",
            target_id=purchase_order_id,
            payload={
                "case_id": case_id,
                "purchase_order_id": purchase_order_id,
                "po_number": po_number,
                "po_number_norm": po_norm,
                "link_id": link_id,
                "reason": reason_s,
                "carried_under_d032": carried,
                "before_status": before_status,
                "after_status": after_status,
                "before_po_count": before_count,
                "after_po_count": after_count,
                "allow_protected": item_allow,
            },
            commit=False,
        )

        results.append(
            {
                "case_id": case_id,
                "purchase_order_id": purchase_order_id,
                "link_id": link_id,
                "po_number": po_number,
                "carried_under_d032": carried,
                "before_status": before_status,
                "after_status": after_status,
                "before_po_count": before_count,
                "after_po_count": after_count,
            }
        )

    if commit:
        await db.commit()
    else:
        await db.flush()

    return {
        "unlinked_count": len(results),
        "results": results,
        "reason": reason_s,
    }
