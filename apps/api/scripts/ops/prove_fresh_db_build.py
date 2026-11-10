#!/usr/bin/env python3
"""BACKLOG-214 proof: build an EMPTY database with ``alembic upgrade head``.

Creates a scratch database (default ``cip_fresh_build_proof``) on the local cluster with the owner
login (PG_OWNER / CIP_CLONE_ADMIN_URL, never printed), runs ``upgrade head`` as the owner, checks the
revision is the single head, then ``downgrade -1`` and ``upgrade head`` again, and drops the database
unless ``--keep``. Refuses ``cip`` and ``cip_test``; never connects to either.

  python scripts/ops/prove_fresh_db_build.py [--db NAME] [--keep]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from scripts.ops.prove_job_delete_restore_clone import alembic, swap_db  # noqa: E402
from scripts.ops.prove_on_the_water_clone import admin_url  # noqa: E402

REFUSED = {"cip", "cip_test", "postgres", "template0", "template1"}


def _sa(url: str) -> str:
    return url.replace("postgresql://", "postgresql+psycopg://", 1) if url.startswith("postgresql://") else url


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="cip_fresh_build_proof")
    p.add_argument("--keep", action="store_true")
    a = p.parse_args()
    if a.db in REFUSED:
        raise SystemExit(f"STOP: refusing {a.db}")
    s = get_settings()
    admin = admin_url(s)
    maint = create_engine(_sa(swap_db(admin, "postgres")), isolation_level="AUTOCOMMIT")
    with maint.connect() as c:
        print("maintenance current_database()", c.execute(text("select current_database()")).scalar())
        if c.execute(text("select 1 from pg_database where datname = :n"), {"n": a.db}).scalar():
            c.execute(text(f'DROP DATABASE "{a.db}" WITH (FORCE)'))
            print("dropped previous", a.db)
        c.execute(text(f'CREATE DATABASE "{a.db}"'))
        print("created", a.db)
    target = create_engine(_sa(swap_db(admin, a.db)))
    with target.connect() as c:
        name = c.execute(text("select current_database()")).scalar()
        print("current_database()", name)
        if name != a.db:
            raise SystemExit("STOP: wrong database")
        tables = c.execute(text("select count(*) from information_schema.tables where table_schema='public'")).scalar()
        print("public tables before", tables)
        if tables:
            raise SystemExit("STOP: scratch database is not empty")
    target.dispose()
    env = dict(
        os.environ,
        DATABASE_URL=swap_db(s.database_url, a.db),
        DATABASE_URL_SYNC=swap_db(s.database_url_sync, a.db),
        DATABASE_URL_SYNC_MIGRATE=swap_db(admin, a.db),
    )
    heads = alembic(env, "heads")
    print("heads:", heads)
    print("upgrade head:", alembic(env, "upgrade", "head"))
    current = alembic(env, "current")
    print("current:", current)
    print("downgrade -1:", alembic(env, "downgrade", "-1"))
    print("upgrade head again:", alembic(env, "upgrade", "head"))
    current2 = alembic(env, "current")
    print("current again:", current2)
    target = create_engine(_sa(swap_db(admin, a.db)))
    with target.connect() as c:
        ver = [r[0] for r in c.execute(text("select version_num from alembic_version"))]
        tables = c.execute(text("select count(*) from information_schema.tables where table_schema='public'")).scalar()
        print("alembic_version", ver, "public tables", tables)
    target.dispose()
    head = heads.split()[0] if heads else ""
    ok = ver == [head]
    if not a.keep:
        with maint.connect() as c:
            c.execute(text(f'DROP DATABASE "{a.db}" WITH (FORCE)'))
            print("dropped", a.db)
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
