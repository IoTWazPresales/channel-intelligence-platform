"""Observed purchase-order suggestions for lineup case PO confirmation."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupCasePo, CommercialLineupLine
from app.models.dimensions import DimDistributor
from app.models.purchase_order import PurchaseOrder
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.commercial_planner.lineup_case_po_confirm import (
    CaseNotFoundError,
    _infer_case_distributor_id,
)


async def _case_product_ids(db: AsyncSession, case_id: int) -> list[int]:
    rows = (
        await db.execute(
            select(CommercialLineupLine.product_id)
            .where(
                CommercialLineupLine.case_id == case_id,
                CommercialLineupLine.product_id.isnot(None),
            )
            .distinct()
        )
    ).scalars().all()
    return sorted({int(pid) for pid in rows if pid is not None})


async def _case_line_distributor_ids(db: AsyncSession, case_id: int) -> list[int]:
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
    return sorted({int(did) for did in rows if did is not None})


async def _linked_po_ids(db: AsyncSession, case_id: int) -> set[int]:
    rows = (
        await db.execute(
            select(CommercialLineupCasePo.purchase_order_id).where(
                CommercialLineupCasePo.case_id == case_id
            )
        )
    ).scalars().all()
    return {int(r) for r in rows if r is not None}


async def suggest_pos_for_case(db: AsyncSession, case_id: int) -> dict[str, Any]:
    """Return observed POs ranked by product overlap with this case's resolved lineup lines."""
    case = await db.get(CommercialLineupCase, case_id)
    if case is None:
        raise CaseNotFoundError(str(case_id))

    product_ids = await _case_product_ids(db, case_id)
    case_distributor_id = await _infer_case_distributor_id(db, case_id)
    line_distributor_ids = await _case_line_distributor_ids(db, case_id)
    linked_ids = await _linked_po_ids(db, case_id)

    if not product_ids:
        return {
            "case_id": case_id,
            "case_distributor_id": case_distributor_id,
            "suggestions": [],
        }

    stmt = (
        select(
            PurchaseOrder.id,
            PurchaseOrder.po_number_raw,
            PurchaseOrder.po_number_norm,
            PurchaseOrder.distributor_id,
            PurchaseOrder.status,
            DimDistributor.code.label("distributor_code"),
            DimDistributor.name.label("distributor_name"),
            func.count(func.distinct(ShipmentEvidenceLine.product_id)).label("matched_product_count"),
            func.coalesce(func.sum(ShipmentEvidenceLine.quantity), 0).label("total_shipped_units"),
        )
        .join(
            ShipmentEvidenceLine,
            ShipmentEvidenceLine.purchase_order_id == PurchaseOrder.id,
        )
        .outerjoin(DimDistributor, DimDistributor.id == PurchaseOrder.distributor_id)
        .where(
            ShipmentEvidenceLine.purchase_order_id.isnot(None),
            ShipmentEvidenceLine.product_id.in_(product_ids),
        )
        .group_by(
            PurchaseOrder.id,
            PurchaseOrder.po_number_raw,
            PurchaseOrder.po_number_norm,
            PurchaseOrder.distributor_id,
            PurchaseOrder.status,
            DimDistributor.code,
            DimDistributor.name,
        )
    )

    if case_distributor_id is not None:
        stmt = stmt.where(
            or_(
                PurchaseOrder.distributor_id.is_(None),
                PurchaseOrder.distributor_id == case_distributor_id,
            )
        )
    elif line_distributor_ids:
        stmt = stmt.where(
            or_(
                PurchaseOrder.distributor_id.is_(None),
                PurchaseOrder.distributor_id.in_(line_distributor_ids),
            )
        )

    stmt = stmt.order_by(
        func.count(func.distinct(ShipmentEvidenceLine.product_id)).desc(),
        PurchaseOrder.po_number_norm.asc(),
    )

    rows = (await db.execute(stmt)).all()
    suggestions: list[dict[str, Any]] = []
    for (
        po_id,
        po_raw,
        po_norm,
        dist_id,
        status,
        dist_code,
        dist_name,
        matched_count,
        shipped_units,
    ) in rows:
        if case_distributor_id is not None and dist_id is not None and int(dist_id) != case_distributor_id:
            continue
        if (
            case_distributor_id is None
            and line_distributor_ids
            and dist_id is not None
            and int(dist_id) not in line_distributor_ids
        ):
            continue
        suggestions.append(
            {
                "purchase_order_id": int(po_id),
                "po_number": po_raw,
                "po_number_norm": po_norm,
                "distributor_id": int(dist_id) if dist_id is not None else None,
                "distributor_code": dist_code,
                "distributor_name": dist_name,
                "matched_product_count": int(matched_count or 0),
                "total_shipped_units": float(shipped_units or 0),
                "already_linked": int(po_id) in linked_ids,
                "status": status,
            }
        )

    return {
        "case_id": case_id,
        "case_distributor_id": case_distributor_id,
        "suggestions": suggestions,
    }


