"""Physical customer FK repoint with all-or-nothing zero-ref guard (full merge)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.models.commercial_planner import CommercialCustomerTerm
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer
from app.models.import_distributor_si import CustomerSourceTokenAlias, ImportEntityMappingCandidate
from app.services.customer_fk_discovery import discover_customer_fk_columns, extra_customer_ref_specs
from app.services.customer_usage import _CUSTOMER_MAPPING_ENTITY_TYPES

# Tables where repoint uses row-level dedup instead of blind UPDATE (unique per customer_id).
_UNIQUE_PER_CUSTOMER_TABLES = frozenset(
    {
        "commercial_customer_term",
        "customer_report_config",
    }
)


class CustomerFullRepointAbortError(RuntimeError):
    def __init__(self, message: str, *, loser_id: int, table: str | None = None, remaining: int = 0):
        self.loser_id = int(loser_id)
        self.table = table
        self.remaining = int(remaining)
        super().__init__(message)


def count_customer_fk_refs(db: Session, customer_id: int) -> dict[str, int]:
    """Count rows referencing ``customer_id`` per discovered FK column."""
    cid = int(customer_id)
    counts: dict[str, int] = {}
    for table, column in discover_customer_fk_columns(db):
        key = f"{table}.{column}"
        try:
            n = int(
                db.execute(
                    text(f"SELECT count(*) FROM {table} WHERE {column} = :cid"),
                    {"cid": cid},
                ).scalar()
                or 0
            )
        except ProgrammingError:
            n = 0
        if n:
            counts[key] = n

    for table, column, where_extra in extra_customer_ref_specs():
        key = f"{table}.{column}"
        try:
            n = int(
                db.execute(
                    text(
                        f"SELECT count(*) FROM {table} WHERE {column} = :cid AND ({where_extra})"
                    ),
                    {"cid": cid},
                ).scalar()
                or 0
            )
        except ProgrammingError:
            n = 0
        if n:
            counts[key] = n
    return counts


def _strict_loser_ref_counts(db: Session, loser_id: int) -> dict[str, int]:
    return count_customer_fk_refs(db, int(loser_id))


def _assert_zero_loser_refs(db: Session, loser_id: int) -> None:
    for key, remaining in _strict_loser_ref_counts(db, int(loser_id)).items():
        if remaining > 0:
            table = key.split(".", 1)[0]
            raise CustomerFullRepointAbortError(
                f"dim_customer loser {loser_id} still referenced by {remaining} row(s) in {key} after repoint",
                loser_id=int(loser_id),
                table=table,
                remaining=remaining,
            )


def _require_repoint_rowcount(*, expected: int, actual: int, table: str, loser_id: int) -> None:
    if expected > 0 and actual != expected:
        raise CustomerFullRepointAbortError(
            f"repoint {table} for customer loser {loser_id}: expected {expected} row(s) updated, got {actual}",
            loser_id=int(loser_id),
            table=table,
            remaining=expected,
        )


def _repoint_customer_aliases_with_dedup(db: Session, *, keeper_id: int, loser_id: int) -> dict[str, int]:
    stats = {"updated": 0, "deleted_dup": 0}
    aliases = list(
        db.scalars(select(CustomerSourceTokenAlias).where(CustomerSourceTokenAlias.customer_id == int(loser_id))).all()
    )
    for al in aliases:
        dup = db.scalars(
            select(CustomerSourceTokenAlias)
            .where(
                CustomerSourceTokenAlias.customer_id == int(keeper_id),
                CustomerSourceTokenAlias.normalized_token == al.normalized_token,
                CustomerSourceTokenAlias.raw_token == al.raw_token,
                func.coalesce(CustomerSourceTokenAlias.source_definition_id, -1)
                == func.coalesce(al.source_definition_id, -1),
                func.coalesce(CustomerSourceTokenAlias.distributor_id, -1)
                == func.coalesce(al.distributor_id, -1),
            )
            .limit(1)
        ).first()
        if dup is not None:
            db.delete(al)
            stats["deleted_dup"] += 1
        else:
            al.customer_id = int(keeper_id)
            db.add(al)
            stats["updated"] += 1
    return stats


def _repoint_unique_per_customer_row(db: Session, *, table: str, keeper_id: int, loser_id: int) -> dict[str, int]:
    """Repoint or delete when ``customer_id`` is unique on the table."""
    stats = {"updated": 0, "deleted_dup": 0}
    if table == "commercial_customer_term":
        loser_row = db.scalar(select(CommercialCustomerTerm).where(CommercialCustomerTerm.customer_id == int(loser_id)))
        if loser_row is None:
            return stats
        keeper_exists = db.scalar(
            select(CommercialCustomerTerm.id).where(CommercialCustomerTerm.customer_id == int(keeper_id)).limit(1)
        )
        if keeper_exists is not None:
            db.delete(loser_row)
            stats["deleted_dup"] += 1
        else:
            loser_row.customer_id = int(keeper_id)
            db.add(loser_row)
            stats["updated"] += 1
        return stats
    if table == "customer_report_config":
        loser_row = db.scalar(select(CustomerReportConfig).where(CustomerReportConfig.customer_id == int(loser_id)))
        if loser_row is None:
            return stats
        keeper_exists = db.scalar(
            select(CustomerReportConfig.id).where(CustomerReportConfig.customer_id == int(keeper_id)).limit(1)
        )
        if keeper_exists is not None:
            db.delete(loser_row)
            stats["deleted_dup"] += 1
        else:
            loser_row.customer_id = int(keeper_id)
            db.add(loser_row)
            stats["updated"] += 1
        return stats
    return stats


def _repoint_import_mapping_candidates(db: Session, *, keeper_id: int, loser_id: int) -> int:
    rows = list(
        db.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.suggested_entity_id == int(loser_id),
                ImportEntityMappingCandidate.entity_type.in_(_CUSTOMER_MAPPING_ENTITY_TYPES),
            )
        ).all()
    )
    updated = 0
    for row in rows:
        row.suggested_entity_id = int(keeper_id)
        db.add(row)
        updated += 1
    return updated


def repoint_customer_footprint_full(
    db: Session,
    *,
    loser_id: int,
    keeper_id: int,
    expected_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Repoint every discovered FK from loser → keeper; abort if any ref remains on loser."""
    kid, lid = int(keeper_id), int(loser_id)
    if kid == lid:
        raise CustomerFullRepointAbortError("keeper and loser must differ", loser_id=lid)

    stats: dict[str, Any] = {"table_updates": {}, "alias_dedup": {}, "mapping_candidates": 0}

    alias_stats = _repoint_customer_aliases_with_dedup(db, keeper_id=kid, loser_id=lid)
    stats["alias_dedup"] = alias_stats

    for table in _UNIQUE_PER_CUSTOMER_TABLES:
        u = _repoint_unique_per_customer_row(db, table=table, keeper_id=kid, loser_id=lid)
        if u["updated"] or u["deleted_dup"]:
            stats["table_updates"][table] = u

    mapping_updates = _repoint_import_mapping_candidates(db, keeper_id=kid, loser_id=lid)
    stats["mapping_candidates"] = mapping_updates

    for table, column in discover_customer_fk_columns(db):
        if table in _UNIQUE_PER_CUSTOMER_TABLES:
            continue
        if table == "customer_source_token_alias":
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
            # Tombstone chain flatten: verify against live before-count, not preview snapshot.
            rowcount_expected = before if (table == "dim_customer" and column == "merged_into_customer_id") else expected
            if rowcount_expected >= 0:
                _require_repoint_rowcount(expected=rowcount_expected, actual=actual, table=key, loser_id=lid)
            elif before > 0:
                _require_repoint_rowcount(expected=before, actual=actual, table=key, loser_id=lid)
            stats["table_updates"][key] = actual
        except ProgrammingError as exc:
            raise CustomerFullRepointAbortError(
                f"repoint failed for {key}: {exc}",
                loser_id=lid,
                table=table,
            ) from exc

    db.flush()
    _assert_zero_loser_refs(db, lid)
    return stats
