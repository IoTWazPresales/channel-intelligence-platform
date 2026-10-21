"""Run the N-0068 cip_test DB tests with DATABASE_URL(_SYNC) pointed at cip_test.

Run from apps/api with its virtualenv. Derives the cip_test URLs from the configured
settings in-process so no credential appears in shell text, and refuses unless the
swapped database name is exactly cip_test. Same shape as N0065_run_db_tests.py.
"""

from __future__ import annotations

import os
import sys

from app.core.config import get_settings


def _swap(url: str) -> str:
    base, _, tail = url.rpartition("/")
    query = ""
    if "?" in tail:
        query = "?" + tail.split("?", 1)[1]
    return f"{base}/cip_test{query}"


def main() -> int:
    s = get_settings()
    a, b = _swap(s.database_url), _swap(s.database_url_sync)
    for u in (a, b):
        assert u.rsplit("/", 1)[1].split("?", 1)[0] == "cip_test"
    os.environ["DATABASE_URL"] = a
    os.environ["DATABASE_URL_SYNC"] = b
    get_settings.cache_clear()
    s2 = get_settings()
    print("DATABASE_URL db =", s2.database_url.rsplit("/", 1)[1].split("?", 1)[0])
    print("DATABASE_URL_SYNC db =", s2.database_url_sync.rsplit("/", 1)[1].split("?", 1)[0])

    from sqlalchemy import create_engine, text

    eng = create_engine(s2.database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1))
    with eng.connect() as c:
        print("current_database() =", c.execute(text("select current_database()")).scalar_one())
        row = c.execute(
            text("select rolname, rolsuper, rolbypassrls from pg_roles where rolname = current_user")
        ).one()
        print("role =", row.rolname, "super =", row.rolsuper, "bypassrls =", row.rolbypassrls)
        print("alembic_version =", c.execute(text("select version_num from alembic_version")).scalars().all())
    eng.dispose()

    import pytest

    return pytest.main(["-q", "-rs", "tests/test_column_grain_n0068_db.py", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
