"""Apply 20261012_0035 as the table owner. Prints database, role, and revision only."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.db.migrate_url_guard import resolve_alembic_migrate_url
from app.db.sync_url import sqlalchemy_sync_engine_url

ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "apps" / "api"


def main() -> int:
    owner_pw = os.environ.get("PG_OWNER") or ""
    if not owner_pw:
        print("OWNER_MISSING")
        return 2
    settings = get_settings()
    current = sqlalchemy_sync_engine_url(
        resolve_alembic_migrate_url(
            database_url_sync=settings.database_url_sync,
            database_url_sync_migrate=settings.database_url_sync_migrate,
        )
    )
    owner_url = make_url(current).set(username="postgres", password=owner_pw)
    env = os.environ.copy()
    env["DATABASE_URL_SYNC_MIGRATE"] = owner_url.render_as_string(hide_password=False)
    env.pop("CIP_SMOKE_MIGRATE", None)
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "20261012_0035"],
        cwd=API,
        env=env,
    )
    if proc.returncode != 0:
        return proc.returncode
    engine = create_engine(sqlalchemy_sync_engine_url(owner_url.render_as_string(hide_password=False)))
    with engine.connect() as conn:
        db, role = conn.execute(text("SELECT current_database(), current_user")).one()
        rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        exists = conn.execute(
            text("SELECT to_regclass('public.cpor_case_approval_link') IS NOT NULL")
        ).scalar()
    print(db)
    print(role)
    print(rev)
    print("table", bool(exists))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
