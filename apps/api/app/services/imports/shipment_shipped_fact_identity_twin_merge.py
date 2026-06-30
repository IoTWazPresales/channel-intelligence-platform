"""Reconcile shipped ``fact_inbound_shipment`` twins from invoice_line source_key drift.

Legacy imports (invoice_line null) produced shorter ``source_key`` values than populated imports.
Facts upsert on ``fact_upsert_key`` (OU|delivery|item) going forward; this script collapses
historical legacy twins where safe (1:1 qty match). Split and non-reconciling groups are skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.facts import FactInboundShipment
from app.models.purchase_order import PurchaseOrder
from app.services.imports.shipment_evidence_line_identity import (
    is_legacy_shipped_source_key,
    shipped_source_key_has_invoice_segment,
    stable_shipped_fact_upsert_key_from_fields,
)

TwinBucket = Literal["clean", "split", "non_reconciling"]


class ShippedFactTwinMergeAbortError(RuntimeError):
    def __init__(self, message: str, *, loser_id: int):
        self.loser_id = int(loser_id)
        super().__init__(message)


@dataclass(frozen=True)
class ShippedFactTwinGroup:
    fact_upsert_key: str
    purchase_order_id: int | None
    resolved_customer_id: int | None
    delivery_no: str | None
    item_code: str | None
    bucket: TwinBucket
    keeper_id: int | None
    loser_ids: tuple[int, ...]
    legacy_qty: float
    populated_qty: float
    populated_sum_qty: float
    reason: str = ""


@dataclass
class ShippedFactTwinSkip:
    fact_upsert_key: str
    bucket: TwinBucket
    reason: str
    fact_ids: tuple[int, ...] = ()
    legacy_qty: float = 0.0
    populated_sum_qty: float = 0.0


def _qty(f: FactInboundShipment) -> float:
    return float(f.quantity or 0)


def _fact_stable_key(f: FactInboundShipment) -> str | None:
    if (f.line_state or "").strip().lower() != "shipped":
        return None
    return stable_shipped_fact_upsert_key_from_fields(
        operating_unit=f.operating_unit,
        delivery_no=f.delivery_no,
        item_code=f.item_code,
    )


def _is_legacy_shipped_fact(f: FactInboundShipment) -> bool:
    if (f.line_state or "").strip().lower() != "shipped":
        return False
    if is_legacy_shipped_source_key(f.source_key):
        return True
    if f.invoice_line is None and not shipped_source_key_has_invoice_segment(f.source_key):
        return True
    return False


def _is_populated_shipped_fact(f: FactInboundShipment) -> bool:
    if (f.line_state or "").strip().lower() != "shipped":
        return False
    if shipped_source_key_has_invoice_segment(f.source_key):
        return True
    if f.invoice_line is not None and str(f.invoice_line).strip():
        return True
    return False


def _pick_keeper(populated: list[FactInboundShipment]) -> FactInboundShipment:
    return sorted(
        populated,
        key=lambda f: (
            -(int(f.import_job_id) if f.import_job_id is not None else 0),
            -int(f.id),
        ),
    )[0]


def _classify_group(
    stable_key: str,
    facts: list[FactInboundShipment],
) -> ShippedFactTwinGroup | ShippedFactTwinSkip:
    legacy = [f for f in facts if _is_legacy_shipped_fact(f)]
    populated = [f for f in facts if _is_populated_shipped_fact(f)]
    other = [f for f in facts if f not in legacy and f not in populated]

    rep = facts[0]
    po_id = int(rep.purchase_order_id) if rep.purchase_order_id is not None else None
    cust = int(rep.resolved_customer_id) if rep.resolved_customer_id is not None else None
    legacy_qty = sum(_qty(f) for f in legacy)
    populated_sum = sum(_qty(f) for f in populated)

    if not legacy or not populated:
        return ShippedFactTwinSkip(
            fact_upsert_key=stable_key,
            bucket="non_reconciling",
            reason="missing_legacy_or_populated_twin",
            fact_ids=tuple(int(f.id) for f in facts),
            legacy_qty=legacy_qty,
            populated_sum_qty=populated_sum,
        )

    if other:
        return ShippedFactTwinSkip(
            fact_upsert_key=stable_key,
            bucket="non_reconciling",
            reason="unclassified_fact_rows_in_group",
            fact_ids=tuple(int(f.id) for f in facts),
            legacy_qty=legacy_qty,
            populated_sum_qty=populated_sum,
        )

    if len(legacy) == 1 and len(populated) == 1:
        lq, pq = _qty(legacy[0]), _qty(populated[0])
        if abs(lq - pq) < 1e-6:
            keeper = _pick_keeper(populated)
            return ShippedFactTwinGroup(
                fact_upsert_key=stable_key,
                purchase_order_id=po_id,
                resolved_customer_id=cust,
                delivery_no=rep.delivery_no,
                item_code=rep.item_code,
                bucket="clean",
                keeper_id=int(keeper.id),
                loser_ids=(int(legacy[0].id),),
                legacy_qty=lq,
                populated_qty=pq,
                populated_sum_qty=pq,
                reason="legacy_1_1_populated_qty_match",
            )
        return ShippedFactTwinSkip(
            fact_upsert_key=stable_key,
            bucket="non_reconciling",
            reason="legacy_populated_qty_mismatch",
            fact_ids=tuple(int(f.id) for f in facts),
            legacy_qty=legacy_qty,
            populated_sum_qty=populated_sum,
        )

    if len(legacy) == 1 and len(populated) >= 2:
        return ShippedFactTwinSkip(
            fact_upsert_key=stable_key,
            bucket="split",
            reason="legacy_vs_multiple_populated_invoice_lines",
            fact_ids=tuple(int(f.id) for f in facts),
            legacy_qty=legacy_qty,
            populated_sum_qty=populated_sum,
        )

    return ShippedFactTwinSkip(
        fact_upsert_key=stable_key,
        bucket="non_reconciling",
        reason="multiple_legacy_or_unexpected_shape",
        fact_ids=tuple(int(f.id) for f in facts),
        legacy_qty=legacy_qty,
        populated_sum_qty=populated_sum,
    )


def plan_shipped_fact_identity_twin_merges(db: Session) -> tuple[list[ShippedFactTwinGroup], list[ShippedFactTwinSkip]]:
    """Find shipped fact groups sharing ``fact_upsert_key`` with legacy+populated twins."""
    facts = list(
        db.scalars(
            select(FactInboundShipment).where(FactInboundShipment.line_state == "shipped")
        ).all()
    )

    groups: dict[tuple[str, int | None, int | None], list[FactInboundShipment]] = {}
    for f in facts:
        stable = f.fact_upsert_key or _fact_stable_key(f)
        if not stable:
            continue
        po = int(f.purchase_order_id) if f.purchase_order_id is not None else None
        cust = int(f.resolved_customer_id) if f.resolved_customer_id is not None else None
        groups.setdefault((stable, po, cust), []).append(f)

    plans: list[ShippedFactTwinGroup] = []
    skipped: list[ShippedFactTwinSkip] = []

    for (stable, _po, _cust), members in sorted(groups.items(), key=lambda x: x[0][0]):
        if len(members) < 2:
            continue
        legacy = [f for f in members if _is_legacy_shipped_fact(f)]
        populated = [f for f in members if _is_populated_shipped_fact(f)]
        if not legacy or not populated:
            continue
        outcome = _classify_group(stable, members)
        if isinstance(outcome, ShippedFactTwinGroup):
            if outcome.bucket == "clean":
                plans.append(outcome)
            else:
                skipped.append(
                    ShippedFactTwinSkip(
                        fact_upsert_key=outcome.fact_upsert_key,
                        bucket=outcome.bucket,
                        reason=outcome.reason,
                        fact_ids=tuple(int(f.id) for f in members),
                        legacy_qty=outcome.legacy_qty,
                        populated_sum_qty=outcome.populated_sum_qty,
                    )
                )
        else:
            skipped.append(outcome)

    return plans, skipped


def _assert_fact_deletable(db: Session, fact_id: int) -> None:
    """Facts have no inbound FKs; guard only that the row still exists."""
    if db.get(FactInboundShipment, int(fact_id)) is None:
        raise ShippedFactTwinMergeAbortError(
            f"fact_inbound_shipment id={fact_id} missing before delete",
            loser_id=int(fact_id),
        )


def execute_shipped_fact_identity_twin_merge(db: Session, group: ShippedFactTwinGroup) -> dict[str, int]:
    if group.bucket != "clean" or group.keeper_id is None:
        raise ValueError("execute only for clean groups")
    deleted = 0
    for loser_id in group.loser_ids:
        _assert_fact_deletable(db, loser_id)
        r = db.execute(delete(FactInboundShipment).where(FactInboundShipment.id == int(loser_id)))
        if int(r.rowcount or 0) != 1:
            raise ShippedFactTwinMergeAbortError(
                f"expected to delete 1 fact row id={loser_id}, got {r.rowcount}",
                loser_id=int(loser_id),
            )
        deleted += 1
    return {"facts_deleted": deleted}


def shipped_fact_twin_summary_stats(db: Session) -> dict[str, Any]:
    shipped = (
        db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(FactInboundShipment.quantity), 0),
                func.count(func.distinct(FactInboundShipment.purchase_order_id)),
            ).where(FactInboundShipment.line_state == "shipped")
        )
    ).one()
    return {
        "shipped_fact_rows": int(shipped[0] or 0),
        "shipped_fact_units": float(shipped[1] or 0),
        "shipped_fact_po_count": int(shipped[2] or 0),
    }


def shipped_fact_twin_plan_to_dict(g: ShippedFactTwinGroup) -> dict[str, Any]:
    return {
        "fact_upsert_key": g.fact_upsert_key,
        "purchase_order_id": g.purchase_order_id,
        "resolved_customer_id": g.resolved_customer_id,
        "delivery_no": g.delivery_no,
        "item_code": g.item_code,
        "bucket": g.bucket,
        "keeper_id": g.keeper_id,
        "loser_ids": list(g.loser_ids),
        "legacy_qty": g.legacy_qty,
        "populated_qty": g.populated_qty,
        "populated_sum_qty": g.populated_sum_qty,
        "reason": g.reason,
    }


def shipped_fact_twin_skip_to_dict(s: ShippedFactTwinSkip) -> dict[str, Any]:
    return {
        "fact_upsert_key": s.fact_upsert_key,
        "bucket": s.bucket,
        "reason": s.reason,
        "fact_ids": list(s.fact_ids),
        "legacy_qty": s.legacy_qty,
        "populated_sum_qty": s.populated_sum_qty,
    }


def amazon_po_shipped_stats(db: Session, po_norm: str, customer_id: int) -> dict[str, Any]:
    po_id = db.scalar(select(PurchaseOrder.id).where(PurchaseOrder.po_number_norm == po_norm))
    if po_id is None:
        return {"po_number_norm": po_norm, "shipped_rows": 0, "shipped_units": 0.0}
    row = db.execute(
        select(func.count(), func.coalesce(func.sum(FactInboundShipment.quantity), 0)).where(
            FactInboundShipment.purchase_order_id == int(po_id),
            FactInboundShipment.resolved_customer_id == int(customer_id),
            FactInboundShipment.line_state == "shipped",
        )
    ).one()
    return {
        "po_number_norm": po_norm,
        "purchase_order_id": int(po_id),
        "customer_id": int(customer_id),
        "shipped_rows": int(row[0] or 0),
        "shipped_units": float(row[1] or 0),
    }


def twin_blast_radius(db: Session, plans: list[ShippedFactTwinGroup], skipped: list[ShippedFactTwinSkip]) -> dict[str, Any]:
    loser_ids = {lid for g in plans for lid in g.loser_ids}
    stale_units = sum(g.legacy_qty for g in plans)
    deliveries = {g.delivery_no for g in plans if g.delivery_no}
    po_ids = {g.purchase_order_id for g in plans if g.purchase_order_id is not None}
    return {
        "clean_groups": len(plans),
        "clean_loser_facts": len(loser_ids),
        "clean_stale_units": round(stale_units, 4),
        "clean_distinct_deliveries": len(deliveries),
        "clean_distinct_pos": len(po_ids),
        "split_groups": sum(1 for s in skipped if s.bucket == "split"),
        "non_reconciling_groups": sum(1 for s in skipped if s.bucket == "non_reconciling"),
    }
