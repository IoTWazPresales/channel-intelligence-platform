"""EXPLAIN ANALYZE the brief and cover fact reads. Read-only. Stops unless cip."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

API = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://cip:cip@localhost:5432/cip")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://cip:cip@localhost:5432/cip")

from sqlalchemy import event, func, select, text
from sqlalchemy.dialects import postgresql

from app.core.product_line_scope import request_editable_product_lines, request_product_lines
from app.db.session import AsyncSessionLocal, engine
from app.db.session_sync import sync_engine
from app.models.facts import FactInboundShipment, FactSalesSellout
from app.services.shipment_strict_pair import twin_remainder


def _read_only(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("SET default_transaction_read_only = on")
    cursor.close()


event.listen(engine.sync_engine, "connect", _read_only)
event.listen(sync_engine, "connect", _read_only)

OUT = Path(__file__).with_name("n0108_explain_facts_out.txt")


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def _walk(plan: dict, found: list[dict]) -> None:
    found.append(plan)
    for child in plan.get("Plans") or []:
        _walk(child, found)


def _summary(payload: list) -> str:
    plan = payload[0]["Plan"]
    nodes: list[dict] = []
    _walk(plan, nodes)
    nodes.sort(key=lambda n: n.get("Actual Total Time") or 0, reverse=True)
    lines = [
        f"execution_ms={payload[0].get('Execution Time')} planning_ms={payload[0].get('Planning Time')}"
    ]
    for node in nodes[:8]:
        lines.append(
            "  {typ} actual={ms:.1f}ms rows={rows} loops={loops}".format(
                typ=node.get("Node Type"),
                ms=node.get("Actual Total Time") or 0,
                rows=node.get("Actual Rows"),
                loops=node.get("Actual Loops"),
            )
        )
    return "\n".join(lines)


async def _explain(db, label: str, stmt, lines: list[str]) -> None:
    sql = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + _sql(stmt)
    started = time.perf_counter()
    raw = (await db.execute(text(sql))).scalar()
    elapsed = time.perf_counter() - started
    payload = raw if isinstance(raw, list) else json.loads(raw)
    lines.append(f"--- {label} wall={elapsed:.3f}s ---")
    lines.append(_summary(payload))


def _weekly_stmts(tid: str, start, end):
    so_week = func.date_trunc("week", FactSalesSellout.transaction_date)
    in_date = func.coalesce(FactInboundShipment.ship_confirm_date, FactInboundShipment.pod_date)
    in_week = func.date_trunc("week", in_date)
    twin = twin_remainder(FactInboundShipment)
    return {
        "so_max": select(func.max(FactSalesSellout.transaction_date)).where(
            FactSalesSellout.tenant_id == tid
        ),
        "in_max": select(func.max(in_date)).where(FactInboundShipment.tenant_id == tid),
        "so_weeks": (
            select(so_week.label("wk"), func.coalesce(func.sum(FactSalesSellout.units), 0))
            .where(FactSalesSellout.tenant_id == tid)
            .where(FactSalesSellout.transaction_date >= start)
            .where(FactSalesSellout.transaction_date <= end)
            .group_by(so_week)
        ),
        "in_weeks": (
            select(in_week.label("wk"), func.coalesce(func.sum(twin.counted_quantity), 0))
            .select_from(FactInboundShipment)
            .outerjoin(twin.subquery, twin.onclause)
            .where(FactInboundShipment.tenant_id == tid)
            .where(in_date.is_not(None))
            .where(in_date >= start)
            .where(in_date <= end)
            .where(twin.kept)
            .group_by(in_week)
        ),
        "open_pairs": (
            select(
                FactInboundShipment.distributor_id,
                FactInboundShipment.product_id,
                func.coalesce(func.sum(twin.counted_quantity), 0),
            )
            .select_from(FactInboundShipment)
            .outerjoin(twin.subquery, twin.onclause)
            .where(FactInboundShipment.tenant_id == tid)
            .where(FactInboundShipment.pod_date.is_(None))
            .where(FactInboundShipment.distributor_id.is_not(None))
            .where(FactInboundShipment.product_id.is_not(None))
            .where(twin.kept)
            .group_by(FactInboundShipment.distributor_id, FactInboundShipment.product_id)
        ),
    }


async def main() -> None:
    lines: list[str] = []
    async with AsyncSessionLocal() as db:
        dbname = (await db.execute(text("select current_database()"))).scalar()
        lines.append(f"current_database={dbname}")
        if dbname != "cip":
            OUT.write_text("\n".join(lines), encoding="utf-8")
            raise SystemExit(f"STOP: database is {dbname!r}, not cip")
        sizes = (
            await db.execute(
                text(
                    """
                    SELECT c.relname, c.reltuples::bigint,
                           pg_size_pretty(pg_total_relation_size(c.oid))
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public'
                      AND c.relname IN ('fact_sales_sellout', 'fact_inbound_shipment',
                                        'weeks_of_cover_observation', 'dim_product')
                    ORDER BY c.relname
                    """
                )
            )
        ).all()
        for row in sizes:
            lines.append(f"size {row[0]} tuples={row[1]} {row[2]}")
        indexes = (
            await db.execute(
                text(
                    """
                    SELECT tablename, indexname, indexdef
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND tablename IN ('fact_sales_sellout', 'fact_inbound_shipment')
                    ORDER BY tablename, indexname
                    """
                )
            )
        ).all()
        for row in indexes:
            lines.append(f"index {row[0]}.{row[1]}: {row[2]}")
        await db.rollback()

    from datetime import date

    end = date(2026, 11, 4)
    start = end - timedelta(days=13 * 7)
    stmts = _weekly_stmts("default", start, end)
    scopes = [("unset", None), ("star", frozenset({"*"})), ("one_line", frozenset({"NB"}))]
    for name, scope in scopes:
        token = request_product_lines.set(scope)
        edit = request_editable_product_lines.set(frozenset() if scope is not None else None)
        try:
            async with AsyncSessionLocal() as db:
                shown = (await db.execute(text("select current_setting('cip.product_lines', true)"))).scalar()
                lines.append(f"=== {name} product_lines={shown!r} ===")
                for label, stmt in stmts.items():
                    await _explain(db, label, stmt, lines)
                await db.rollback()
        finally:
            request_product_lines.reset(token)
            request_editable_product_lines.reset(edit)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT.read_text(encoding="utf-8"), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