async def suggest_distributors_for_case(db: AsyncSession, case_id: int) -> dict[str, Any]:
    """Suggest distributor(s) for a case from shipment-evidence product corroboration.

    Every suggestion is an existing ``dim_distributor`` (sourced via ``purchase_order.distributor_id``),
    so an assignment always links to a real master record. Ranked by matched-product count then
    shipped units. ``converged`` is true only when the evidence points to exactly one distinct
    distributor (mirrors the DSI cross-distributor corroboration rule — multiple distributors stay
    ambiguous rather than guessing). Read-only.
    """
    case = await db.get(CommercialLineupCase, case_id)
    if case is None:
        raise CaseNotFoundError(str(case_id))

    product_ids = await _case_product_ids(db, case_id)
    already_assigned = await _case_line_distributor_ids(db, case_id)

    if not product_ids:
        return {
            "case_id": case_id,
            "converged": False,
            "converged_distributor_id": None,
            "distinct_count": 0,
            "suggested_distributors": [],
            "already_assigned_distributor_ids": already_assigned,
        }

    stmt = (
        select(
            PurchaseOrder.distributor_id,
            DimDistributor.code.label("distributor_code"),
            DimDistributor.name.label("distributor_name"),
            func.count(func.distinct(ShipmentEvidenceLine.product_id)).label("matched_product_count"),
            func.coalesce(func.sum(ShipmentEvidenceLine.quantity), 0).label("total_shipped_units"),
            func.count(func.distinct(PurchaseOrder.id)).label("po_count"),
        )
        # INNER join on DimDistributor: only real master records can be suggested/linked.
        .join(ShipmentEvidenceLine, ShipmentEvidenceLine.purchase_order_id == PurchaseOrder.id)
        .join(DimDistributor, DimDistributor.id == PurchaseOrder.distributor_id)
        .where(
            ShipmentEvidenceLine.purchase_order_id.isnot(None),
            ShipmentEvidenceLine.product_id.in_(product_ids),
            PurchaseOrder.distributor_id.isnot(None),
        )
        .group_by(
            PurchaseOrder.distributor_id,
            DimDistributor.code,
            DimDistributor.name,
        )
        .order_by(
            func.count(func.distinct(ShipmentEvidenceLine.product_id)).desc(),
            func.coalesce(func.sum(ShipmentEvidenceLine.quantity), 0).desc(),
        )
    )

    rows = (await db.execute(stmt)).all()
    suggested: list[dict[str, Any]] = []
    for dist_id, dist_code, dist_name, matched_count, shipped_units, po_count in rows:
        suggested.append(
            {
                "distributor_id": int(dist_id),
                "distributor_code": dist_code,
                "distributor_name": dist_name,
                "matched_product_count": int(matched_count or 0),
                "total_shipped_units": float(shipped_units or 0),
                "po_count": int(po_count or 0),
                "already_assigned": int(dist_id) in set(already_assigned),
            }
        )

    distinct_count = len(suggested)
    converged = distinct_count == 1
    return {
        "case_id": case_id,
        "converged": converged,
        "converged_distributor_id": suggested[0]["distributor_id"] if converged else None,
        "distinct_count": distinct_count,
        "suggested_distributors": suggested,
        "already_assigned_distributor_ids": already_assigned,
    }
