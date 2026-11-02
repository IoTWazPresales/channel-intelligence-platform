"""Shared READ-ONLY helper for the 2 Nov overnight investigations (no writes of any kind).

Usage in a query script (run from the repo root, no cd):
    apps/api/.venv/Scripts/python.exe .eif/audit/OVERNIGHT_20261102/queries/<script>.py

    from ro import run_ro                      # the script sits in this folder, so `import ro` works
    async def work(db): ...                    # db is an AsyncSession already set READ ONLY
    run_ro(work)

Safety (the same proof as the 2 Nov review scripts):
  * SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY, then SET TRANSACTION READ ONLY, before any read
  * a write attempt (CREATE TEMP TABLE) must be refused (ReadOnlySqlTransaction) or the script aborts
  * default_transaction_read_only and transaction_read_only are printed as 'on'
  * the transaction is rolled back at the end; nothing is committed
  * the connection comes from the application settings (role cip); PG_OWNER is never used or printed
"""
from __future__ import annotations

import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path

API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402

TENANT = "default"


def jsonable(x):
    if isinstance(x, Decimal):
        return float(x)
    if hasattr(x, "isoformat"):
        return x.isoformat()
    return x


async def _prove_read_only(db) -> dict:
    await db.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"))
    await db.execute(text("SET TRANSACTION READ ONLY"))
    proof = {"database": (await db.execute(text("select current_database()"))).scalar_one()}
    assert proof["database"] == "cip", proof["database"]
    try:
        async with db.begin_nested():
            await db.execute(text("CREATE TEMP TABLE _ro_probe (i int)"))
        raise SystemExit("the connection is not read-only; aborting")
    except DBAPIError as exc:
        proof["write_probe"] = "refused: " + (type(exc.orig).__name__ if exc.orig is not None else "?")
    assert proof["write_probe"].startswith("refused")
    proof["default_transaction_read_only"] = (await db.execute(text("show default_transaction_read_only"))).scalar_one()
    proof["transaction_read_only"] = (await db.execute(text("show transaction_read_only"))).scalar_one()
    assert proof["transaction_read_only"] == "on"
    return proof


async def _main(work):
    async with AsyncSessionLocal() as db:
        proof = await _prove_read_only(db)
        print("READ-ONLY PROOF", json.dumps(proof), file=sys.stderr)
        try:
            return await work(db)
        finally:
            await db.rollback()


def run_ro(work):
    return asyncio.run(_main(work))


async def q(db, sql: str, **params):
    """Run one SELECT; returns a list of dict rows."""
    res = await db.execute(text(sql), params)
    keys = list(res.keys())
    return [{k: jsonable(v) for k, v in zip(keys, row)} for row in res.fetchall()]
