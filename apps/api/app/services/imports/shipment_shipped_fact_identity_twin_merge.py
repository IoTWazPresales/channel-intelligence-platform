"""Collapse shipped ``fact_inbound_shipment`` rows sharing ``fact_upsert_key``.

Shipped keys are PO-inclusive: ``ship:{OU|delivery|item|purchase_order_id}``. Invoice lines
on the same (delivery, item, PO) sum into one fact; different POs on one delivery stay separate.
Legacy rows (jobs 32/40, ``invoice_line`` null) are incomplete under-counts; the latest import
job's invoice-line set is truth for each PO-specific key.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    fact_ids: tuple[int, ...] = ()
    rows: int = 0
    units: float = 0.0


def regenerate_shipped_fact_upsert_keys(db: Session) -> int:
    """Recompute PO-inclusive ``fact_upsert_key`` on all shipped facts."""
    facts = list(
        db.scalars(
            select(FactInboundShipment).where(FactInboundShipment.line_state == "shipped")
        ).all()
    )
    updated = 0
    for f in facts:
        key = stable_shipped_fact_upsert_key_from_fields(
            operating_unit=f.operating_unit,
            delivery_no=f.delivery_no,
            item_code=f.item_code,
            purchase_order_id=f.purchase_order_id,
        )
        if not key:
            continue
        if f.fact_upsert_key != key:
            f.fact_upsert_key = key
            updated += 1
    db.flush()
    return updated


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
    return stable_shipped_fact_upsert_key_from_fields(
        operating_unit=f.operating_unit,
        delivery_no=f.delivery_no,
        item_code=f.item_code,
        purchase_order_id=f.purchase_order_id,
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
    if "|ord:" in (f.source_key or ""):
        return False  # order-grain key of a line not invoiced yet: a complete row, not an under-count
    if f.invoice_line is None and not shipped_source_key_has_invoice_segment(f.source_key):
        return True
    return False


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
) -> ShippedFactCollapseGroup:
    max_job = max(_job_id(f) for f in facts)
    latest_rows = [f for f in facts if _job_id(f) == max_job]
    older_rows = [f for f in facts if _job_id(f) != max_job]
    if not latest_rows:
        raise ValueError(f"no rows for max import_job_id on key {stable_key!r}")

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
        plans.append(_build_collapse_group(stable, members))

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
        "skipped_groups": len(skipped),
    }


# Backward-compatible aliases for tests importing old names
ShippedFactTwinGroup = ShippedFactCollapseGroup
ShippedFactTwinSkip = ShippedFactCollapseSkip
TwinBucket = CollapseBucket


def _classify_group(stable_key: str, facts: list[FactInboundShipment]) -> ShippedFactCollapseGroup:
    """Backward-compatible entry for unit tests."""
    return _build_collapse_group(stable_key, facts)


# --------------------------------------------------------------------------------------------- PO-less twins
# A shipped fact with no purchase_order_id keeps the key it was written under (``ship:{OU|delivery|item}``). Once the
# purchase order resolves, the same line is written under ``ship:{OU|delivery|item|PO}``: a different key, so the old
# row is never updated again and keeps counting (the 39 overdue vessels on cip, 1 Nov 2026). It is retired, not deleted:
# ``line_state`` becomes ``closed_superseded`` and every reader that excludes the closed states drops it. The collapse
# above needs two rows on one key and deletes the loser; this has two keys and keeps the row, so it is a separate rule
# in the same module, sharing its keeper-id convention.

LINE_SUPERSEDED = "closed_superseded"

_PO_LESS_TWINS_SQL = """
WITH old AS (
  SELECT f.id, f.tenant_id, f.operating_unit, f.delivery_no, f.item_code, f.quantity, f.import_job_id, f.fact_upsert_key
  FROM fact_inbound_shipment f
  WHERE f.line_state = 'shipped' AND f.purchase_order_id IS NULL
    AND coalesce(btrim(f.delivery_no), '') <> '' AND coalesce(btrim(f.item_code), '') <> ''
), twin AS (
  SELECT o.id AS old_id, count(*) AS twins, sum(coalesce(s.quantity, 0)) AS twin_qty,
         min(s.id) AS keeper_id, (array_agg(s.fact_upsert_key ORDER BY s.id))[1] AS keeper_key,
         max(s.import_job_id) AS keeper_job
  FROM old o
  JOIN fact_inbound_shipment s
    ON s.tenant_id = o.tenant_id AND s.id <> o.id AND s.line_state = 'shipped' AND s.purchase_order_id IS NOT NULL
   AND s.delivery_no = o.delivery_no AND s.item_code = o.item_code
   AND s.operating_unit IS NOT DISTINCT FROM o.operating_unit
   AND coalesce(s.import_job_id, 0) > coalesce(o.import_job_id, 0)
   {job_scope}
  GROUP BY o.id
)
SELECT o.id AS old_id, o.fact_upsert_key AS old_key, o.import_job_id AS old_job, o.delivery_no, o.item_code,
       coalesce(o.quantity, 0) AS old_qty, t.twins, t.twin_qty, t.keeper_id, t.keeper_key, t.keeper_job,
       (round(coalesce(o.quantity, 0), 4) = round(t.twin_qty, 4)) AS qty_match,
       (SELECT coalesce(sum(l.quantity), 0) FROM shipment_evidence_line l JOIN fact_inbound_shipment k ON k.id = t.keeper_id
         WHERE l.import_job_id = k.import_job_id AND l.line_state = 'shipped' AND l.delivery_no = o.delivery_no
           AND l.item_code = o.item_code AND l.purchase_order_id = k.purchase_order_id) AS evidence_qty
