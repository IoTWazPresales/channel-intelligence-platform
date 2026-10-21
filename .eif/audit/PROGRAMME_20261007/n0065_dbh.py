"""Read-only helper for N-0065 perf discovery. SELECT/EXPLAIN only, READ ONLY transactions."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "apps" / "api"))

import sqlalchemy as sa  # noqa: E402

from app.core.config import get_settings  # noqa: E402


def engine():
    url = get_settings().database_url_sync
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    from sqlalchemy.pool import NullPool

    return sa.create_engine(url, poolclass=NullPool)  # NullPool: a reused backend reads the gate as an empty string


def ro(conn, timeout="60s"):
    conn.execute(sa.text("SET TRANSACTION READ ONLY"))
    conn.execute(sa.text(f"SET LOCAL statement_timeout = '{timeout}'"))
    print("database:", conn.execute(sa.text("select current_database()")).scalar())
