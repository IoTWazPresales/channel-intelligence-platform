"""Governed one-off consolidation for duplicate provisional entities and alias-scope conflicts."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.models.dimensions import CustomerContact, CustomerLocation, DimCustomer, DimDistributor
from app.models.facts import FactInboundShipment, FactInventoryCustomer, FactReturns, FactSalesSellout
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
from app.models.import_distributor_si import CustomerSourceTokenAlias, ImportDistributorSiStagingLine, ImportEntityMappingCandidate
from app.services.customer_usage import _CUSTOMER_MAPPING_ENTITY_TYPES, _SPECS
from app.services.imports.provisional_entity_identity import canonical_provisional_entity_name_key


def repoint_customer_id_references_full(db: Session, *, loser_id: int, keeper_id: int) -> int:
    """Repoint every customer FK surface listed in ``customer_usage._SPECS`` plus shipment facts."""
    updates = 0
    for _label, col in _SPECS:
        model = col.class_
        if model.__table__.info.get("is_view"):
            continue
        result = db.execute(update(model).where(col == loser_id).values({col.key: keeper_id}))
        updates += int(result.rowcount or 0)

    from app.models.shipment_evidence import ShipmentEvidenceLine

    r1 = db.execute(
        update(ShipmentEvidenceLine).where(ShipmentEvidenceLine.customer_id == loser_id).values(customer_id=keeper_id)
    )
    r2 = db.execute(
        update(FactInboundShipment).where(FactInboundShipment.customer_id == loser_id).values(customer_id=keeper_id)
    )
    r3 = db.execute(
        update(ImportEntityMappingCandidate)
        .where(ImportEntityMappingCandidate.suggested_entity_id == loser_id)
        .values(suggested_entity_id=keeper_id)
    )
    r4 = db.execute(
        update(CustomerLocation).where(CustomerLocation.customer_id == loser_id).values(customer_id=keeper_id)
    )
    r5 = db.execute(
        update(CustomerContact).where(CustomerContact.customer_id == loser_id).values(customer_id=keeper_id)
    )
    updates += (
        int(r1.rowcount or 0)
        + int(r2.rowcount or 0)
        + int(r3.rowcount or 0)
        + int(r4.rowcount or 0)
        + int(r5.rowcount or 0)
    )
    return updates


def _repoint_customer_id_references(db: Session, *, loser_id: int, keeper_id: int) -> None:
    """Backward-compatible alias — use :func:`repoint_customer_id_references_full`."""
    repoint_customer_id_references_full(db, loser_id=loser_id, keeper_id=keeper_id)


def resolve_approved_customer_alias_scope_conflicts(
    db: Session,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Deprecated dry-run listing — steward merge uses ``customer_alias_scope_merge`` API.

    When ``dry_run=False``, raises — auto lowest-id merge is removed; use
    ``POST /customers/alias-scope-conflicts/merge-confirm`` with steward-selected survivor.
    """
    rows = db.execute(
        text(
            """
            SELECT normalized_token,
                   COALESCE(source_definition_id, -1) AS scope_src,
                   COALESCE(distributor_id, -1) AS scope_dist,
                   array_agg(DISTINCT customer_id ORDER BY customer_id) AS customer_ids,
                   COUNT(*) AS alias_rows
            FROM customer_source_token_alias
            WHERE status = 'approved'
            GROUP BY 1, 2, 3
            HAVING COUNT(DISTINCT customer_id) > 1
            ORDER BY 1, 2, 3
            """
        )
    ).fetchall()

    planned: list[dict[str, Any]] = []
    for r in rows:
        ids = [int(x) for x in (r[3] or [])]
        if len(ids) < 2:
            continue
        planned.append(
            {
                "normalized_token": str(r[0]),
                "source_definition_id": None if int(r[1]) < 0 else int(r[1]),
                "distributor_id": None if int(r[2]) < 0 else int(r[2]),
                "customer_ids": ids,
                "alias_rows": int(r[4] or 0),
                "deprecated": "Use POST /customers/alias-scope-conflicts/merge-preview with steward-selected survivor",
            }
        )

    out: dict[str, Any] = {
        "dry_run": dry_run,
        "conflict_group_count": len(planned),
        "planned_resolutions": planned,
        "deprecated": True,
    }
    if dry_run:
        return out

    raise RuntimeError(
        "Auto lowest-id alias-scope merge removed. Use steward merge via "
        "POST /customers/alias-scope-conflicts/merge-confirm"
    )


def dedupe_duplicate_approved_customer_alias_rows(
    db: Session,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Delete redundant approved customer alias rows in the same scope (same customer_id).

    Keeps the lowest ``id`` per ``(normalized_token, source_definition_id, distributor_id)``.
    Required before migration 0048 when duplicate rows share one ``customer_id``.
    """
    rows = db.execute(
        text(
            """
            SELECT normalized_token,
                   COALESCE(source_definition_id, -1) AS scope_src,
                   COALESCE(distributor_id, -1) AS scope_dist,
                   array_agg(id ORDER BY id) AS alias_ids,
                   COUNT(*) AS alias_rows
            FROM customer_source_token_alias
            WHERE status = 'approved'
            GROUP BY 1, 2, 3
            HAVING COUNT(*) > 1
            ORDER BY 1, 2, 3
            """
        )
    ).fetchall()

    planned: list[dict[str, Any]] = []
    loser_ids: list[int] = []
    for r in rows:
        ids = [int(x) for x in (r[3] or [])]
        if len(ids) < 2:
            continue
        keeper = int(ids[0])
        losers = [int(x) for x in ids[1:]]
        loser_ids.extend(losers)
        planned.append(
            {
                "normalized_token": str(r[0]),
                "keeper_alias_id": keeper,
                "delete_alias_ids": losers,
                "alias_rows": int(r[4] or 0),
            }
        )

    out: dict[str, Any] = {
        "dry_run": dry_run,
        "duplicate_scope_count": len(planned),
        "delete_alias_count": len(loser_ids),
        "planned": planned[:50],
    }
    if dry_run:
        return out

    deleted = 0
    for aid in loser_ids:
        row = db.get(CustomerSourceTokenAlias, int(aid))
        if row is not None:
            db.delete(row)
            deleted += 1
    db.commit()
    out["deleted_alias_rows"] = deleted
    return out


def build_distributor_id_to_canonical_key(db: Session) -> dict[int, str]:
    """Map every ``dim_distributor.id`` to canonical display-name key (for receipt / merge scope)."""
    out: dict[int, str] = {}
    for row in db.execute(select(DimDistributor.id, DimDistributor.name)):
        did = int(row[0])
        out[did] = canonical_provisional_entity_name_key(str(row[1] or "")) or f"__id_{did}"
    return out