FROM old o JOIN twin t ON t.old_id = o.id
ORDER BY o.id
"""


@dataclass(frozen=True)
class PoLessTwin:
    old_id: int
    old_key: str | None
    old_job: int | None
    delivery_no: str | None
    item_code: str | None
    old_qty: float
    twins: int
    twin_qty: float
    keeper_id: int
    keeper_key: str | None
    keeper_job: int | None
    qty_match: bool
    evidence_qty: float = 0.0

    @property
    def evidence_match(self) -> bool:
        """The one PO-key twin holds exactly what its job's evidence lines add up to (the old fact saw only part of it)."""
        return self.twins == 1 and self.evidence_qty > 0 and round(self.evidence_qty, 4) == round(self.twin_qty, 4)

    def eligible(self, accept_evidence_sum: bool = False) -> bool:
        return self.qty_match or (accept_evidence_sum and self.evidence_match)


def plan_po_less_shipped_twins(db: Session, *, written_by_job: int | None = None) -> list[PoLessTwin]:
    """Every PO-less shipped fact that a newer job re-wrote under a PO-inclusive key (read only).

    ``written_by_job`` limits the twins to those that job wrote (the load-time call); ``None`` plans the whole table.
    """
    sql = _PO_LESS_TWINS_SQL.format(job_scope="AND s.import_job_id = :job" if written_by_job is not None else "")
    params = {"job": int(written_by_job)} if written_by_job is not None else {}
    return [
        PoLessTwin(
            old_id=int(r["old_id"]), old_key=r["old_key"], old_job=r["old_job"], delivery_no=r["delivery_no"],
            item_code=r["item_code"], old_qty=float(r["old_qty"]), twins=int(r["twins"]), twin_qty=float(r["twin_qty"]),
            keeper_id=int(r["keeper_id"]), keeper_key=r["keeper_key"], keeper_job=r["keeper_job"], qty_match=bool(r["qty_match"]),
            evidence_qty=float(r["evidence_qty"] or 0),
        )
        for r in db.execute(text(sql), params).mappings().all()
    ]


def retire_po_less_shipped_twins(db: Session, plan: list[PoLessTwin], *, accept_evidence_sum: bool = False) -> int:
    """Soft-retire the planned twins whose quantity equals their PO-key twins' (and, with ``accept_evidence_sum``, those whose
    single PO-key twin equals the sum of its job's evidence lines). Returns how many rows changed."""
    changed = 0
    for t in plan:
        if not t.eligible(accept_evidence_sum):
            continue
        r = db.execute(
            text(
                "UPDATE fact_inbound_shipment SET line_state = :st, superseded_by_fact_id = :k, superseded_by_key = :kk, "
                "updated_at = now() WHERE id = :id AND line_state = 'shipped' AND purchase_order_id IS NULL"
            ),
            {"st": LINE_SUPERSEDED, "k": t.keeper_id, "kk": t.keeper_key, "id": t.old_id},
        )
        changed += int(r.rowcount or 0)
    return changed


