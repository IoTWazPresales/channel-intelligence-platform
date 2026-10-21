"""Run the N-0101 round 3 cip_test snapshot tests with DATABASE_URL(_SYNC) pointed at cip_test.

Run from apps/api with its virtualenv (PYTHONPATH=.). Derives the cip_test URLs from
the configured settings in-process so no credential appears in shell text, and refuses
unless the swapped database name is exactly cip_test.
"""

from __future__ import annotations

import os
import sys

from app.core.config import get_settings


def _swap(url: str) -> str:
    base, _, tail = url.rpartition("/")
    query = "?" + tail.split("?", 1)[1] if "?" in tail else ""
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
    print("DATABASE_URL_SYNC db =", s2.database_url_sync.rsplit("/", 1)[1].split("?", 1)[0])

    from sqlalchemy import create_engine, text

    eng = create_engine(s2.database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1))
    with eng.connect() as c:
        print("current_database() =", c.execute(text("select current_database()")).scalar_one())
        print("listing_observation rows before =", c.execute(text("select count(*) from listing_observation")).scalar_one())
    import pytest

    rc = pytest.main(["-q", "-rs", "-p", "no:cacheprovider", "tests/test_listing_capture_snapshot_db.py", *sys.argv[1:]])
    with eng.connect() as c:
        print("listing_observation rows after =", c.execute(text("select count(*) from listing_observation")).scalar_one())
    eng.dispose()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
