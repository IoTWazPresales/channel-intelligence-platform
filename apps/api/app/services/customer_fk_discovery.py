"""Discover FK columns referencing ``dim_customer.id`` from live ``pg_constraint`` metadata."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

# Extra surfaces not expressed as a single-column FK to dim_customer.id in pg_constraint.
_EXTRA_CUSTOMER_REFS: tuple[tuple[str, str, str], ...] = (
    (
        "import_entity_mapping_candidate",
        "suggested_entity_id",
        "entity_type IN ('customer_dealer_token', 'shipment_customer_token')",
    ),
)

# Self-referential soft redirect — repoint when other rows point at the loser.
_MERGED_INTO_REF: tuple[str, str] = ("dim_customer", "merged_into_customer_id")


def discover_customer_fk_columns(db: Session) -> tuple[tuple[str, str], ...]:
    """Return ``(table_name, column_name)`` for every FK to ``dim_customer.id``."""
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
                  AND ref.relname = 'dim_customer'
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

    # De-dupe while preserving order; skip dim_customer.id PK self-FK if present.
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for pair in discovered:
        if pair in seen:
            continue
        if pair[0] == "dim_customer" and pair[1] == "id":
            continue
        seen.add(pair)
        out.append(pair)
    if _MERGED_INTO_REF not in seen:
        out.append(_MERGED_INTO_REF)
    return tuple(out)


def extra_customer_ref_specs() -> tuple[tuple[str, str, str], ...]:
    return _EXTRA_CUSTOMER_REFS
