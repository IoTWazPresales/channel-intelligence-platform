"""Discover FK columns referencing ``dim_distributor.id`` from live ``pg_constraint`` metadata."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

_EXTRA_DISTRIBUTOR_REFS: tuple[tuple[str, str, str], ...] = (
    (
        "import_entity_mapping_candidate",
        "suggested_entity_id",
        "entity_type IN ('distributor_token', 'shipment_distributor')",
    ),
)

_MERGED_INTO_REF: tuple[str, str] = ("dim_distributor", "merged_into_distributor_id")


def discover_distributor_fk_columns(db: Session) -> tuple[tuple[str, str], ...]:
    """Return ``(table_name, column_name)`` for every FK to ``dim_distributor.id``."""
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
                  AND ref.relname = 'dim_distributor'
                  AND array_length(con.confkey, 1) = 1
                  AND (
                    SELECT attname FROM pg_attribute
                    WHERE attrelid = con.confrelid AND attnum = con.confkey[1]
                  ) = 'id'
                ORDER BY 1, 2
                """
            )
        ).all()
        discovered = tuple((str(r[0]), str(r[1])) for r in rows)
    except ProgrammingError:
        discovered = ()

    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for pair in discovered:
        if pair in seen:
            continue
        if pair[0] == "dim_distributor" and pair[1] == "id":
            continue
        seen.add(pair)
        out.append(pair)
    if _MERGED_INTO_REF not in seen:
        out.append(_MERGED_INTO_REF)
    return tuple(out)


def extra_distributor_ref_specs() -> tuple[tuple[str, str, str], ...]:
    return _EXTRA_DISTRIBUTOR_REFS
