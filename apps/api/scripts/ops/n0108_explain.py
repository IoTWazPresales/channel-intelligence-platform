"""Read-only EXPLAIN of the one-line brief/cover queries that are still slow. cip only."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://cip:cip@localhost:5432/cip")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://cip:cip@localhost:5432/cip")

from sqlalchemy import event, text
from sqlalchemy.dialects import postgresql

from app.core.product_line_scope import request_editable_product_lines, request_product_lines
from app.db.session import AsyncSessionLocal, engine
from app.db.session_sync import sync_engine


def _read_only(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("SET default_transaction_read_only = on")
    cursor.close()


event.listen(engine.sync_engine, "connect", _read_only)
event.listen(sync_engine, "connect", _read_only)

from app.api.v1.endpoints.channel_ops import _cover_weekly_flow, _open_inbound_by_pair  # noqa: E402
from app.models.facts import FactInboundShipment, FactSalesSellout  # noqa: E402
from app.services.brief_signals import inbound_not_received_count_stmt  # noqa: E402
from app.services.imports.shipment_open_book import exclude_closed_inbound  # noqa: E402
from app.services.shipping_commercial_kpis import predicate_needs_look  # noqa: E402
from app.core.my_accounts import apply_account_predicate  # noqa: E402
from sqlalchemy import func, select  # noqa: E402


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


async def _explain(db, label: str, stmt) -> None:
    sql = "EXPLAIN (ANALYZE, BUFFERS) " + _sql(stmt)
    print(f"--- {label} ---", flush=True)
    try:
        rows = (await db.execute(text(sql))).all()
    except Exception as exc:
        print(f"EXPLAIN failed: {type(exc).__name__}: {exc}", flush=True)
        await db.rollback()
        return
    for row in rows:
        line = row[0]
        if any(
            token in line
            for token in (
                "Execution Time",
                "Planning Time",
                "Nested Loop",
                "Seq Scan",
                "Index",
                "Sort",
                "Hash",
                "Window",
                "CTE",
                "actual time",
            )
        ):
            print(line, flush=True)


async def main() -> None:
    request_product_lines.set(frozenset({"NB"}))
    request_editable_product_lines.set(frozenset())
    async with AsyncSessionLocal() as db:
        dbname = (await db.execute(text("select current_database()"))).scalar()
        print(f"current_database={dbname}", flush=True)
        if dbname != "cip":
            raise SystemExit(f"STOP: database is {dbname!r}, not cip")
        shown = (await db.execute(text("select current_setting('cip.product_lines', true)"))).scalar()
        print(f"product_lines={shown!r}", flush=True)
        await _explain(db, "inbound_count", inbound_not_received_count_stmt(None))
        indexes = (
            await db.execute(
                text(
                    """
                    SELECT tablename, indexname
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND tablename IN ('fact_inbound_shipment', 'fact_sales_sellout')
                    ORDER BY tablename, indexname
                    """
                )
            )
        ).all()
        print("indexes:", flush=True)
        for table, name in indexes:
            print(f"  {table} {name}", flush=True)
        await db.rollback()


if __name__ == "__main__":
    asyncio.run(main())
