"""Physical distributor FK repoint with all-or-nothing zero-ref guard (full merge)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.models.commercial_planner import CommercialDistributorTerm
from app.models.import_distributor_si import (
    CustomerSourceTokenAlias,
    DistributorSourceTokenAlias,
    ImportEntityMappingCandidate,
)
from app.services.distributor_fk_discovery import discover_distributor_fk_columns, extra_distributor_ref_specs
from app.services.distributor_merge_po_consolidation import (
    DistributorPoConsolidationAbortError,
    execute_distributor_owned_po_actions,
)
from app.services.distributor_usage import _DISTRIBUTOR_MAPPING_ENTITY_TYPES

_UNIQUE_PER_DISTRIBUTOR_TABLES = frozenset({"commercial_distributor_term"})

_SKIP_BLIND_UPDATE = frozenset(
    {
        "purchase_order",  # handled by PO consolidation sub-engine
        "distributor_source_token_alias",
        "customer_source_token_alias",
    }
)


class DistributorFullRepointAbortError(RuntimeError):
    def __init__(self, message: str, *, loser_id: int, table: str | None = None, remaining: int = 0):
        self.loser_id = int(loser_id)
        self.table = table
        self.remaining = int(remaining)
        super().__init__(message)


def count_distributor_fk_refs(db: Session, distributor_id: int) -> dict[str, int]:
    did = int(distributor_id)
    counts: dict[str, int] = {}
    for table, column in discover_distributor_fk_columns(db):
        key = f"{table}.{column}"
        try:
            n = int(
                db.execute(
                    text(f"SELECT count(*) FROM {table} WHERE {column} = :did"),
                    {"did": did},
                ).scalar()
                or 0
            )
        except ProgrammingError:
            n = 0
        if n:
            counts[key] = n

    for table, column, where_extra in extra_distributor_ref_specs():
        key = f"{table}.{column}"
        try:
            n = int(
                db.execute(
                    text(f"SELECT count(*) FROM {table} WHERE {column} = :did AND ({where_extra})"),
                    {"did": did},
                ).scalar()
                or 0
            )
        except ProgrammingError:
            n = 0
        if n:
            counts[key] = n
    return counts


def _assert_zero_loser_refs(db: Session, loser_id: int) -> None:
    for key, remaining in count_distributor_fk_refs(db, int(loser_id)).items():
        if remaining > 0:
            table = key.split(".", 1)[0]
            raise DistributorFullRepointAbortError(
                f"dim_distributor loser {loser_id} still referenced by {remaining} row(s) in {key} after repoint",
                loser_id=int(loser_id),
                table=table,
                remaining=remaining,
            )


def _require_repoint_rowcount(*, expected: int, actual: int, table: str, loser_id: int) -> None:
    if expected > 0 and actual != expected:
        raise DistributorFullRepointAbortError(
            f"repoint {table} for distributor loser {loser_id}: expected {expected} row(s) updated, got {actual}",
            loser_id=int(loser_id),
            table=table,
            remaining=expected,
        )


def _repoint_distributor_aliases_with_dedup(db: Session, *, keeper_id: int, loser_id: int) -> dict[str, int]:
    stats = {"updated": 0, "deleted_dup": 0}
    aliases = list(
        db.scalars(
            select(DistributorSourceTokenAlias).where(DistributorSourceTokenAlias.distributor_id == int(loser_id))
        ).all()
    )
    for al in aliases:
        dup = db.scalars(
            select(DistributorSourceTokenAlias)
            .where(
                DistributorSourceTokenAlias.distributor_id == int(keeper_id),
                DistributorSourceTokenAlias.normalized_token == al.normalized_token,
                DistributorSourceTokenAlias.raw_token == al.raw_token,
            )
            .limit(1)
        ).first()
        if dup is not None:
            db.delete(al)
            stats["deleted_dup"] += 1
        else:
            al.distributor_id = int(keeper_id)
            db.add(al)
            stats["updated"] += 1
    return stats


def _repoint_customer_aliases_distributor_scope(db: Session, *, keeper_id: int, loser_id: int) -> dict[str, int]:
    stats = {"updated": 0, "deleted_dup": 0}
    aliases = list(
        db.scalars(
            select(CustomerSourceTokenAlias).where(CustomerSourceTokenAlias.distributor_id == int(loser_id))
        ).all()
    )
    for al in aliases:
        dup = db.scalars(
            select(CustomerSourceTokenAlias)
            .where(
                CustomerSourceTokenAlias.distributor_id == int(keeper_id),
                CustomerSourceTokenAlias.customer_id == al.customer_id,
                CustomerSourceTokenAlias.normalized_token == al.normalized_token,
                CustomerSourceTokenAlias.raw_token == al.raw_token,
                func.coalesce(CustomerSourceTokenAlias.source_definition_id, -1)
                == func.coalesce(al.source_definition_id, -1),
            )
            .limit(1)
        ).first()
        if dup is not None:
            db.delete(al)
            stats["deleted_dup"] += 1
        else:
            al.distributor_id = int(keeper_id)
            db.add(al)
            stats["updated"] += 1
    return stats


def _repoint_unique_per_distributor_row(db: Session, *, table: str, keeper_id: int, loser_id: int) -> dict[str, int]:
    stats = {"updated": 0, "deleted_dup": 0}
    if table == "commercial_distributor_term":
        loser_row = db.scalar(
            select(CommercialDistributorTerm).where(CommercialDistributorTerm.distributor_id == int(loser_id))
        )
        if loser_row is None:
            return stats
        keeper_exists = db.scalar(
            select(CommercialDistributorTerm.id)
            .where(CommercialDistributorTerm.distributor_id == int(keeper_id))
            .limit(1)
        )
        if keeper_exists is not None:
            db.delete(loser_row)
            stats["deleted_dup"] += 1
        else:
            loser_row.distributor_id = int(keeper_id)
            db.add(loser_row)
            stats["updated"] += 1
    return stats


def _repoint_import_mapping_candidates(db: Session, *, keeper_id: int, loser_id: int) -> int:
    rows = list(
        db.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.suggested_entity_id == int(loser_id),
                ImportEntityMappingCandidate.entity_type.in_(_DISTRIBUTOR_MAPPING_ENTITY_TYPES),
            )
        ).all()
    )
    updated = 0
    for row in rows:
        row.suggested_entity_id = int(keeper_id)
        db.add(row)
        updated += 1
    return updated


def repoint_distributor_footprint_full(
    db: Session,
    *,
    loser_id: int,
    keeper_id: int,
    expected_counts: dict[str, int] | None = None,
    po_plans: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    kid, lid = int(keeper_id), int(loser_id)
    if kid == lid:
        raise DistributorFullRepointAbortError("keeper and loser must differ", loser_id=lid)

    stats: dict[str, Any] = {
        "table_updates": {},
        "alias_dedup": {},
        "customer_alias_distributor_scope": {},
        "mapping_candidates": 0,
        "po_actions": {},
    }

    try:
        stats["po_actions"] = execute_distributor_owned_po_actions(
            db,
            keeper_distributor_id=kid,
            loser_distributor_id=lid,
            po_plans=po_plans,
        )
    except DistributorPoConsolidationAbortError as exc:
        raise DistributorFullRepointAbortError(
            str(exc),
            loser_id=lid,
            table=exc.table,
            remaining=exc.remaining,
        ) from exc

    stats["alias_dedup"] = _repoint_distributor_aliases_with_dedup(db, keeper_id=kid, loser_id=lid)
    stats["customer_alias_distributor_scope"] = _repoint_customer_aliases_distributor_scope(
        db, keeper_id=kid, loser_id=lid
    )

    for table in _UNIQUE_PER_DISTRIBUTOR_TABLES:
        u = _repoint_unique_per_distributor_row(db, table=table, keeper_id=kid, loser_id=lid)
        if u["updated"] or u["deleted_dup"]:
            stats["table_updates"][table] = u

    stats["mapping_candidates"] = _repoint_import_mapping_candidates(db, keeper_id=kid, loser_id=lid)

    for table, column in discover_distributor_fk_columns(db):
        if table in _SKIP_BLIND_UPDATE or table in _UNIQUE_PER_DISTRIBUTOR_TABLES:
            continue
        key = f"{table}.{column}"
        expected = int((expected_counts or {}).get(key, -1))
        try:
            before = int(
                db.execute(text(f"SELECT count(*) FROM {table} WHERE {column} = :lid"), {"lid": lid}).scalar() or 0
            )
            if before == 0:
                continue
            r = db.execute(
                text(f"UPDATE {table} SET {column} = :kid WHERE {column} = :lid"),
                {"kid": kid, "lid": lid},
            )
            actual = int(r.rowcount or 0)
            rowcount_expected = (
                before if (table == "dim_distributor" and column == "merged_into_distributor_id") else expected
            )
            if rowcount_expected >= 0:
                _require_repoint_rowcount(expected=rowcount_expected, actual=actual, table=key, loser_id=lid)
            elif before > 0:
                _require_repoint_rowcount(expected=before, actual=actual, table=key, loser_id=lid)
            stats["table_updates"][key] = actual
        except ProgrammingError as exc:
            raise DistributorFullRepointAbortError(
                f"repoint failed for {key}: {exc}",
                loser_id=lid,
                table=table,
            ) from exc

    db.flush()
    _assert_zero_loser_refs(db, lid)
    return stats
