"""Time brief and cover handlers only. Read-only. Stops unless cip.

One warmup pass per scope, then one measured pass. The pieces are not timed
separately, so the measured pass is the route itself.
"""

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

from app.api.v1.endpoints.channel_ops import channel_ops_cover_distribution  # noqa: E402
from app.services.brief_signals import build_brief_payload  # noqa: E402


async def once(name: str, read, edit, role: str | None) -> None:
    read_token = request_product_lines.set(read)
    edit_token = request_editable_product_lines.set(edit)
    role_token = request_role.set(role)
    try:
        async with AsyncSessionLocal() as db:
            dbname = (await db.execute(text("select current_database()"))).scalar()
            if dbname != "cip":
                raise SystemExit(f"STOP: database is {dbname!r}, not cip")
            shown = (await db.execute(text("select current_setting('cip.product_lines', true)"))).scalar()
            started = time.perf_counter()
            cover = await channel_ops_cover_distribution(db, None)
            cover_s = time.perf_counter() - started
            started = time.perf_counter()
            brief = await build_brief_payload(db, None)
            brief_s = time.perf_counter() - started
            print(
                f"{name} database={dbname} product_lines={shown!r} "
                f"cover={cover_s:.3f}s pairs={cover.get('pair_count')} "
                f"brief={brief_s:.3f}s signals={len(brief.get('signals') or [])}",
                flush=True,
            )
            await db.rollback()
    finally:
        request_product_lines.reset(read_token)
        request_editable_product_lines.reset(edit_token)
        request_role.reset(role_token)


async def main() -> None:
    scopes = [
        ("unset", None, None, None),
        ("star", ALL_PRODUCT_LINES, ALL_PRODUCT_LINES, "admin"),
        ("one_line", frozenset({"NB"}), frozenset(), None),
    ]
    for name, read, edit, role in scopes:
        await once(f"warmup-{name}", read, edit, role)
        await once(name, read, edit, role)


if __name__ == "__main__":
    asyncio.run(main())
