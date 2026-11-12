"""Apply 20261104_0057 on cip_test only. Stops unless current_database() is cip_test."""

from __future__ import annotations

import os
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[2]
os.environ["DATABASE_URL"] = "postgresql+asyncpg://cip:cip@localhost:5432/cip_test"
os.environ["DATABASE_URL_SYNC"] = "postgresql://cip:cip@localhost:5432/cip_test"
os.environ["DATABASE_URL_SYNC_MIGRATE"] = "postgresql://cip:cip@localhost:5432/cip_test"
sys.path.insert(0, str(API))

import psycopg

URL = os.environ["DATABASE_URL_SYNC"]


def main() -> None:
    with psycopg.connect(URL, autocommit=True) as conn:
        name = conn.execute("SELECT current_database()").fetchone()[0]
        user = conn.execute("SELECT current_user").fetchone()[0]
        print(f"current_database={name} current_user={user}", flush=True)
        if name != "cip_test":
            raise SystemExit(f"STOP: database is {name!r}, not cip_test")
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        print(f"alembic_version={version[0] if version else None}", flush=True)
        owner = conn.execute(
            """
            SELECT r.rolname
            FROM pg_proc p
            JOIN pg_roles r ON r.oid = p.proowner
            WHERE p.proname = 'cip_inbound_shipment_lineage'
            """
        ).fetchone()
        print(f"function_owner={owner[0] if owner else None}", flush=True)
        if version is None or version[0] != "20261103_0056":
            raise SystemExit(f"STOP: cip_test is not at 20261103_0056 (found {version})")

    from sqlalchemy.engine.url import make_url

    from app.core.config import get_settings
    from app.db.migrate_url_guard import resolve_alembic_migrate_url

    settings = get_settings()
    migrate_url = resolve_alembic_migrate_url(
        database_url_sync=settings.database_url_sync,
        database_url_sync_migrate=settings.database_url_sync_migrate,
    )
    migrate_db = make_url(migrate_url).database
    print(f"migrate_database={migrate_db}", flush=True)
    if migrate_db != "cip_test":
        raise SystemExit(f"STOP: migrate url database is {migrate_db!r}, not cip_test")

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(API / "alembic.ini"))
    cfg.set_main_option("script_location", str(API / "alembic"))
    command.upgrade(cfg, "20261104_0057")

    with psycopg.connect(URL, autocommit=True) as conn:
        name = conn.execute("SELECT current_database()").fetchone()[0]
        print(f"after current_database={name}", flush=True)
        if name != "cip_test":
            raise SystemExit(f"STOP: database is {name!r}, not cip_test")
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        body = conn.execute(
            "SELECT pg_get_functiondef('public.cip_inbound_shipment_lineage()'::regprocedure)"
        ).fetchone()[0]
        print(f"after alembic_version={version}", flush=True)
        print(f"lookup_installed={'o.evidence_line_id = ni.line_id' in body}", flush=True)
        if version != "20261104_0057" or "o.evidence_line_id = ni.line_id" not in body:
            raise SystemExit("STOP: cip_test upgrade did not install the lookup")


if __name__ == "__main__":
    main()
