"""PO row consolidation when merging distributors (``UNIQUE(po_number_norm, distributor_id)``).

Ported from ``shipment_null_distributor_sibling_po_merge.execute_null_distributor_sibling_po_merge``
inner loop — same FK-child repoint tables, zero-ref guard, and all-or-nothing semantics.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.purchase_order import PurchaseOrder
from app.services.imports.shipment_null_distributor_po_merge import _repoint_case_po_links
from app.services.imports.shipment_null_distributor_sibling_po_merge import (
    PO_FK_TABLES,
    SiblingPoMergeAbortError,
    _assert_zero_loser_refs,
    _repoint_dismiss_links,
    _repoint_observation_po_links_strict,
    _require_repoint_rowcount,
    _strict_loser_ref_counts,
)


class DistributorPoConsolidationAbortError(RuntimeError):
    def __init__(self, message: str, *, loser_po_id: int, table: str | None = None, remaining: int = 0):
        self.loser_po_id = int(loser_po_id)
        self.table = table
        self.remaining = int(remaining)
        super().__init__(message)


def _survivor_po_by_norm(db: Session, keeper_distributor_id: int) -> dict[str, int]:
    rows = db.execute(
        select(PurchaseOrder.id, PurchaseOrder.po_number_norm).where(
            PurchaseOrder.distributor_id == int(keeper_distributor_id)
        )
    ).all()
    return {str(norm): int(po_id) for po_id, norm in rows}


def plan_distributor_owned_po_actions(
    db: Session,
    *,
    keeper_distributor_id: int,
    loser_distributor_id: int,
) -> list[dict[str, Any]]:
    """Preview PO actions for one loser distributor vs survivor."""
    kid, lid = int(keeper_distributor_id), int(loser_distributor_id)
    norm_to_keeper = _survivor_po_by_norm(db, kid)
    loser_pos = list(
        db.scalars(select(PurchaseOrder).where(PurchaseOrder.distributor_id == lid).order_by(PurchaseOrder.id)).all()
    )
    plans: list[dict[str, Any]] = []
    for po in loser_pos:
        norm = str(po.po_number_norm)
        keeper_po_id = norm_to_keeper.get(norm)
        if keeper_po_id is not None:
            plans.append(
                {
                    "loser_po_id": int(po.id),
                    "po_number_norm": norm,
                    "action": "consolidate_into_po",
                    "keeper_po_id": int(keeper_po_id),
                    "fk_child_counts": {
                        f"{table}.{column}": _strict_loser_ref_counts(db, int(po.id)).get(table, 0)
                        for table, column in PO_FK_TABLES
                    },
                }
            )
        else:
            plans.append(
                {
                    "loser_po_id": int(po.id),
                    "po_number_norm": norm,
                    "action": "repoint_distributor_id",
                    "keeper_distributor_id": kid,
                }
            )
    return plans


def execute_purchase_order_row_consolidation(
    db: Session,
    *,
    keeper_po_id: int,
    loser_po_id: int,
) -> dict[str, int]:
    """Repoint FK children from loser PO → keeper PO; delete loser PO (sibling-merge pattern)."""
    keeper = int(keeper_po_id)
    lid = int(loser_po_id)
    stats = {
        "losers_deleted": 0,
        "evidence_lines_updated": 0,
        "facts_updated": 0,
        "observations_updated": 0,
        "case_links_updated": 0,
        "case_links_deduped": 0,
        "dismiss_rows_updated": 0,
    }
    try:
        before = _strict_loser_ref_counts(db, lid)

        from app.models.facts import FactInboundShipment
        from app.models.shipment_evidence import ShipmentEvidenceLine

        r = db.execute(
            update(ShipmentEvidenceLine)
            .where(ShipmentEvidenceLine.purchase_order_id == lid)
            .values(purchase_order_id=keeper)
        )
        ev_updated = int(r.rowcount or 0)
        _require_repoint_rowcount(
            expected=before["shipment_evidence_line"],
            actual=ev_updated,
            table="shipment_evidence_line",
            loser_id=lid,
        )
        stats["evidence_lines_updated"] = ev_updated

        r = db.execute(
            update(FactInboundShipment)
            .where(FactInboundShipment.purchase_order_id == lid)
            .values(purchase_order_id=keeper)
        )
        fact_updated = int(r.rowcount or 0)
        _require_repoint_rowcount(
            expected=before["fact_inbound_shipment"],
            actual=fact_updated,
            table="fact_inbound_shipment",
            loser_id=lid,
        )
        stats["facts_updated"] = fact_updated

        obs_updated = _repoint_observation_po_links_strict(db, keeper, lid)
        _require_repoint_rowcount(
            expected=before["shipment_evidence_observation"],
            actual=obs_updated,
            table="shipment_evidence_observation",
            loser_id=lid,
        )
        stats["observations_updated"] = obs_updated

        cl = _repoint_case_po_links(db, keeper, lid)
        case_handled = int(cl["updated"]) + int(cl["deleted_dup"])
        _require_repoint_rowcount(
            expected=before["commercial_lineup_case_po"],
            actual=case_handled,
            table="commercial_lineup_case_po",
            loser_id=lid,
        )
        stats["case_links_updated"] = cl["updated"]
        stats["case_links_deduped"] = cl["deleted_dup"]

        dismiss_updated = _repoint_dismiss_links(db, keeper, lid)
        _require_repoint_rowcount(
            expected=before["commercial_lineup_po_auto_link_dismiss"],
            actual=dismiss_updated,
            table="commercial_lineup_po_auto_link_dismiss",
            loser_id=lid,
        )
        stats["dismiss_rows_updated"] = dismiss_updated

        db.flush()
        _assert_zero_loser_refs(db, lid)
        db.execute(delete(PurchaseOrder).where(PurchaseOrder.id == lid))
        stats["losers_deleted"] = 1
        db.flush()
    except SiblingPoMergeAbortError as exc:
        raise DistributorPoConsolidationAbortError(
            str(exc),
            loser_po_id=lid,
            table=exc.table,
            remaining=exc.remaining,
        ) from exc
    return stats


def execute_distributor_owned_po_actions(
    db: Session,
    *,
    keeper_distributor_id: int,
    loser_distributor_id: int,
    po_plans: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run PO consolidate + distributor_id repoint for one loser distributor."""
    plans = po_plans or plan_distributor_owned_po_actions(
        db, keeper_distributor_id=keeper_distributor_id, loser_distributor_id=loser_distributor_id
    )
    stats: dict[str, Any] = {"po_consolidations": [], "po_distributor_repoints": 0}
    kid = int(keeper_distributor_id)
    for plan in plans:
        action = str(plan.get("action") or "")
        if action == "consolidate_into_po":
            cstats = execute_purchase_order_row_consolidation(
                db,
                keeper_po_id=int(plan["keeper_po_id"]),
                loser_po_id=int(plan["loser_po_id"]),
            )
            stats["po_consolidations"].append({"loser_po_id": int(plan["loser_po_id"]), **cstats})
        elif action == "repoint_distributor_id":
            r = db.execute(
                update(PurchaseOrder)
                .where(PurchaseOrder.id == int(plan["loser_po_id"]))
                .values(distributor_id=kid)
            )
            stats["po_distributor_repoints"] += int(r.rowcount or 0)
        else:
            raise DistributorPoConsolidationAbortError(
                f"unknown PO plan action {action!r}",
                loser_po_id=int(plan.get("loser_po_id") or 0),
            )
    db.flush()
    return stats
