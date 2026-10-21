"""N-0065 round 3: run alembic against cip_test ONLY. Run from apps/api with its venv.

    python <this> upgrade 20261006_0024 | upgrade 20261007_0025 | downgrade 20261006_0024 | current

Swaps DATABASE_URL(_SYNC) to cip_test in-process (no credential in shell text), refuses
when DATABASE_URL_SYNC_MIGRATE is set (it would decide the target), and prints
current_database() and the revision before and after.
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


def _swap(url: str) -> str:
    base, _, tail = url.rpartition("/")
    query = ("?" + tail.split("?", 1)[1]) if "?" in tail else ""
    return f"{base}/cip_test{query}"


def _state(label: str) -> None:
    s = get_settings()
    eng = create_engine(s.database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1), poolclass=NullPool)
    with eng.connect() as c:
        db = c.execute(text("select current_database()")).scalar_one()
        rev = c.execute(text("select version_num from alembic_version")).scalars().all()
        print(f"[{label}] current_database() = {db}  alembic = {rev}")
        assert db == "cip_test", db
        c.rollback()
    eng.dispose()


def main() -> int:
    action = sys.argv[1]
    s = get_settings()
    assert not (s.database_url_sync_migrate or "").strip(), "DATABASE_URL_SYNC_MIGRATE is set; refusing"
    os.environ["DATABASE_URL"] = _swap(s.database_url)
    os.environ["DATABASE_URL_SYNC"] = _swap(s.database_url_sync)
    os.environ.pop("DATABASE_URL_SYNC_MIGRATE", None)
    get_settings.cache_clear()
    s2 = get_settings()
    for u in (s2.database_url, s2.database_url_sync):
        assert u.rsplit("/", 1)[1].split("?", 1)[0] == "cip_test"
    _state("before")
    if action == "current":
        return 0
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    if action == "upgrade":
        command.upgrade(cfg, sys.argv[2])
    elif action == "downgrade":
        command.downgrade(cfg, sys.argv[2])
    else:
        raise SystemExit(f"unknown action {action}")
    _state("after")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
