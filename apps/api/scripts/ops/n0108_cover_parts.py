"""One pass through the cover handler pieces under product line NB. Read-only, cip only."""

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

from sqlalchemy import event, select, text

from app.core.product_line_scope import request_editable_product_lines, request_product_lines
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
from app.models.dimensions import DimDistributor, DimProduct  # noqa: E402
from app.services.woc_observation_read import latest_woc_observations  # noqa: E402


from app.services.brief_signals import build_brief_payload  # noqa: E402


async def lap(label, awaitable):
    started = time.perf_counter()
    value = await awaitable
    elapsed = time.perf_counter() - started
    print(f"{label} {elapsed:.3f}s", flush=True)
    return value, elapsed


async def one_scope(name: str, lines: frozenset[str] | None) -> None:
    print(f"=== {name} ===", flush=True)
    token = request_product_lines.set(lines)
    edit = request_editable_product_lines.set(frozenset() if lines is not None else None)
    try:
        async with AsyncSessionLocal() as db:
            dbname = (await db.execute(text("select current_database()"))).scalar()
            if dbname != "cip":
                raise SystemExit(f"STOP: database is {dbname!r}, not cip")
            shown = (await db.execute(text("select current_setting('cip.product_lines', true)"))).scalar()
            print(f"current_database={dbname} product_lines={shown!r}", flush=True)
            cover, cover_s = await lap("cover", channel_ops_cover_distribution(db, None))
            brief, brief_s = await lap("brief", build_brief_payload(db, None))
            print(
                f"result cover_pairs={cover.get('pair_count')} cover_s={cover_s:.3f} "
                f"brief_signals={len(brief.get('signals') or [])} brief_s={brief_s:.3f}",
                flush=True,
            )
            await db.rollback()
    finally:
        request_product_lines.reset(token)
        request_editable_product_lines.reset(edit)


async def main() -> None:
    await one_scope("PD", frozenset({"PD"}))
    await one_scope("PF", frozenset({"PF"}))
    await one_scope("NB", frozenset({"NB"}))


if __name__ == "__main__":
    asyncio.run(main())
