"""Public-schema metadata only: no application rows, scans or ORM transactions."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from time import monotonic
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

CACHE_SECONDS = 60

TABLES_SQL = """
SELECT c.oid AS table_oid, c.relname AS name, c.reltuples::double precision AS approx_rows
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'p')
  AND c.relname <> 'alembic_version'
ORDER BY c.relname
"""

COLUMNS_SQL = """
SELECT
    c.oid AS table_oid,
    a.attname AS name,
    pg_catalog.format_type(a.atttypid, a.atttypmod) AS type,
    NOT (a.attnotnull OR t.typnotnull) AS nullable,
    EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint AS pk
        WHERE pk.conrelid = c.oid
          AND pk.contype = 'p'
          AND a.attnum = ANY(pk.conkey)
    ) AS pk,
    EXISTS (
        SELECT 1
        FROM pg_catalog.pg_constraint AS fk
        WHERE fk.conrelid = c.oid
          AND fk.contype = 'f'
          AND a.attnum = ANY(fk.conkey)
    ) AS fk
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
JOIN pg_catalog.pg_attribute AS a ON a.attrelid = c.oid
JOIN pg_catalog.pg_type AS t ON t.oid = a.atttypid
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'p')
  AND c.relname <> 'alembic_version'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY c.relname, a.attnum
"""

FOREIGN_KEYS_SQL = """
SELECT
    fk.oid::text || ':' || pair.ordinality::text AS id,
    fk.conname AS name,
    source.oid AS from_oid,
    source_column.attname AS from_column,
    target.oid AS to_oid,
    target_column.attname AS to_column,
    pair.ordinality AS ordinal
FROM pg_catalog.pg_constraint AS fk
JOIN pg_catalog.pg_class AS source ON source.oid = fk.conrelid
JOIN pg_catalog.pg_namespace AS source_schema ON source_schema.oid = source.relnamespace
JOIN pg_catalog.pg_class AS target ON target.oid = fk.confrelid
JOIN pg_catalog.pg_namespace AS target_schema ON target_schema.oid = target.relnamespace
CROSS JOIN LATERAL unnest(fk.conkey, fk.confkey)
    WITH ORDINALITY AS pair(from_attnum, to_attnum, ordinality)
JOIN pg_catalog.pg_attribute AS source_column
    ON source_column.attrelid = source.oid AND source_column.attnum = pair.from_attnum
JOIN pg_catalog.pg_attribute AS target_column
    ON target_column.attrelid = target.oid AND target_column.attnum = pair.to_attnum
WHERE fk.contype = 'f'
  AND source_schema.nspname = 'public'
  AND target_schema.nspname = 'public'
  AND source.relkind IN ('r', 'p')
  AND target.relkind IN ('r', 'p')
  AND source.relname <> 'alembic_version'
  AND target.relname <> 'alembic_version'
ORDER BY source.relname, fk.conname, pair.ordinality
"""


class DatabaseColumn(BaseModel):
    name: str
    type: str
    nullable: bool
    pk: bool
    fk: bool


class DatabaseTable(BaseModel):
    id: str
    name: str
    approx_rows: int | None
    columns: list[DatabaseColumn]


class DatabaseForeignKey(BaseModel):
    id: str
    name: str
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    ordinal: int


class DatabaseMap(BaseModel):
    schema_name: Literal["public"] = "public"
    row_count_kind: Literal["approx rows"] = "approx rows"
    generated_at: datetime
    tables: list[DatabaseTable]
    foreign_keys: list[DatabaseForeignKey]


@asynccontextmanager
async def readonly_catalog_connection(
    engine: AsyncEngine,
) -> AsyncIterator[AsyncConnection]:
    """Use a fresh connection; authentication may already have queried its ORM session."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            await connection.execute(text("SET LOCAL statement_timeout = '5s'"))
            yield connection
        finally:
            await transaction.rollback()


async def load_database_map(connection: AsyncConnection) -> DatabaseMap:
    table_rows = (await connection.execute(text(TABLES_SQL))).mappings().all()
    tables: dict[int, DatabaseTable] = {}
    for row in table_rows:
        estimate = float(row["approx_rows"])
        tables[int(row["table_oid"])] = DatabaseTable(
            id=f"public.{row['name']}",
            name=row["name"],
            approx_rows=round(estimate) if estimate >= 0 else None,
            columns=[],
        )

    column_rows = (await connection.execute(text(COLUMNS_SQL))).mappings().all()
    for row in column_rows:
        table = tables.get(int(row["table_oid"]))
        if table is not None:
            table.columns.append(
                DatabaseColumn(
                    name=row["name"],
                    type=row["type"],
                    nullable=row["nullable"],
                    pk=row["pk"],
                    fk=row["fk"],
                )
            )

    relationships: list[DatabaseForeignKey] = []
    fk_rows = (await connection.execute(text(FOREIGN_KEYS_SQL))).mappings().all()
    for row in fk_rows:
        source = tables.get(int(row["from_oid"]))
        target = tables.get(int(row["to_oid"]))
        if source is not None and target is not None:
            relationships.append(
                DatabaseForeignKey(
                    id=row["id"],
                    name=row["name"],
                    from_table=source.id,
                    from_column=row["from_column"],
                    to_table=target.id,
                    to_column=row["to_column"],
                    ordinal=int(row["ordinal"]),
                )
            )

    return DatabaseMap(
        generated_at=datetime.now(UTC),
        tables=list(tables.values()),
        foreign_keys=relationships,
    )


class DatabaseMapReader:
    """One short-lived cache per configured database reader, shared across admin requests."""

    def __init__(self, engine: AsyncEngine, *, ttl_seconds: float = CACHE_SECONDS) -> None:
        self.engine = engine
        self.ttl_seconds = ttl_seconds
        self._payload: DatabaseMap | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def read(self) -> DatabaseMap:
        if self._payload is not None and monotonic() < self._expires_at:
            return self._payload
        async with self._lock:
            if self._payload is not None and monotonic() < self._expires_at:
                return self._payload
            async with readonly_catalog_connection(self.engine) as connection:
                payload = await load_database_map(connection)
            self._payload = payload
            self._expires_at = monotonic() + self.ttl_seconds
            return payload
