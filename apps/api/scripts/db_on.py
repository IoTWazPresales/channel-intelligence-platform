"""Run pytest on cip_test, or read-only SQL on a named non-cip database, without printing credentials.

  python scripts/db_on.py pytest [pytest args...]          full API suite on cip_test
  python scripts/db_on.py sql --db cip_n0115 --file q.sql  read-only SQL on a clone (never cip)
  python scripts/db_on.py sql --db cip_n0115 -c "select 1"

The SQL mode opens a READ ONLY transaction and refuses the database name ``cip``. The app's own
connection settings (env or apps/api/.env) supply host, user and password; only the database
name is swapped. Output never echoes the connection string.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))


def _swap_db(url: str, db: str) -> str:
    return re.sub(r"/[A-Za-z0-9_]+(\?|$)", rf"/{db}\1", url, count=1) if "/" in url.split("@", 1)[-1] else url


def _settings():
    from app.core.config import get_settings

    return get_settings()


def run_pytest(args: list[str]) -> int:
    s = _settings()
    env = dict(os.environ)
    env["DATABASE_URL"] = _swap_db(s.database_url, "cip_test")
    env["DATABASE_URL_SYNC"] = _swap_db(s.database_url_sync, "cip_test")
    for key in ("DATABASE_URL", "DATABASE_URL_SYNC"):
        if not env[key].split("?")[0].endswith("/cip_test"):
            print(f"ABORT: {key} would not point at cip_test", file=sys.stderr)
            return 2
    print("pytest on cip_test")
    cmd = [sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider", *args]
    return subprocess.call(cmd, cwd=str(API_DIR), env=env)


def run_sql(db: str, sql: str, *, timing: bool) -> int:
    if db.strip().lower() == "cip":
        print("ABORT: refusing to run on cip; use a pg_dump clone", file=sys.stderr)
        return 2
    from sqlalchemy import create_engine, text  # noqa: PLC0415

    from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: PLC0415

    engine = create_engine(sqlalchemy_sync_engine_url(_swap_db(_settings().database_url_sync, db)))
    try:
        with engine.connect() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            for stmt in [p.strip() for p in sql.split(";") if p.strip()]:
                t0 = time.perf_counter()
                res = conn.execute(text(stmt))
                rows = res.fetchall() if res.returns_rows else None
                ms = (time.perf_counter() - t0) * 1000
                if rows is not None:
                    print("\t".join(res.keys()))
                    for row in rows:
                        print("\t".join("" if v is None else str(v) for v in row))
                if timing:
                    print(f"-- {ms:.1f} ms")
            conn.rollback()
    finally:
        engine.dispose()
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="mode", required=True)
    sub.add_parser("pytest", add_help=False)
    q = sub.add_parser("sql")
    q.add_argument("--db", required=True)
    q.add_argument("--file")
    q.add_argument("-c", "--command")
    q.add_argument("--timing", action="store_true")
    args, rest = p.parse_known_args()
    if args.mode == "pytest":
        return run_pytest(rest)
    sql = Path(args.file).read_text(encoding="utf-8") if args.file else (args.command or "")
    return run_sql(args.db, sql, timing=args.timing)


if __name__ == "__main__":
    raise SystemExit(main())
