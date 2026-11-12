"""Read-only check that the lateral latest-row read matches DISTINCT ON on cip, then time the handlers.

Prints current_database() and stops unless it is cip. The transaction is READ ONLY.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\Users\warren_eliason\channel-intelligence-platform\.worktrees\n0108-cover-speed\apps\api")
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://cip:cip@localhost:5432/cip")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://cip:cip@localhost:5432/cip")

OUT = Path(__file__).with_name("n0108_compare_out.txt")

OLD = """
SELECT id, distributor_id, product_id
FROM (
    SELECT DISTINCT ON (distributor_id, product_id) *
    FROM weeks_of_cover_observation
    WHERE tenant_id = 'default'
    ORDER BY distributor_id, product_id, cover_as_of_date DESC,
             CASE WHEN trigger = 'as_of_backfill' THEN 1 ELSE 0 END ASC,
             observed_at DESC
) picked
ORDER BY distributor_id, product_id
"""


def _sync_url() -> str:
    return os.environ["DATABASE_URL_SYNC"]


def compare_sql() -> None:
    import psycopg
    from psycopg.rows import dict_row
    from sqlalchemy.dialects import postgresql

    from app.services.woc_observation_read import latest_woc_observation_stmt

    stmt = latest_woc_observation_stmt(tenant_id="default")
    new_sql = str(
        stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    )
    lines: list[str] = []

    def log(msg: str) -> None:
        print(msg, flush=True)
        lines.append(msg)

    with psycopg.connect(_sync_url(), autocommit=True, row_factory=dict_row) as conn:
        conn.execute("SET statement_timeout = '120s'")
        conn.autocommit = False
        conn.execute("SET TRANSACTION READ ONLY")
        db = conn.execute("SELECT current_database()").fetchone()["current_database"]
        log(f"current_database={db}")
        if db != "cip":
            raise SystemExit(f"STOP: database is {db!r}, not cip")
        scopes = [("unset", ""), ("star", "*"), ("one_line", "NB")]
        for name, setting in scopes:
            conn.execute("SELECT set_config('cip.product_lines', %s, true)", (setting,))
            shown = conn.execute("SELECT current_setting('cip.product_lines', true)").fetchone()
            log(f"--- scope={name} setting={shown['current_setting']!r} ---")
            started = time.perf_counter()
            old_rows = conn.execute(OLD).fetchall()
            old_s = time.perf_counter() - started
            started = time.perf_counter()
            new_rows = conn.execute(new_sql).fetchall()
            new_s = time.perf_counter() - started
            old_key = [(row["id"], row["distributor_id"], row["product_id"]) for row in old_rows]
            new_key = [(row["id"], row["distributor_id"], row["product_id"]) for row in new_rows]
            log(
                f"old_rows={len(old_key)} seconds={old_s:.3f} "
                f"new_rows={len(new_key)} seconds={new_s:.3f} equal={old_key == new_key}"
            )
            if old_key != new_key:
                old_set = set(old_key)
                new_set = set(new_key)
                log(f"only_old={len(old_set - new_set)} only_new={len(new_set - old_set)}")
        conn.rollback()
        log("rollback=ok")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def time_handlers() -> None:
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

    from app.api.v1.endpoints.channel_ops import channel_ops_cover_distribution
    from app.services.brief_signals import build_brief_payload

    lines: list[str] = []

    def log(msg: str) -> None:
        print(msg, flush=True)
        lines.append(msg)

    scopes = [
        ("unset", None, None),
        ("star", ALL_PRODUCT_LINES, ALL_PRODUCT_LINES),
        ("one_line", frozenset({"NB"}), frozenset()),
    ]
    for name, read, edit in scopes:
        read_token = request_product_lines.set(read)
        edit_token = request_editable_product_lines.set(edit)
        role_token = request_role.set("admin" if name == "star" else None)
        try:
            async with AsyncSessionLocal() as db:
                dbname = (await db.execute(text("select current_database()"))).scalar()
                if dbname != "cip":
                    raise SystemExit(f"STOP: database is {dbname!r}, not cip")
                shown = (await db.execute(text("select current_setting('cip.product_lines', true)"))).scalar()
                log(f"handler scope={name} database={dbname} product_lines={shown!r}")
                started = time.perf_counter()
                brief = await build_brief_payload(db, None)
                brief_s = time.perf_counter() - started
                started = time.perf_counter()
                cover = await channel_ops_cover_distribution(db, None)
                cover_s = time.perf_counter() - started
                await db.rollback()
                log(
                    f"brief_seconds={brief_s:.3f} signals={len(brief.get('signals') or [])} "
                    f"cover_seconds={cover_s:.3f} pairs={cover.get('pair_count')}"
                )
        finally:
            request_product_lines.reset(read_token)
            request_editable_product_lines.reset(edit_token)
            request_role.reset(role_token)
    previous = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    OUT.write_text(previous + "\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    compare_sql()
    asyncio.run(time_handlers())


if __name__ == "__main__":
    main()
