"""Merge NULL-distributor ``purchase_order`` rows into distributor-set siblings (Unit 2b).

Post-NULL-only dedup, norms may still have one NULL row and one (or more) distributor-set rows.
Keeper = the single distributor-set row; losers = all NULL rows for that norm.
Skip when multiple distinct distributor-set rows exist (steward review) or repoint would violate
a unique constraint we cannot safely resolve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.models.commercial_lineup import CommercialLineupCasePo, CommercialLineupPoAutoLinkDismiss
from app.models.facts import FactInboundShipment
from app.models.purchase_order import PurchaseOrder
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.services.imports.shipment_null_distributor_po_merge import _repoint_case_po_links

# Every FK column referencing purchase_order.id (enumerated from pg_constraint on cip).
PO_FK_TABLES: tuple[tuple[str, str], ...] = (
    ("shipment_evidence_line", "purchase_order_id"),
    ("fact_inbound_shipment", "purchase_order_id"),
    ("shipment_evidence_observation", "purchase_order_id"),
    ("commercial_lineup_case_po", "purchase_order_id"),
    ("commercial_lineup_po_auto_link_dismiss", "purchase_order_id"),
)


@dataclass(frozen=True)
class SiblingPoMergeGroup:
    po_number_norm: str
    keeper_id: int
    keeper_distributor_id: int
    loser_ids: tuple[int, ...]
    repoint_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class SiblingPoMergeSkip:
    po_number_norm: str
    reason: str
    null_po_ids: tuple[int, ...] = ()
    distributor_po_ids: tuple[int, ...] = ()
    distributor_ids: tuple[int | None, ...] = ()


class SiblingPoMergeAbortError(RuntimeError):
    """Raised when repoint or pre-delete checks fail — caller must roll back the transaction."""

    def __init__(self, message: str, *, loser_id: int, table: str | None = None, remaining: int = 0):
        self.loser_id = int(loser_id)
        self.table = table
        self.remaining = int(remaining)
        super().__init__(message)


def _observation_loser_ref_count(db: Session, loser_id: int) -> int:
    """Count observation FK rows for loser; permission denied is a hard merge abort."""
    try:
        return int(
            db.scalar(
                select(func.count())
                .select_from(ShipmentEvidenceObservation)
                .where(ShipmentEvidenceObservation.purchase_order_id == int(loser_id))
            )
            or 0
        )
    except ProgrammingError as exc:
        msg = str(exc).lower()
        if "permission denied" in msg or "insufficientprivilege" in msg:
            raise SiblingPoMergeAbortError(
                f"permission denied counting shipment_evidence_observation refs for loser {loser_id}",
                loser_id=int(loser_id),
                table="shipment_evidence_observation",
            ) from exc
        raise


def _strict_loser_ref_counts(db: Session, loser_id: int) -> dict[str, int]:
    """Count FK rows still pointing at ``loser_id`` (strict — no permission swallow)."""
    lid = int(loser_id)
    return {
        "shipment_evidence_line": int(
            db.scalar(
                select(func.count())
                .select_from(ShipmentEvidenceLine)
                .where(ShipmentEvidenceLine.purchase_order_id == lid)
            )
            or 0
        ),
        "fact_inbound_shipment": int(
            db.scalar(
                select(func.count())
                .select_from(FactInboundShipment)
                .where(FactInboundShipment.purchase_order_id == lid)
            )
            or 0
        ),
        "shipment_evidence_observation": _observation_loser_ref_count(db, lid),
        "commercial_lineup_case_po": int(
            db.scalar(
                select(func.count())
                .select_from(CommercialLineupCasePo)
                .where(CommercialLineupCasePo.purchase_order_id == lid)
            )
            or 0
        ),
        "commercial_lineup_po_auto_link_dismiss": int(
            db.scalar(
                select(func.count())
                .select_from(CommercialLineupPoAutoLinkDismiss)
                .where(CommercialLineupPoAutoLinkDismiss.purchase_order_id == lid)
            )
            or 0
        ),
    }


def _assert_zero_loser_refs(db: Session, loser_id: int) -> None:
    """Pre-delete gate: every FK table must have zero rows referencing the loser."""
    for table, remaining in _strict_loser_ref_counts(db, int(loser_id)).items():
        if remaining > 0:
            raise SiblingPoMergeAbortError(
                f"purchase_order loser {loser_id} still referenced by {remaining} row(s) "
                f"in {table} after repoint",
                loser_id=int(loser_id),
                table=table,
                remaining=remaining,
            )


def _require_repoint_rowcount(
    *,
    expected: int,
    actual: int,
    table: str,
    loser_id: int,
) -> None:
    if expected > 0 and actual != expected:
        raise SiblingPoMergeAbortError(
            f"repoint {table} for loser {loser_id}: expected {expected} row(s) updated, got {actual}",
            loser_id=int(loser_id),
            table=table,
            remaining=expected,
        )


def _repoint_observation_po_links_strict(db: Session, keeper_id: int, loser_id: int) -> int:
    """Repoint observation FKs; permission or rowcount mismatch is a hard failure."""
    try:
        r = db.execute(
            update(ShipmentEvidenceObservation)
            .where(ShipmentEvidenceObservation.purchase_order_id == int(loser_id))
            .values(purchase_order_id=int(keeper_id))
        )
        return int(r.rowcount or 0)
    except ProgrammingError as exc:
        msg = str(exc).lower()
        if "permission denied" in msg or "insufficientprivilege" in msg:
            raise SiblingPoMergeAbortError(
                f"permission denied repointing shipment_evidence_observation for loser {loser_id}",
                loser_id=int(loser_id),
                table="shipment_evidence_observation",
            ) from exc
        raise


def _sibling_norms_subquery():
    """Norms with at least one NULL row and at least one distributor-set row."""
    null_norms = (
        select(PurchaseOrder.po_number_norm)
        .where(PurchaseOrder.distributor_id.is_(None))
        .group_by(PurchaseOrder.po_number_norm)
    )
    dist_norms = (
        select(PurchaseOrder.po_number_norm)
        .where(PurchaseOrder.distributor_id.isnot(None))
        .group_by(PurchaseOrder.po_number_norm)
    )
    return (
        select(PurchaseOrder.po_number_norm)
        .where(PurchaseOrder.po_number_norm.in_(null_norms.intersect(dist_norms)))
        .distinct()
        .order_by(PurchaseOrder.po_number_norm)
    )


def _po_ids_for_norm(db: Session, norm: str, *, distributor_null: bool) -> list[int]:
    stmt = select(PurchaseOrder.id).where(PurchaseOrder.po_number_norm == norm)
    if distributor_null:
        stmt = stmt.where(PurchaseOrder.distributor_id.is_(None))
    else:
        stmt = stmt.where(PurchaseOrder.distributor_id.isnot(None))
    return [int(x) for x in db.scalars(stmt.order_by(PurchaseOrder.id)).all()]


def _distributor_ids_for_pos(db: Session, po_ids: list[int]) -> list[int]:
    if not po_ids:
        return []
    rows = db.execute(
        select(PurchaseOrder.distributor_id)
        .where(PurchaseOrder.id.in_(po_ids), PurchaseOrder.distributor_id.isnot(None))
        .distinct()
        .order_by(PurchaseOrder.distributor_id)
    ).all()
    return [int(r[0]) for r in rows if r[0] is not None]


def _count_fk_rows(db: Session, table: str, column: str, po_id: int) -> int:
    if table == "shipment_evidence_line":
        return int(
            db.scalar(
                select(func.count())
                .select_from(ShipmentEvidenceLine)
                .where(ShipmentEvidenceLine.purchase_order_id == int(po_id))
            )
            or 0
        )
    if table == "fact_inbound_shipment":
        return int(
            db.scalar(
                select(func.count())
                .select_from(FactInboundShipment)
                .where(FactInboundShipment.purchase_order_id == int(po_id))
            )
            or 0
        )
    if table == "commercial_lineup_case_po":
        return int(
            db.scalar(
                select(func.count())
                .select_from(CommercialLineupCasePo)
                .where(CommercialLineupCasePo.purchase_order_id == int(po_id))
            )
            or 0
        )
    if table == "commercial_lineup_po_auto_link_dismiss":
        return int(
            db.scalar(
                select(func.count())
                .select_from(CommercialLineupPoAutoLinkDismiss)
                .where(CommercialLineupPoAutoLinkDismiss.purchase_order_id == int(po_id))
            )
            or 0
        )
    # shipment_evidence_observation — optional grant on dev ``cip`` user
    from sqlalchemy.exc import ProgrammingError

    from app.models.shipment_evidence_observation import ShipmentEvidenceObservation

    try:
        with db.begin_nested():
            return int(
                db.scalar(
                    select(func.count())
                    .select_from(ShipmentEvidenceObservation)
                    .where(ShipmentEvidenceObservation.purchase_order_id == int(po_id))
                )
                or 0
            )
    except ProgrammingError as exc:
        msg = str(exc).lower()
        if "permission denied" in msg or "insufficientprivilege" in msg:
            return 0
        raise


def _repoint_counts_for_losers(db: Session, keeper_id: int, loser_ids: tuple[int, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table, column in PO_FK_TABLES:
        key = f"{table}.{column}"
        counts[key] = sum(_count_fk_rows(db, table, column, int(lid)) for lid in loser_ids)
    counts["purchase_order.delete"] = len(loser_ids)
    return counts


def _would_violate_unique_on_repoint(db: Session, keeper_id: int, loser_ids: tuple[int, ...]) -> str | None:
    """Return a skip reason when repointing would hit a unique constraint we cannot resolve."""
    if not loser_ids:
        return None

    # fact_inbound_shipment.source_key is globally unique; repointing purchase_order_id is safe.
    # commercial_lineup_case_po (case_id, purchase_order_id) is resolved via dedup on repoint.
    # Evidence / observation rows are keyed by (import_job_id, source_key) / row hash — not PO id.

    # Guard: two distributor-set rows for the same (norm, distributor_id) should not exist; if they
    # do, merging NULL losers into one keeper would be ambiguous at the PO identity layer.
    keeper = db.get(PurchaseOrder, int(keeper_id))
    if keeper is None:
        return "keeper_missing"
    dup_dist_row = db.scalar(
        select(func.count())
        .select_from(PurchaseOrder)
        .where(
            PurchaseOrder.po_number_norm == keeper.po_number_norm,
            PurchaseOrder.distributor_id == keeper.distributor_id,
            PurchaseOrder.id != int(keeper_id),
        )
    )
    if int(dup_dist_row or 0) > 0:
        return "duplicate_distributor_set_po_rows"

    # Dismiss rows are keyed by proposal_key (case:customer:norm), not purchase_order_id — safe.

    # Hypothetical future unique on (purchase_order_id, …): detect overlapping fact source_keys
    # only when the same source_key appears on facts for both loser and keeper (would indicate
    # corrupt duplicate facts, not a mergeable sibling pair).
    loser_fact_keys = {
        str(r[0])
        for r in db.execute(
            select(FactInboundShipment.source_key).where(
                FactInboundShipment.purchase_order_id.in_([int(x) for x in loser_ids])
            )
        ).all()
    }
    if loser_fact_keys:
        overlap = db.scalar(
            select(func.count())
            .select_from(FactInboundShipment)
            .where(
                FactInboundShipment.purchase_order_id == int(keeper_id),
                FactInboundShipment.source_key.in_(loser_fact_keys),
            )
        )
        if int(overlap or 0) > 0:
            return "fact_source_key_overlap"
    return None


def plan_null_distributor_sibling_po_merges(db: Session) -> tuple[list[SiblingPoMergeGroup], list[SiblingPoMergeSkip]]:
    """Build merge plan for NULL + distributor-set sibling PO norms."""
    norms = [str(r[0]) for r in db.execute(_sibling_norms_subquery()).all()]
    plans: list[SiblingPoMergeGroup] = []
    skipped: list[SiblingPoMergeSkip] = []

    for norm in norms:
        null_ids = _po_ids_for_norm(db, norm, distributor_null=True)
        dist_ids = _po_ids_for_norm(db, norm, distributor_null=False)
        if not null_ids or not dist_ids:
            continue

        distinct_distributors = _distributor_ids_for_pos(db, dist_ids)
        if len(distinct_distributors) != 1:
            skipped.append(
                SiblingPoMergeSkip(
                    po_number_norm=norm,
                    reason="ambiguous_multiple_distributors",
                    null_po_ids=tuple(null_ids),
                    distributor_po_ids=tuple(dist_ids),
                    distributor_ids=tuple(distinct_distributors),
                )
            )
            continue

        if len(dist_ids) != 1:
            skipped.append(
                SiblingPoMergeSkip(
                    po_number_norm=norm,
                    reason="ambiguous_multiple_distributor_set_rows",
                    null_po_ids=tuple(null_ids),
                    distributor_po_ids=tuple(dist_ids),
                    distributor_ids=tuple(distinct_distributors),
                )
            )
            continue

        keeper_id = int(dist_ids[0])
        loser_ids = tuple(null_ids)
        unsafe = _would_violate_unique_on_repoint(db, keeper_id, loser_ids)
        if unsafe:
            skipped.append(
                SiblingPoMergeSkip(
                    po_number_norm=norm,
                    reason=f"unsafe_{unsafe}",
                    null_po_ids=loser_ids,
                    distributor_po_ids=(keeper_id,),
                    distributor_ids=(distinct_distributors[0],),
                )
            )
            continue

        plans.append(
            SiblingPoMergeGroup(
                po_number_norm=norm,
                keeper_id=keeper_id,
                keeper_distributor_id=distinct_distributors[0],
                loser_ids=loser_ids,
                repoint_counts=_repoint_counts_for_losers(db, keeper_id, loser_ids),
            )
        )
    return plans, skipped


def _repoint_dismiss_links(db: Session, keeper_id: int, loser_id: int) -> int:
    r = db.execute(
        update(CommercialLineupPoAutoLinkDismiss)
        .where(CommercialLineupPoAutoLinkDismiss.purchase_order_id == int(loser_id))
        .values(purchase_order_id=int(keeper_id))
    )
    return int(r.rowcount or 0)


def execute_null_distributor_sibling_po_merge(
    db: Session,
    group: SiblingPoMergeGroup,
) -> dict[str, int]:
    """Repoint all FK references from NULL loser PO ids to distributor-set keeper; delete losers."""
    stats = {
        "losers_deleted": 0,
        "evidence_lines_updated": 0,
        "facts_updated": 0,
        "observations_updated": 0,
        "case_links_updated": 0,
        "case_links_deduped": 0,
        "dismiss_rows_updated": 0,
    }
    keeper = int(group.keeper_id)
    for loser in group.loser_ids:
        lid = int(loser)
        before = _strict_loser_ref_counts(db, lid)

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
        stats["evidence_lines_updated"] += ev_updated

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
        stats["facts_updated"] += fact_updated

        obs_updated = _repoint_observation_po_links_strict(db, keeper, lid)
        _require_repoint_rowcount(
            expected=before["shipment_evidence_observation"],
            actual=obs_updated,
            table="shipment_evidence_observation",
            loser_id=lid,
        )
        stats["observations_updated"] += obs_updated

        cl = _repoint_case_po_links(db, keeper, lid)
        case_handled = int(cl["updated"]) + int(cl["deleted_dup"])
        _require_repoint_rowcount(
            expected=before["commercial_lineup_case_po"],
            actual=case_handled,
            table="commercial_lineup_case_po",
            loser_id=lid,
        )
        stats["case_links_updated"] += cl["updated"]
        stats["case_links_deduped"] += cl["deleted_dup"]

        dismiss_updated = _repoint_dismiss_links(db, keeper, lid)
        _require_repoint_rowcount(
            expected=before["commercial_lineup_po_auto_link_dismiss"],
            actual=dismiss_updated,
            table="commercial_lineup_po_auto_link_dismiss",
            loser_id=lid,
        )
        stats["dismiss_rows_updated"] += dismiss_updated

        db.flush()
        _assert_zero_loser_refs(db, lid)
        db.execute(delete(PurchaseOrder).where(PurchaseOrder.id == lid))
        stats["losers_deleted"] += 1
    db.flush()
    return stats


def sibling_merge_summary_stats(db: Session) -> dict[str, int]:
    """Counts for NULL + distributor-set sibling population."""
    plans, skipped = plan_null_distributor_sibling_po_merges(db)
    null_sibling_rows = int(
        db.scalar(
            select(func.count())
            .select_from(PurchaseOrder)
            .where(
                PurchaseOrder.distributor_id.is_(None),
                PurchaseOrder.po_number_norm.in_(_sibling_norms_subquery()),
            )
        )
        or 0
    )
    dist_sibling_rows = int(
        db.scalar(
            select(func.count())
            .select_from(PurchaseOrder)
            .where(
                PurchaseOrder.distributor_id.isnot(None),
                PurchaseOrder.po_number_norm.in_(_sibling_norms_subquery()),
            )
        )
        or 0
    )
    return {
        "sibling_norm_groups_total": len(plans) + len(skipped),
        "mergeable_groups": len(plans),
        "skipped_groups": len(skipped),
        "mergeable_null_losers": sum(len(g.loser_ids) for g in plans),
        "skipped_ambiguous": sum(1 for s in skipped if s.reason.startswith("ambiguous_")),
        "skipped_unsafe": sum(1 for s in skipped if s.reason.startswith("unsafe_")),
        "null_distributor_sibling_rows": null_sibling_rows,
        "distributor_set_sibling_rows": dist_sibling_rows,
    }


def sibling_merge_plan_to_dict(group: SiblingPoMergeGroup) -> dict[str, Any]:
    return {
        "po_number_norm": group.po_number_norm,
        "keeper_id": group.keeper_id,
        "keeper_distributor_id": group.keeper_distributor_id,
        "loser_ids": list(group.loser_ids),
        "repoint_counts": group.repoint_counts,
    }


def sibling_merge_skip_to_dict(skip: SiblingPoMergeSkip) -> dict[str, Any]:
    return {
        "po_number_norm": skip.po_number_norm,
        "reason": skip.reason,
        "null_po_ids": list(skip.null_po_ids),
        "distributor_po_ids": list(skip.distributor_po_ids),
        "distributor_ids": list(skip.distributor_ids),
    }
