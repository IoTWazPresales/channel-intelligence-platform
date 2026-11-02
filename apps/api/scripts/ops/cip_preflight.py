#!/usr/bin/env python3
"""Read-only preflight for a run against cip: resolved URLs (password hidden), current_database(), alembic head, running or queued work."""
from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402

s = get_settings()
for name, url in (("DATABASE_URL", s.database_url), ("DATABASE_URL_SYNC", s.database_url_sync)):
    u = make_url(url.replace("+psycopg", "").replace("+asyncpg", ""))
    print(f"{name}: host={u.host} port={u.port} database={u.database} user={u.username} password=***")
eng = create_engine(sqlalchemy_sync_engine_url(s.database_url_sync))
with eng.connect() as con:
    con.execute(text("SET TRANSACTION READ ONLY"))
    db = con.execute(text("select current_database()")).scalar()
    print("current_database() =", db, "| role =", con.execute(text("select current_user")).scalar())
    print("alembic version(s):", [r[0] for r in con.execute(text("select version_num from alembic_version"))])
    rows = con.execute(text("select status, stage, count(*) from import_job where status not in ('completed','failed','cancelled','archived') group by 1,2")).all()
    print("import jobs not finished (status, stage, n):", [tuple(r) for r in rows])
    print("import jobs touched in the last 30 minutes:", con.execute(text("select count(*) from import_job where updated_at > now() - interval '30 minutes'")).scalar())
    con.rollback()
try:
    import redis  # type: ignore

    r = redis.Redis.from_url(s.celery_broker_url if hasattr(s, "celery_broker_url") else s.redis_url)
    print("redis queue lengths:", {q: r.llen(q) for q in ("celery",)})
except Exception as e:  # noqa: BLE001
    print("redis check not available:", type(e).__name__, str(e)[:120])
try:
    from app.worker.celery_app import celery_app

    i = celery_app.control.inspect(timeout=6)
    print("celery active:", {k: len(v) for k, v in (i.active() or {}).items()}, "| reserved:", {k: len(v) for k, v in (i.reserved() or {}).items()})
except Exception as e:  # noqa: BLE001
    print("celery inspect failed:", type(e).__name__, str(e)[:120])
if db != "cip":
    print("STOP: the target is not cip")
    raise SystemExit(2)
