"""Merge duplicate ``purchase_order`` rows with NULL ``distributor_id`` (Unit 2 PO dedup).

Postgres unique (po_number_norm, distributor_id) allows unlimited dupes when distributor_id IS NULL.
Preview-first: plan groups by ``po_number_norm``, pick one keeper per norm, repoint FKs, delete losers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.models.commercial_lineup import CommercialLineupCasePo
from app.models.facts import FactInboundShipment
from app.models.purchase_order import PurchaseOrder
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation


@dataclass(frozen=True)
class NullDistPoMergeGroup:
    po_number_norm: str
    keeper_id: int
    loser_ids: tuple[int, ...]
    evidence_lines_per_po: dict[int, int] = field(default_factory=dict)
    case_links_per_po: dict[int, int] = field(default_factory=dict)


def _evidence_counts(db: Session, po_ids: list[int]) -> dict[int, int]:
    if not po_ids:
        return {}
    rows = db.execute(
        select(ShipmentEvidenceLine.purchase_order_id, func.count())
        .where(ShipmentEvidenceLine.purchase_order_id.in_(po_ids))
        .group_by(ShipmentEvidenceLine.purchase_order_id)
    ).all()
    return {int(pid): int(n) for pid, n in rows if pid is not None}


def _case_link_counts(db: Session, po_ids: list[int]) -> dict[int, int]:
    if not po_ids:
        return {}
    rows = db.execute(
        select(CommercialLineupCasePo.purchase_order_id, func.count())
        .where(CommercialLineupCasePo.purchase_order_id.in_(po_ids))
        .group_by(CommercialLineupCasePo.purchase_order_id)
    ).all()
    return {int(pid): int(n) for pid, n in rows}


def _pick_keeper(po_ids: list[int], evidence: dict[int, int], case_links: dict[int, int]) -> int:
    """Keeper = most shipment evidence links, then most case links, then lowest id."""

    def sort_key(pid: int) -> tuple[int, int, int]:
        return (-evidence.get(pid, 0), -case_links.get(pid, 0), pid)

    return min(po_ids, key=sort_key)


def plan_null_distributor_po_merges(db: Session) -> list[NullDistPoMergeGroup]:
    """Build merge plan for NULL-distributor PO norms with more than one row."""
    dup_norms = [
        str(r[0])
        for r in db.execute(
            select(PurchaseOrder.po_number_norm)
            .where(PurchaseOrder.distributor_id.is_(None))
            .group_by(PurchaseOrder.po_number_norm)
            .having(func.count() > 1)
            .order_by(PurchaseOrder.po_number_norm)
        ).all()
    ]
    if not dup_norms:
        return []

    plans: list[NullDistPoMergeGroup] = []
    for norm in dup_norms:
        po_rows = list(
            db.scalars(
                select(PurchaseOrder.id)
                .where(
                    PurchaseOrder.distributor_id.is_(None),
                    PurchaseOrder.po_number_norm == norm,
                )
                .order_by(PurchaseOrder.id)
            ).all()
        )
        po_ids = [int(x) for x in po_rows]
        if len(po_ids) < 2:
            continue
        evidence = _evidence_counts(db, po_ids)
        case_links = _case_link_counts(db, po_ids)
        keeper = _pick_keeper(po_ids, evidence, case_links)
        losers = tuple(pid for pid in po_ids if pid != keeper)
        plans.append(
            NullDistPoMergeGroup(
                po_number_norm=norm,
                keeper_id=keeper,
                loser_ids=losers,
                evidence_lines_per_po=evidence,
                case_links_per_po=case_links,
            )
        )
    return plans


def _repoint_case_po_links(db: Session, keeper_id: int, loser_id: int) -> dict[str, int]:
    """Move case links from loser to keeper; drop duplicates on (case_id, keeper)."""
    stats = {"updated": 0, "deleted_dup": 0}
    links = list(
        db.scalars(
            select(CommercialLineupCasePo).where(CommercialLineupCasePo.purchase_order_id == int(loser_id))
        ).all()
    )
    for link in links:
        exists = db.scalar(
            select(CommercialLineupCasePo.id).where(
                CommercialLineupCasePo.case_id == int(link.case_id),
                CommercialLineupCasePo.purchase_order_id == int(keeper_id),
            )
        )
        if exists is not None:
            db.delete(link)
            stats["deleted_dup"] += 1
        else:
            link.purchase_order_id = int(keeper_id)
            db.add(link)
            stats["updated"] += 1
    return stats


def _repoint_observation_po_links(db: Session, keeper_id: int, loser_id: int) -> int:
    """Repoint observation FKs; no-op when role lacks table grant (dev ``cip`` user)."""
    try:
        with db.begin_nested():
            r = db.execute(
                update(ShipmentEvidenceObservation)
                .where(ShipmentEvidenceObservation.purchase_order_id == int(loser_id))
                .values(purchase_order_id=int(keeper_id))
            )
            return int(r.rowcount or 0)
    except ProgrammingError as exc:
        msg = str(exc).lower()
        if "permission denied" in msg or "insufficientprivilege" in msg:
            return 0
        raise


def execute_null_distributor_po_merge(
    db: Session,
    group: NullDistPoMergeGroup,
) -> dict[str, int]:
    """Repoint FKs from loser PO ids to keeper and delete loser ``purchase_order`` rows."""
    stats = {
        "losers_deleted": 0,
        "evidence_lines_updated": 0,
        "facts_updated": 0,
        "observations_updated": 0,
        "case_links_updated": 0,
        "case_links_deduped": 0,
    }
    keeper = int(group.keeper_id)
    for loser in group.loser_ids:
        lid = int(loser)
        r = db.execute(
            update(ShipmentEvidenceLine)
            .where(ShipmentEvidenceLine.purchase_order_id == lid)
            .values(purchase_order_id=keeper)
        )
        stats["evidence_lines_updated"] += int(r.rowcount or 0)
        r = db.execute(
            update(FactInboundShipment)
            .where(FactInboundShipment.purchase_order_id == lid)
            .values(purchase_order_id=keeper)
        )
        stats["facts_updated"] += int(r.rowcount or 0)
        stats["observations_updated"] += _repoint_observation_po_links(db, keeper, lid)
        cl = _repoint_case_po_links(db, keeper, lid)
        stats["case_links_updated"] += cl["updated"]
        stats["case_links_deduped"] += cl["deleted_dup"]
        db.execute(delete(PurchaseOrder).where(PurchaseOrder.id == lid))
        stats["losers_deleted"] += 1
    db.flush()
    return stats


def merge_summary_stats(db: Session) -> dict[str, int]:
    """High-level NULL-distributor PO duplication counts."""
    total_null = int(
        db.scalar(select(func.count()).select_from(PurchaseOrder).where(PurchaseOrder.distributor_id.is_(None)))
        or 0
    )
    distinct_norms = int(
        db.scalar(
            select(func.count(func.distinct(PurchaseOrder.po_number_norm))).where(
                PurchaseOrder.distributor_id.is_(None)
            )
        )
        or 0
    )
    dup_norms = int(
        db.scalar(
            select(func.count())
            .select_from(
                select(PurchaseOrder.po_number_norm)
                .where(PurchaseOrder.distributor_id.is_(None))
                .group_by(PurchaseOrder.po_number_norm)
                .having(func.count() > 1)
                .subquery()
            )
        )
        or 0
    )
    return {
        "purchase_order_null_distributor_rows": total_null,
        "distinct_null_distributor_norms": distinct_norms,
        "norms_with_duplicates": dup_norms,
        "rows_mergeable": total_null - distinct_norms,
    }


def merge_plan_to_dict(group: NullDistPoMergeGroup) -> dict[str, Any]:
    return {
        "po_number_norm": group.po_number_norm,
        "keeper_id": group.keeper_id,
        "loser_ids": list(group.loser_ids),
        "evidence_lines_per_po": group.evidence_lines_per_po,
        "case_links_per_po": group.case_links_per_po,
    }
