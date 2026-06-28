"""Confirm a lineup case with one or more purchase orders (Session C Unit 2d).

Flow (idempotent, amendment-aware):
  normalize_po_number -> lookup/upsert ``purchase_order`` (distributor inferred from the case's
  lineup lines) -> insert ``commercial_lineup_case_po`` link when missing -> case -> ``po_issued``.

Re-confirming the same PO is a no-op (the unique (case_id, purchase_order_id) link already exists);
confirming an additional PO appends a new link (never replaces existing links). POs are shared
shipment evidence, so an existing PO row is reused rather than duplicated.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import (
    COMMERCIAL_LINEUP_STATUSES,
    CommercialLineupCase,
    CommercialLineupCasePo,
    CommercialLineupLine,
)
from app.models.purchase_order import PurchaseOrder
from app.services.imports.shipment_po_normalization import normalize_po_number

# Direct PO confirm is allowed from any non-terminal-cancelled status (historical shortcut).
# Forward ladder (draft -> accepted) remains for plan-anchored workflows; confirm jumps to po_issued.
CONFIRM_BLOCKED_STATUSES: frozenset[str] = frozenset({"cancelled"})


def confirm_allowed_for_status(status: str) -> bool:
    return status in COMMERCIAL_LINEUP_STATUSES and status not in CONFIRM_BLOCKED_STATUSES


class CaseNotFoundError(Exception):
    pass


class CaseStatusNotConfirmableError(Exception):
    def __init__(self, status: str):
        self.status = status
        super().__init__(status)


async def _infer_case_distributor_id(db: AsyncSession, case_id: int) -> int | None:
    """A case's PO distributor = the single distinct distributor on its lineup lines, else None.

    Ambiguous (multiple distributors) or unknown -> None, so the PO is anchored distributor-agnostic
    rather than guessing. This matches the shipment materialize behaviour (PO may have null dist).
    """
    rows = (
        await db.execute(
            select(CommercialLineupLine.distributor_id)
            .where(
                CommercialLineupLine.case_id == case_id,
                CommercialLineupLine.distributor_id.isnot(None),
            )
            .distinct()
        )
    ).scalars().all()
    distinct_ids = [int(r) for r in rows if r is not None]
    return distinct_ids[0] if len(distinct_ids) == 1 else None


async def _lookup_or_create_po(
    db: AsyncSession, *, po_number_raw: str, po_number_norm: str, distributor_id: int | None
) -> tuple[PurchaseOrder, bool]:
    """Return (purchase_order, created). Reuses an existing PO on (norm, distributor) including NULL."""
    stmt = select(PurchaseOrder).where(PurchaseOrder.po_number_norm == po_number_norm)
    if distributor_id is None:
        stmt = stmt.where(PurchaseOrder.distributor_id.is_(None))
    else:
        stmt = stmt.where(PurchaseOrder.distributor_id == distributor_id)
    existing = (await db.execute(stmt)).scalars().first()
    if existing is not None:
        return existing, False
    po = PurchaseOrder(
        po_number_raw=po_number_raw,
        po_number_norm=po_number_norm,
        distributor_id=distributor_id,
        status="raised",
        source="lineup_declared",
    )
    db.add(po)
    await db.flush()
    return po, True


async def confirm_case_with_po(
    db: AsyncSession,
    case_id: int,
    *,
    po_numbers: list[str],
    notes: str | None = None,
) -> dict[str, Any]:
    """Confirm a lineup case with PO number(s); idempotent, amendment-aware. Sets status po_issued."""
    case = await db.get(CommercialLineupCase, case_id)
    if case is None:
        raise CaseNotFoundError(str(case_id))
    if not confirm_allowed_for_status(case.commercial_status):
        raise CaseStatusNotConfirmableError(case.commercial_status)

    # De-dup + drop blanks, preserving the first raw spelling seen for each normalized key.
    normalized: dict[str, str] = {}
    for raw in po_numbers:
        norm = normalize_po_number(raw)
        if norm and norm not in normalized:
            normalized[norm] = (raw or "").strip()
    if not normalized:
        raise ValueError("At least one non-empty PO number is required.")

    distributor_id = await _infer_case_distributor_id(db, case_id)

    linked: list[dict[str, Any]] = []
    for norm, raw in normalized.items():
        po, created = await _lookup_or_create_po(
            db, po_number_raw=raw or norm, po_number_norm=norm, distributor_id=distributor_id
        )
        existing_link = (
            await db.execute(
                select(CommercialLineupCasePo).where(
                    CommercialLineupCasePo.case_id == case_id,
                    CommercialLineupCasePo.purchase_order_id == po.id,
                )
            )
        ).scalars().first()
        newly_linked = existing_link is None
        if newly_linked:
            db.add(CommercialLineupCasePo(case_id=case_id, purchase_order_id=po.id, notes=notes))
        linked.append(
            {
                "purchase_order_id": int(po.id),
                "po_number_norm": norm,
                "po_number_raw": po.po_number_raw,
                "distributor_id": distributor_id,
                "newly_linked": newly_linked,
                "newly_created_po": created,
            }
        )

    case.commercial_status = "po_issued"
    await db.commit()

    total = (
        await db.execute(
            select(func.count(CommercialLineupCasePo.id)).where(
                CommercialLineupCasePo.case_id == case_id
            )
        )
    ).scalar_one()

    return {
        "case_id": case_id,
        "commercial_status": case.commercial_status,
        "iteration_number": int(case.iteration_number),
        "linked_pos": linked,
        "po_count": int(total),
        "newly_linked_count": sum(1 for x in linked if x["newly_linked"]),
    }


async def list_case_pos_bulk(
    db: AsyncSession, case_ids: list[int]
) -> dict[int, list[dict[str, Any]]]:
    """Linked POs grouped by case_id for a set of cases (avoids N+1 on the list endpoint)."""
    out: dict[int, list[dict[str, Any]]] = {cid: [] for cid in case_ids}
    if not case_ids:
        return out
    rows = (
        await db.execute(
            select(
                CommercialLineupCasePo.case_id,
                PurchaseOrder.id,
                PurchaseOrder.po_number_raw,
                PurchaseOrder.po_number_norm,
                PurchaseOrder.distributor_id,
                PurchaseOrder.status,
            )
            .join(
                CommercialLineupCasePo,
                CommercialLineupCasePo.purchase_order_id == PurchaseOrder.id,
            )
            .where(CommercialLineupCasePo.case_id.in_(case_ids))
            .order_by(CommercialLineupCasePo.id.asc())
        )
    ).all()
    for case_id, po_id, raw, norm, dist_id, status in rows:
        out.setdefault(int(case_id), []).append(
            {
                "purchase_order_id": int(po_id),
                "po_number_raw": raw,
                "po_number_norm": norm,
                "distributor_id": dist_id,
                "status": status,
            }
        )
    return out


async def list_case_pos(db: AsyncSession, case_id: int) -> list[dict[str, Any]]:
    """Linked POs for a case (for the case payload / card)."""
    rows = (
        await db.execute(
            select(PurchaseOrder, CommercialLineupCasePo.created_at)
            .join(
                CommercialLineupCasePo,
                CommercialLineupCasePo.purchase_order_id == PurchaseOrder.id,
            )
            .where(CommercialLineupCasePo.case_id == case_id)
            .order_by(CommercialLineupCasePo.id.asc())
        )
    ).all()
    out: list[dict[str, Any]] = []
    for po, linked_at in rows:
        out.append(
            {
                "purchase_order_id": int(po.id),
                "po_number_raw": po.po_number_raw,
                "po_number_norm": po.po_number_norm,
                "distributor_id": po.distributor_id,
                "status": po.status,
                "linked_at": linked_at.isoformat() if linked_at else None,
            }
        )
    return out
