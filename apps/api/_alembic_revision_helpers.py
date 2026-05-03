"""Small introspection helpers for idempotent Alembic revisions.

The initial revision (20260412_0001) builds schema from SQLAlchemy ``create_all`` against
the *current* ORM. Later revisions that were authored when the ORM was smaller may repeat
DDL (add_column / create_table / indexes / FKs) that ``create_all`` already applied.
These helpers let those revisions no-op safely on fresh databases while remaining
applicable to older databases that only ran the historical migration path.

Used only from Alembic migration scripts — not imported by the FastAPI app.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Inspector


def get_inspector(bind: Connection) -> Inspector:
    return sa.inspect(bind)


def has_table(insp: Inspector, table_name: str, schema: str | None = None) -> bool:
    return insp.has_table(table_name, schema=schema)


def has_column(insp: Inspector, table_name: str, column_name: str, schema: str | None = None) -> bool:
    cols = insp.get_columns(table_name, schema=schema)
    return any(c.get("name") == column_name for c in cols)


def has_index(insp: Inspector, table_name: str, index_name: str, schema: str | None = None) -> bool:
    for ix in insp.get_indexes(table_name, schema=schema):
        if ix.get("name") == index_name:
            return True
    return False


def fk_exists(insp: Inspector, table_name: str, fk_name: str, schema: str | None = None) -> bool:
    for fk in insp.get_foreign_keys(table_name, schema=schema):
        if fk.get("name") == fk_name:
            return True
    return False


def unique_constraint_exists(
    insp: Inspector, table_name: str, constraint_name: str, schema: str | None = None
) -> bool:
    for uq in insp.get_unique_constraints(table_name, schema=schema):
        if uq.get("name") == constraint_name:
            return True
    return False


def get_column_type_name(insp: Inspector, table_name: str, column_name: str, schema: str | None = None) -> str | None:
    for c in insp.get_columns(table_name, schema=schema):
        if c.get("name") == column_name:
            t: Any = c.get("type")
            return str(t) if t is not None else None
    return None