def refresh_superseded_pointers(db: Session) -> int:
    """A reload replaces a fact row (new id, same key): point retired facts at the current id of their key."""
    r = db.execute(
        text(
            "UPDATE fact_inbound_shipment f SET superseded_by_fact_id = k.id FROM fact_inbound_shipment k "
            "WHERE f.line_state = :st AND k.fact_upsert_key = f.superseded_by_key AND k.tenant_id = f.tenant_id "
            "AND f.superseded_by_fact_id IS DISTINCT FROM k.id"
        ),
        {"st": LINE_SUPERSEDED},
    )
    return int(r.rowcount or 0)


# An open order of the Shipped sheet has a fact key made from its source key. When a job is read again and a line's source key
# changes (the order now sits in the key of a line that is not invoiced yet), the old line is purged, its fact keeps the old key
# and loses its evidence line (``ON DELETE SET NULL``), and the job's own open-book close skips it: it is the same job, not an
# earlier one. It would be counted twice (the "needs a look" card showed 15 lines for 9). It is retired, pointing at the fact that
# now carries the same order line, or closed as disappeared when nothing does.
_ORPHAN_OPEN_SQL = """
SELECT o.id, o.order_no, o.order_line, o.item_code, o.quantity, o.source_key,
       r.id AS replaced_by, r.fact_upsert_key AS replaced_by_key
FROM fact_inbound_shipment o
LEFT JOIN LATERAL (
  SELECT n.id, n.fact_upsert_key FROM fact_inbound_shipment n
  WHERE n.tenant_id = o.tenant_id AND n.import_job_id = o.import_job_id AND n.id <> o.id AND n.shipment_evidence_line_id IS NOT NULL
    AND lower(n.line_state) = 'open_order' AND n.report_type = o.report_type AND n.order_no IS NOT DISTINCT FROM o.order_no
    AND n.order_line IS NOT DISTINCT FROM o.order_line AND n.item_code IS NOT DISTINCT FROM o.item_code
  ORDER BY n.id LIMIT 1
) r ON true
WHERE o.import_job_id = :job AND o.shipment_evidence_line_id IS NULL AND lower(o.line_state) = 'open_order'
ORDER BY o.id
"""


def plan_orphaned_open_rows(db: Session, import_job_id: int) -> list[dict[str, Any]]:
    """Open facts of this job that no evidence line carries any more (read only)."""
    return [dict(r) for r in db.execute(text(_ORPHAN_OPEN_SQL), {"job": int(import_job_id)}).mappings().all()]


def retire_orphaned_open_rows(db: Session, import_job_id: int, plan: list[dict[str, Any]] | None = None) -> dict[str, int]:
    """Soft-retire the orphaned open facts of a job: superseded by the fact of the same order line, else closed as disappeared."""
    plan = plan_orphaned_open_rows(db, import_job_id) if plan is None else plan
    superseded = disappeared = 0
    for r in plan:
        if r["replaced_by"] is not None:
            res = db.execute(
                text("UPDATE fact_inbound_shipment SET line_state = :st, superseded_by_fact_id = :k, superseded_by_key = :kk, updated_at = now() "
                     "WHERE id = :id AND shipment_evidence_line_id IS NULL AND lower(line_state) = 'open_order'"),
                {"st": LINE_SUPERSEDED, "k": r["replaced_by"], "kk": r["replaced_by_key"], "id": r["id"]},
            )
            superseded += int(res.rowcount or 0)
        else:
            res = db.execute(
                text("UPDATE fact_inbound_shipment SET line_state = 'closed_disappeared', updated_at = now() "
                     "WHERE id = :id AND shipment_evidence_line_id IS NULL AND lower(line_state) = 'open_order'"),
                {"id": r["id"]},
            )
            disappeared += int(res.rowcount or 0)
    return {"superseded": superseded, "disappeared": disappeared}


def retire_po_less_twins_written_by_job(db: Session, import_job_id: int) -> dict[str, Any]:
    """Load-time rule: the job just wrote PO-key facts; retire the PO-less twins they replace."""
    plan = plan_po_less_shipped_twins(db, written_by_job=int(import_job_id))
    retired = retire_po_less_shipped_twins(db, plan)
    repointed = refresh_superseded_pointers(db)
    return {
        "retired": retired,
        "repointed": repointed,
        "quantity_differs": [(t.old_id, t.old_qty, t.twin_qty) for t in plan if not t.qty_match],
    }
