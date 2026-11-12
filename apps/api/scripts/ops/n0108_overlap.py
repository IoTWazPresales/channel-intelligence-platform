"""Time the three cover reads together. Read-only. Stops unless cip."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

API = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://cip:cip@localhost:5432/cip")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://cip:cip@localhost:5432/cip")

from sqlalchemy import event, text

from app.db.parallel_reads import gather_reads
from app.db.session import AsyncSessionLocal, engine
from app.db.session_sync import sync_engine


def _read_only(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("SET default_transaction_read_only = on")
    cursor.close()


event.listen(engine.sync_engine, "connect", _read_only)
event.listen(sync_engine, "connect", _read_only)

from app.api.v1.endpoints.channel_ops import (  # noqa: E402
    _cover_weekly_flow,
    _open_inbound_by_pair,
    channel_ops_cover_distribution,
)
from app.services.woc_observation_read import latest_woc_observations  # noqa: E402


def stamp(label: str, started: float) -> None:
    print(f"  {label} {time.perf_counter() - started:.3f}s", flush=True)


async def timed(name, fn):
    async def wrapped(db):
        t0 = time.perf_counter()
        print(f"start {name}", flush=True)
        value = await fn(db)
        print(f"end {name} {time.perf_counter() - t0:.3f}s", flush=True)
        return value

    return wrapped


async def main() -> None:
    async with AsyncSessionLocal() as db:
        name = (await db.execute(text("select current_database()"))).scalar()
        print(f"current_database={name}", flush=True)
        if name != "cip":
            raise SystemExit(f"STOP: database is {name!r}, not cip")
        readers = [
            await timed("woc", lambda s: latest_woc_observations(s, tenant_id="default")),
            await timed("inbound", lambda s: _open_inbound_by_pair(s, "default")),
            await timed("weekly", lambda s: _cover_weekly_flow(s, "default")),
        ]
        t0 = time.perf_counter()
        await gather_reads(db, *readers)
        stamp("gather", t0)
        t0 = time.perf_counter()
        cover = await channel_ops_cover_distribution(db, None)
        stamp(f"handler pairs={cover.get('pair_count')}", t0)
        await db.rollback()


if __name__ == "__main__":
    asyncio.run(main())
