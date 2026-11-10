#!/usr/bin/env python3
"""BACKLOG-214 proof: build an EMPTY database with ``alembic upgrade head``.

Creates a NEW scratch database on the local cluster with the owner login (PG_OWNER /
CIP_CLONE_ADMIN_URL, never printed), runs ``upgrade head`` as the owner, checks the revision is
the single head, then ``downgrade -1`` (or ``--deep-downgrade REV``) and ``upgrade head`` again.

Safety:
  * the name must match ``cip_fresh_build_[a-z0-9_]+`` (default: a unique timestamped name);
  * an EXISTING database is refused, never dropped;
  * only the database created by this invocation is dropped (in ``finally``) unless ``--keep``;
  * never connects to ``cip`` or ``cip_test``.

  python scripts/ops/prove_fresh_db_build.py [--db NAME] [--deep-downgrade REV] [--keep]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from app.core.config import get_settings  # noqa: E402
from scripts.ops.prove_job_delete_restore_clone import alembic, swap_db  # noqa: E402
from scripts.ops.prove_on_the_water_clone import admin_url  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

PUBLIC_TABLES = "select count(*) from information_schema.tables where table_schema='public'"
NAME_RE = re.compile(r"^cip_fresh_build_[a-z0-9_]{1,40}$")


def _sa(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _default_name() -> str:
    return f"cip_fresh_build_{time.strftime('%Y%m%d%H%M%S')}_{os.getpid()}"


def check_name(name: str) -> str:
    if not NAME_RE.match(name):
        raise SystemExit(f"STOP: scratch name must match {NAME_RE.pattern}: {name!r}")
    return name


def _proof(s, admin: str, db: str, deep: str | None) -> bool:
    target = create_engine(_sa(swap_db(admin, db)))
    with target.connect() as c:
        name = c.execute(text("select current_database()")).scalar()
        print("current_database()", name)
        if name != db:
            raise SystemExit("STOP: wrong database")
        tables = c.execute(text(PUBLIC_TABLES)).scalar()
        print("public tables before", tables)
        if tables:
            raise SystemExit("STOP: scratch database is not empty")
    target.dispose()
    env = dict(
        os.environ,
        DATABASE_URL=swap_db(s.database_url, db),
        DATABASE_URL_SYNC=swap_db(s.database_url_sync, db),
        DATABASE_URL_SYNC_MIGRATE=swap_db(admin, db),
    )
    heads = alembic(env, "heads")
    print("heads:", heads)
    print("upgrade head:", alembic(env, "upgrade", "head"))
    print("current:", alembic(env, "current"))
    step = deep or "-1"
    print(f"downgrade {step}:", alembic(env, "downgrade", step))
    print("current after downgrade:", alembic(env, "current"))
    print("upgrade head again:", alembic(env, "upgrade", "head"))
    print("current again:", alembic(env, "current"))
    target = create_engine(_sa(swap_db(admin, db)))
    with target.connect() as c:
        ver = [r[0] for r in c.execute(text("select version_num from alembic_version"))]
        tables = c.execute(text(PUBLIC_TABLES)).scalar()
        print("alembic_version", ver, "public tables", tables)
    target.dispose()
    head = heads.split()[0] if heads else ""
    return ver == [head]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=None, help="new cip_fresh_build_* name; must not exist")
    p.add_argument("--deep-downgrade", default=None, help="downgrade target, then re-upgrade")
    p.add_argument("--keep", action="store_true")
    a = p.parse_args()
    db = check_name(a.db or _default_name())
    s = get_settings()
    admin = admin_url(s)
    maint = create_engine(_sa(swap_db(admin, "postgres")), isolation_level="AUTOCOMMIT")
    created = False
    ok = False
    try:
        with maint.connect() as c:
            maint_name = c.execute(text("select current_database()")).scalar()
            print("maintenance current_database()", maint_name)
            if c.execute(text("select 1 from pg_database where datname = :n"), {"n": db}).scalar():
                raise SystemExit(f"STOP: {db} already exists; refusing to reuse or drop it")
            c.execute(text(f'CREATE DATABASE "{db}"'))
            created = True
            print("created", db)
        ok = _proof(s, admin, db, a.deep_downgrade)
    finally:
        if created and not a.keep:
            with maint.connect() as c:
                c.execute(text(f'DROP DATABASE "{db}" WITH (FORCE)'))
                print("dropped", db)
        elif created:
            print("kept", db)
        maint.dispose()
    print("RESULT", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
