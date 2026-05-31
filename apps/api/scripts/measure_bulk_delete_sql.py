#!/usr/bin/env python3
"""Measure SQL statement count for customer bulk-delete preview (real session, no mocks).

Usage (from apps/api with venv active):
  ALLOW_TESTS_ON_DEV_DB=1 python scripts/measure_bulk_delete_sql.py
  ALLOW_TESTS_ON_DEV_DB=1 python scripts/measure_bulk_delete_sql.py --ids 1,2,3,4,5,6
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[1]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from sqlalchemy import text

from app.db.session import AsyncSessionLocal, engine
from app.services.db_sql_counter import sql_counter_scope
from app.services.master_entity_bulk_delete import preview_master_bulk_delete


async def main() -> int:
    parser = argparse.ArgumentParser(description="Count SQL statements for bulk-delete preview")
    parser.add_argument("--ids", default="", help="Comma-separated customer ids (default: first 6 in DB)")
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        db_name = (await db.execute(text("SELECT current_database()"))).scalar_one()
        print(f"database: {db_name}")

    if args.ids.strip():
        entity_ids = [int(x.strip()) for x in args.ids.split(",") if x.strip()]
    else:
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(text("SELECT id FROM dim_customer ORDER BY id LIMIT 6"))).all()
        entity_ids = [int(r[0]) for r in rows]

    if not entity_ids:
        print("No customer ids to preview.")
        return 1

    print(f"preview entity_ids: {entity_ids}")

    with sql_counter_scope(engine) as counter:
        t0 = time.perf_counter()
        async with AsyncSessionLocal() as db:
            payload = await preview_master_bulk_delete(db, "customers", entity_ids)
        elapsed = time.perf_counter() - t0

    print(f"elapsed_s: {elapsed:.3f}")
    print(f"sql_statement_count: {counter.count}")
    for i, stmt in enumerate(counter.statements, 1):
        print(f"  sql_{i}: {stmt}")
    print(f"deletable_count: {payload.get('deletable_count')}")
    print(f"blocked_count: {payload.get('blocked_count')}")

    if counter.count != 2:
        print("FAIL: expected exactly 2 SQL statements (1 UNION ALL + 1 label batch)", file=sys.stderr)
        return 2
    if "UNION ALL" not in counter.statements[0].upper() and "fact_" not in counter.statements[0].lower():
        print("WARN: first statement may not be the UNION ALL reference check", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
