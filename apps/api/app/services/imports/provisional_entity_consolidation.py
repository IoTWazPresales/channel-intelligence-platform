"""Governed one-off consolidation for duplicate provisional entities and alias-scope conflicts."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.models.dimensions import CustomerContact, CustomerLocation, DimCustomer, DimDistributor
from app.models.facts import FactInventoryCustomer, FactReturns, FactSalesSellout
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
from app.models.import_distributor_si import CustomerSourceTokenAlias, ImportDistributorSiStagingLine, ImportEntityMappingCandidate
from app.services.imports.provisional_entity_identity import canonical_provisional_entity_name_key


def _repoint_customer_id_references(db: Session, *, loser_id: int, keeper_id: int) -> None:
  """Point customer FKs at ``keeper_id`` before deleting a duplicate provisional customer."""
  db.execute(
      update(ImportDistributorSiStagingLine)
      .where(ImportDistributorSiStagingLine.resolved_customer_id == loser_id)
      .values(resolved_customer_id=keeper_id)
  )
  db.execute(
      update(ImportCustomerSellthroughStagingLine)
      .where(ImportCustomerSellthroughStagingLine.resolved_customer_id == loser_id)
      .values(resolved_customer_id=keeper_id)
  )
  db.execute(
      update(FactSalesSellout).where(FactSalesSellout.customer_id == loser_id).values(customer_id=keeper_id)
  )
  db.execute(
      update(FactReturns).where(FactReturns.customer_id == loser_id).values(customer_id=keeper_id)
  )
  db.execute(
      update(FactInventoryCustomer).where(FactInventoryCustomer.customer_id == loser_id).values(customer_id=keeper_id)
  )
  db.execute(
      update(ImportEntityMappingCandidate)
      .where(ImportEntityMappingCandidate.suggested_entity_id == loser_id)
      .values(suggested_entity_id=keeper_id)
  )
  from app.models.shipment_evidence import ShipmentEvidenceLine

  db.execute(
      update(ShipmentEvidenceLine).where(ShipmentEvidenceLine.customer_id == loser_id).values(customer_id=keeper_id)
  )


def resolve_approved_customer_alias_scope_conflicts(
    db: Session,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Collapse approved customer aliases where one scope maps to multiple ``customer_id`` values.

    Keeper rule: lowest ``customer_id`` per
    ``(normalized_token, source_definition_id, distributor_id)`` scope. Loser customers are
  deleted only when they have no locations/contacts and no remaining aliases after repoint.
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
        keeper = int(ids[0])
        losers = [int(x) for x in ids[1:]]
        planned.append(
            {
                "normalized_token": str(r[0]),
                "source_definition_id": None if int(r[1]) < 0 else int(r[1]),
                "distributor_id": None if int(r[2]) < 0 else int(r[2]),
                "keeper_id": keeper,
                "loser_ids": losers,
                "alias_rows": int(r[4] or 0),
            }
        )

    out: dict[str, Any] = {
        "dry_run": dry_run,
        "conflict_group_count": len(planned),
        "planned_resolutions": planned,
    }
    if dry_run:
        return out

    repointed_aliases = 0
    deleted_customers: list[int] = []
    skipped_customers: list[dict[str, Any]] = []

    for entry in planned:
        kid = int(entry["keeper_id"])
        nt = str(entry["normalized_token"])
        sid = entry["source_definition_id"]
        did = entry["distributor_id"]
        for lid in entry["loser_ids"]:
            conds = [
                CustomerSourceTokenAlias.normalized_token == nt,
                CustomerSourceTokenAlias.status == "approved",
                CustomerSourceTokenAlias.customer_id == int(lid),
            ]
            if sid is None:
                conds.append(CustomerSourceTokenAlias.source_definition_id.is_(None))
            else:
                conds.append(CustomerSourceTokenAlias.source_definition_id == int(sid))
            if did is None:
                conds.append(CustomerSourceTokenAlias.distributor_id.is_(None))
            else:
                conds.append(CustomerSourceTokenAlias.distributor_id == int(did))

            aliases = list(db.scalars(select(CustomerSourceTokenAlias).where(*conds)).all())
            for al in aliases:
                dup = db.scalars(
                    select(CustomerSourceTokenAlias)
                    .where(
                        CustomerSourceTokenAlias.customer_id == kid,
                        CustomerSourceTokenAlias.normalized_token == al.normalized_token,
                        CustomerSourceTokenAlias.raw_token == al.raw_token,
                    )
                    .limit(1)
                ).first()
                if dup is not None:
                    db.delete(al)
                else:
                    al.customer_id = kid
                    db.add(al)
                repointed_aliases += 1

            _repoint_customer_id_references(db, loser_id=int(lid), keeper_id=kid)

            n_loc = int(
                db.scalar(select(func.count()).select_from(CustomerLocation).where(CustomerLocation.customer_id == lid))
                or 0
            )
            n_con = int(
                db.scalar(select(func.count()).select_from(CustomerContact).where(CustomerContact.customer_id == lid))
                or 0
            )
            n_alias = int(
                db.scalar(
                    select(func.count())
                    .select_from(CustomerSourceTokenAlias)
                    .where(CustomerSourceTokenAlias.customer_id == lid)
                )
                or 0
            )
            if n_loc > 0 or n_con > 0 or n_alias > 0:
                skipped_customers.append(
                    {"customer_id": int(lid), "reason": "has_locations_contacts_or_aliases", "keeper_id": kid}
                )
                continue
            loser_row = db.get(DimCustomer, int(lid))
            if loser_row is not None:
                db.delete(loser_row)
                deleted_customers.append(int(lid))
            db.flush()

    db.commit()
    out["repointed_alias_ops"] = repointed_aliases
    out["deleted_customer_ids"] = deleted_customers
    out["skipped_customers"] = skipped_customers
    return out


def build_distributor_id_to_canonical_key(db: Session) -> dict[int, str]:
    """Map every ``dim_distributor.id`` to canonical display-name key (for receipt / merge scope)."""
    out: dict[int, str] = {}
    for row in db.execute(select(DimDistributor.id, DimDistributor.name)):
        did = int(row[0])
        out[did] = canonical_provisional_entity_name_key(str(row[1] or "")) or f"__id_{did}"
    return out
