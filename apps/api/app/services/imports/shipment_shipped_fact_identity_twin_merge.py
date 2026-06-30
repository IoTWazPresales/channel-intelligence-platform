"""Collapse shipped ``fact_inbound_shipment`` rows sharing ``fact_upsert_key``.

Invoice lines are real separate system-generated lines and must be summed. Legacy rows
(jobs 32/40, ``invoice_line`` null) are incomplete under-counts; the latest import job's
invoice-line set is truth. Every key with >1 shipped row collapses to one survivor unless
multiple distinct ``purchase_order_id`` values would corrupt PO attribution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.models.facts import FactInboundShipment
from app.models.purchase_order import PurchaseOrder
from app.services.imports.shipment_evidence_line_identity import (
    stable_shipped_fact_upsert_key_from_fields,
)

CollapseBucket = Literal["clean", "multi_invoice", "multi_import"]


class ShippedFactCollapseAbortError(RuntimeError):
    """Raised when repoint or pre-delete checks fail — caller must roll back the transaction."""

    def __init__(self, message: str, *, loser_id: int, table: str | None = None, remaining: int = 0):
        self.loser_id = int(loser_id)
        self.table = table
        self.remaining = int(remaining)
        super().__init__(message)


@dataclass(frozen=True)
class ShippedFactCollapseGroup:
    fact_upsert_key: str
    purchase_order_id: int | None
    resolved_customer_id: int | None
    delivery_no: str | None
    item_code: str | None
    bucket: CollapseBucket
    max_import_job_id: int
    keeper_id: int
    loser_ids: tuple[int, ...]
    survivor_qty: float
    survivor_amount: float | None
    rows_before: int
    units_before: float
    reason: str = ""


@dataclass(frozen=True)
class ShippedFactCollapseSkip:
    fact_upsert_key: str
    reason: str
    purchase_order_ids: tuple[int | None, ...] = ()
    fact_ids: tuple[int, ...] = ()
    rows: int = 0
    units: float = 0.0


def _qty(f: FactInboundShipment) -> float:
    return float(f.quantity or 0)


def _amount(f: FactInboundShipment) -> float | None:
    if f.amount is None:
        return None
    return float(f.amount)


def _job_id(f: FactInboundShipment) -> int:
    return int(f.import_job_id) if f.import_job_id is not None else 0


def _fact_stable_key(f: FactInboundShipment) -> str | None:
    if (f.line_state or "").strip().lower() != "shipped":
        return None
    return f.fact_upsert_key or stable_shipped_fact_upsert_key_from_fields(
        operating_unit=f.operating_unit,
        delivery_no=f.delivery_no,
        item_code=f.item_code,
    )


def _is_legacy_shipped_fact(f: FactInboundShipment) -> bool:
    from app.services.imports.shipment_evidence_line_identity import (
        is_legacy_shipped_source_key,
        shipped_source_key_has_invoice_segment,
    )

    if (f.line_state or "").strip().lower() != "shipped":
        return False
    if is_legacy_shipped_source_key(f.source_key):
        return True
    if f.invoice_line is None and not shipped_source_key_has_invoice_segment(f.source_key):
        return True
    return False


def _po_attribution_skip_reason(facts: list[FactInboundShipment]) -> str | None:
    """Return skip reason when rows on one key would corrupt PO attribution."""
    non_null = {int(f.purchase_order_id) for f in facts if f.purchase_order_id is not None}
    null_count = sum(1 for f in facts if f.purchase_order_id is None)
    if len(non_null) > 1:
        return "multiple_distinct_purchase_order_ids"
    if non_null and null_count:
        return "mixed_null_and_non_null_purchase_order_id"
    return None


def _report_bucket(
    all_facts: list[FactInboundShipment],
    older_rows: list[FactInboundShipment],
    latest_rows: list[FactInboundShipment],
) -> CollapseBucket:
    if len(all_facts) == 2:
        return "clean"
    legacy = [f for f in all_facts if _is_legacy_shipped_fact(f)]
    if len(latest_rows) >= 2 and len(older_rows) >= 1:
        return "multi_invoice"
    if len(latest_rows) >= 2:
        return "multi_invoice"
    if len(legacy) >= 2 or len({f.import_job_id for f in older_rows}) >= 2:
        return "multi_import"
    if len({f.import_job_id for f in all_facts}) > 1:
        return "multi_import"
    if len(all_facts) == 2:
        return "clean"
    return "multi_import"


def _pick_keeper(latest_rows: list[FactInboundShipment]) -> FactInboundShipment:
    return sorted(latest_rows, key=lambda f: (-int(f.id),))[0]


def _build_collapse_group(
    stable_key: str,
    facts: list[FactInboundShipment],
) -> ShippedFactCollapseGroup | ShippedFactCollapseSkip:
    po_skip = _po_attribution_skip_reason(facts)
    if po_skip:
        po_ids = tuple(
            int(f.purchase_order_id) if f.purchase_order_id is not None else None for f in facts
        )
        return ShippedFactCollapseSkip(
            fact_upsert_key=stable_key,
            reason=po_skip,
            purchase_order_ids=po_ids,
            fact_ids=tuple(int(f.id) for f in facts),
            rows=len(facts),
            units=sum(_qty(f) for f in facts),
        )

    max_job = max(_job_id(f) for f in facts)
    latest_rows = [f for f in facts if _job_id(f) == max_job]
    older_rows = [f for f in facts if _job_id(f) != max_job]
    if not latest_rows:
        return ShippedFactCollapseSkip(
            fact_upsert_key=stable_key,
            reason="no_rows_for_max_import_job",
            fact_ids=tuple(int(f.id) for f in facts),
            rows=len(facts),
            units=sum(_qty(f) for f in facts),
        )

    keeper = _pick_keeper(latest_rows)
    survivor_qty = sum(_qty(f) for f in latest_rows)
    amounts = [_amount(f) for f in latest_rows if _amount(f) is not None]
    survivor_amount: float | None = sum(amounts) if amounts else None
    loser_ids = tuple(int(f.id) for f in facts if int(f.id) != int(keeper.id))

    rep = keeper
    po_id = int(rep.purchase_order_id) if rep.purchase_order_id is not None else None
    cust = int(rep.resolved_customer_id) if rep.resolved_customer_id is not None else None

    return ShippedFactCollapseGroup(
        fact_upsert_key=stable_key,
        purchase_order_id=po_id,
        resolved_customer_id=cust,
        delivery_no=rep.delivery_no,
        item_code=rep.item_code,
        bucket=_report_bucket(facts, older_rows, latest_rows),
        max_import_job_id=max_job,
        keeper_id=int(keeper.id),
        loser_ids=loser_ids,
        survivor_qty=survivor_qty,
        survivor_amount=survivor_amount,
        rows_before=len(facts),
        units_before=sum(_qty(f) for f in facts),
        reason="latest_job_invoice_lines_summed",
    )


def plan_shipped_fact_identity_twin_merges(
    db: Session,
) -> tuple[list[ShippedFactCollapseGroup], list[ShippedFactCollapseSkip]]:
    """Plan collapse for every shipped ``fact_upsert_key`` with more than one fact row."""
    facts = list(
        db.scalars(
            select(FactInboundShipment).where(FactInboundShipment.line_state == "shipped")
        ).all()
    )

    groups: dict[str, list[FactInboundShipment]] = {}
    for f in facts:
        stable = _fact_stable_key(f)
        if not stable:
            continue
        groups.setdefault(stable, []).append(f)

    plans: list[ShippedFactCollapseGroup] = []
    skipped: list[ShippedFactCollapseSkip] = []

    for stable, members in sorted(groups.items(), key=lambda x: x[0]):
        if len(members) < 2:
            continue
        outcome = _build_collapse_group(stable, members)
        if isinstance(outcome, ShippedFactCollapseGroup):
            plans.append(outcome)
        else:
            skipped.append(outcome)

    return plans, skipped


def _discover_fact_inbound_fk_columns(db: Session) -> tuple[tuple[str, str], ...]:
    """Enumerate FK columns referencing ``fact_inbound_shipment.id`` (empty if none)."""
    try:
        rows = db.execute(
            text(
                """
                SELECT c.relname AS table_name, a.attname AS column_name
                FROM pg_constraint con
                JOIN pg_class c ON c.oid = con.conrelid
                JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey)
                JOIN pg_class ref ON ref.oid = con.confrelid
                WHERE con.contype = 'f'
                  AND ref.relname = 'fact_inbound_shipment'
                  AND array_length(con.confkey, 1) = 1
                  AND (
                    SELECT attname FROM pg_attribute
                    WHERE attrelid = con.confrelid AND attnum = con.confkey[1]
                  ) = 'id'
                ORDER BY 1, 2
                """
            )
        ).all()
        return tuple((str(r[0]), str(r[1])) for r in rows)
    except ProgrammingError:
        return ()


def _count_fk_refs(db: Session, table: str, column: str, fact_id: int) -> int:
    return int(
        db.execute(
            text(f"SELECT count(*) FROM {table} WHERE {column} = :fid"),
            {"fid": int(fact_id)},
        ).scalar()
        or 0
    )


def _strict_loser_fact_ref_counts(db: Session, loser_id: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table, column in _discover_fact_inbound_fk_columns(db):
        counts[f"{table}.{column}"] = _count_fk_refs(db, table, column, int(loser_id))
    return counts


def _require_repoint_rowcount(
    *,
    expected: int,
    actual: int,
    table: str,
    loser_id: int,
) -> None:
    if expected > 0 and actual != expected:
        raise ShippedFactCollapseAbortError(
            f"repoint {table} for loser fact {loser_id}: expected {expected} row(s) updated, got {actual}",
            loser_id=int(loser_id),
            table=table,
            remaining=expected,
        )


def _repoint_fact_fk_refs_strict(db: Session, keeper_id: int, loser_id: int) -> dict[str, int]:
    """Repoint any FK rows from loser fact id to keeper; rowcount must match."""
    stats: dict[str, int] = {}
    for table, column in _discover_fact_inbound_fk_columns(db):
        key = f"{table}.{column}"
        before = _count_fk_refs(db, table, column, int(loser_id))
        if before == 0:
            stats[key] = 0
            continue
        r = db.execute(
            text(f"UPDATE {table} SET {column} = :keeper WHERE {column} = :loser"),
            {"keeper": int(keeper_id), "loser": int(loser_id)},
        )
        updated = int(r.rowcount or 0)
        _require_repoint_rowcount(
            expected=before,
            actual=updated,
            table=key,
            loser_id=int(loser_id),
        )
        stats[key] = updated
    return stats


def _assert_zero_loser_fact_refs(db: Session, loser_id: int) -> None:
    for table, remaining in _strict_loser_fact_ref_counts(db, int(loser_id)).items():
        if remaining > 0:
            raise ShippedFactCollapseAbortError(
                f"fact_inbound_shipment loser {loser_id} still referenced by {remaining} row(s) in {table}",
                loser_id=int(loser_id),
                table=table,
                remaining=remaining,
            )


def execute_shipped_fact_identity_twin_merge(db: Session, group: ShippedFactCollapseGroup) -> dict[str, int]:
    """Collapse one group: update keeper measures, repoint FKs, delete losers."""
    keeper_id = int(group.keeper_id)
    keeper = db.get(FactInboundShipment, keeper_id)
    if keeper is None:
        raise ShippedFactCollapseAbortError(
            f"keeper fact id={keeper_id} missing before collapse",
            loser_id=keeper_id,
        )

    values: dict[str, Any] = {"quantity": group.survivor_qty}
    if group.survivor_amount is not None:
        values["amount"] = group.survivor_amount
    db.execute(update(FactInboundShipment).where(FactInboundShipment.id == keeper_id).values(**values))

    deleted = 0
    repointed = 0
    for loser_id in group.loser_ids:
        lid = int(loser_id)
        if db.get(FactInboundShipment, lid) is None:
            raise ShippedFactCollapseAbortError(
                f"fact_inbound_shipment id={lid} missing before delete",
                loser_id=lid,
            )
        repoint_stats = _repoint_fact_fk_refs_strict(db, keeper_id, lid)
        repointed += sum(repoint_stats.values())
        db.flush()
        _assert_zero_loser_fact_refs(db, lid)
        r = db.execute(delete(FactInboundShipment).where(FactInboundShipment.id == lid))
        if int(r.rowcount or 0) != 1:
            raise ShippedFactCollapseAbortError(
                f"expected to delete 1 fact row id={lid}, got {r.rowcount}",
                loser_id=lid,
            )
        deleted += 1
    return {"facts_deleted": deleted, "fk_rows_repointed": repointed}


def execute_all_shipped_fact_collapses(db: Session, plans: list[ShippedFactCollapseGroup]) -> dict[str, int]:
    """Execute every collapse in the current transaction; abort rolls back the whole batch."""
    totals = {"groups": 0, "facts_deleted": 0, "fk_rows_repointed": 0}
    for group in plans:
        stats = execute_shipped_fact_identity_twin_merge(db, group)
        totals["groups"] += 1
        totals["facts_deleted"] += int(stats.get("facts_deleted", 0))
        totals["fk_rows_repointed"] += int(stats.get("fk_rows_repointed", 0))
    return totals


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
    dup_keys = db.scalar(
        select(func.count())
        .select_from(
            select(FactInboundShipment.fact_upsert_key)
            .where(
                FactInboundShipment.line_state == "shipped",
                FactInboundShipment.fact_upsert_key.isnot(None),
            )
            .group_by(FactInboundShipment.fact_upsert_key)
            .having(func.count() > 1)
            .subquery()
        )
    )
    return {
        "shipped_fact_rows": int(shipped[0] or 0),
        "shipped_fact_units": float(shipped[1] or 0),
        "shipped_fact_po_count": int(shipped[2] or 0),
        "duplicate_fact_upsert_key_groups": int(dup_keys or 0),
    }


def shipped_fact_twin_plan_to_dict(g: ShippedFactCollapseGroup) -> dict[str, Any]:
    return {
        "fact_upsert_key": g.fact_upsert_key,
        "purchase_order_id": g.purchase_order_id,
        "resolved_customer_id": g.resolved_customer_id,
        "delivery_no": g.delivery_no,
        "item_code": g.item_code,
        "bucket": g.bucket,
        "max_import_job_id": g.max_import_job_id,
        "keeper_id": g.keeper_id,
        "loser_ids": list(g.loser_ids),
        "survivor_qty": g.survivor_qty,
        "survivor_amount": g.survivor_amount,
        "rows_before": g.rows_before,
        "units_before": g.units_before,
        "reason": g.reason,
    }


def shipped_fact_twin_skip_to_dict(s: ShippedFactCollapseSkip) -> dict[str, Any]:
    return {
        "fact_upsert_key": s.fact_upsert_key,
        "reason": s.reason,
        "purchase_order_ids": list(s.purchase_order_ids),
        "fact_ids": list(s.fact_ids),
        "rows": s.rows,
        "units": s.units,
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


def twin_blast_radius(
    db: Session,
    plans: list[ShippedFactCollapseGroup],
    skipped: list[ShippedFactCollapseSkip],
) -> dict[str, Any]:
    loser_ids = {lid for g in plans for lid in g.loser_ids}
    rows_removed = sum(g.rows_before - 1 for g in plans)
    units_delta = sum(g.units_before - g.survivor_qty for g in plans)
    deliveries = {g.delivery_no for g in plans if g.delivery_no}
    po_ids = {g.purchase_order_id for g in plans if g.purchase_order_id is not None}
    bucket_rows: dict[str, int] = {"clean": 0, "multi_invoice": 0, "multi_import": 0}
    bucket_units: dict[str, float] = {"clean": 0.0, "multi_invoice": 0.0, "multi_import": 0.0}
    for g in plans:
        bucket_rows[g.bucket] += g.rows_before
        bucket_units[g.bucket] += g.units_before
    return {
        "collapse_groups": len(plans),
        "collapse_loser_facts": len(loser_ids),
        "collapse_rows_removed": rows_removed,
        "collapse_stale_units": round(units_delta, 4),
        "collapse_distinct_deliveries": len(deliveries),
        "collapse_distinct_pos": len(po_ids),
        "bucket_rows_before": bucket_rows,
        "bucket_units_before": {k: round(v, 4) for k, v in bucket_units.items()},
        "multi_po_skipped_groups": len(skipped),
    }


# Backward-compatible aliases for tests importing old names
ShippedFactTwinGroup = ShippedFactCollapseGroup
ShippedFactTwinSkip = ShippedFactCollapseSkip
TwinBucket = CollapseBucket


def _classify_group(stable_key: str, facts: list[FactInboundShipment]) -> ShippedFactCollapseGroup | ShippedFactCollapseSkip:
    """Backward-compatible entry for unit tests."""
    return _build_collapse_group(stable_key, facts)
