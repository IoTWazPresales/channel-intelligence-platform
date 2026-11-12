"""Read-only step timings for brief and cover. Stops unless current_database() is cip."""

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

from app.core.product_line_scope import (
    ALL_PRODUCT_LINES,
    request_editable_product_lines,
    request_product_lines,
    request_role,
)
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
from app.core.tenant_scope import tenant_id_from_user  # noqa: E402
from app.services.brief_signals import (  # noqa: E402
    _cover_summary,
    _cst_late_missing_counts,
    _dsi_freshness,
    _needs_look_summary,
    _sell_through_attention,
    _settlement_aggregates,
    build_brief_payload,
    inbound_not_received_count_stmt,
)
from app.services.woc_observation_read import latest_woc_observations  # noqa: E402


async def _lap(label: str, awaitable) -> None:
    started = time.perf_counter()
    result = await awaitable
    print(f"  {label} {time.perf_counter() - started:.3f}s", flush=True)
    return result


async def profile(name: str, read, edit) -> None:
    print(f"=== {name} ===", flush=True)
    read_token = request_product_lines.set(read)
    edit_token = request_editable_product_lines.set(edit)
    role_token = request_role.set("admin" if name == "star" else None)
    try:
        async with AsyncSessionLocal() as db:
            dbname = (await db.execute(text("select current_database()"))).scalar()
            if dbname != "cip":
                raise SystemExit(f"STOP: database is {dbname!r}, not cip")
            shown = (await db.execute(text("select current_setting('cip.product_lines', true)"))).scalar()
            print(f"current_database={dbname} product_lines={shown!r}", flush=True)
            tid = tenant_id_from_user(None)
            await _lap("woc", latest_woc_observations(db, tenant_id=tid))
            await _lap("inbound_pairs", _open_inbound_by_pair(db, tid))
            await _lap("weekly_flow", _cover_weekly_flow(db, tid))
            started = time.perf_counter()
            cover = await channel_ops_cover_distribution(db, None)
            print(
                f"  cover_handler {time.perf_counter() - started:.3f}s pairs={cover.get('pair_count')}",
                flush=True,
            )
            await _lap("dsi", _dsi_freshness(db, None))
            await _lap("cover_summary", _cover_summary(db, None))
            await _lap("settlement", _settlement_aggregates(db, None))
            await _lap("inbound_count", db.scalar(inbound_not_received_count_stmt(None)))
            await _lap("cst", _cst_late_missing_counts(db))
            await _lap("needs_look", _needs_look_summary(db, None))
            await _lap("sell_through", _sell_through_attention(None))
            started = time.perf_counter()
            brief = await build_brief_payload(db, None)
            print(
                f"  brief_handler {time.perf_counter() - started:.3f}s signals={len(brief.get('signals') or [])}",
                flush=True,
            )
            await db.rollback()
    finally:
        request_product_lines.reset(read_token)
        request_editable_product_lines.reset(edit_token)
        request_role.reset(role_token)


async def main() -> None:
    # Warm once, then record the second pass. The first pass pays for a cold cache.
    await profile("warmup-unset", None, None)
    await profile("unset", None, None)
    await profile("star", ALL_PRODUCT_LINES, ALL_PRODUCT_LINES)
    await profile("one_line", frozenset({"NB"}), frozenset())


if __name__ == "__main__":
    asyncio.run(main())
