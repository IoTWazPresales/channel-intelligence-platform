"""Prove empty-DB Alembic replay: upgrade head without stamp.

Creates disposable DB ``cip_alembic_empty`` (drops if exists), runs
``alembic upgrade head``, asserts tip + ``fact_demand_forecast`` + OPEN_CHANNEL.

Never touches ``cip``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url

SMOKE_DB = "cip_alembic_empty"
API_ROOT = Path(__file__).resolve().parents[2]


def _admin_url() -> str:
    settings = get_settings()
    url = sqlalchemy_sync_engine_url(
        settings.database_url_sync_migrate or settings.database_url_sync
    )
    # Point at postgres maintenance DB for CREATE/DROP DATABASE
    if url.rstrip("/").endswith("/cip") or "/cip?" in url:
        return url.replace("/cip", "/postgres")
    # Fallback: replace final path segment
    from urllib.parse import urlparse, urlunparse

    p = urlparse(url)
    return urlunparse(p._replace(path="/postgres"))


def main() -> None:
    admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": SMOKE_DB}
        ).scalar()
        if exists:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :n AND pid <> pg_backend_pid()"
                ),
                {"n": SMOKE_DB},
            )
            conn.execute(text(f'DROP DATABASE "{SMOKE_DB}"'))
        conn.execute(text(f'CREATE DATABASE "{SMOKE_DB}"'))
        print(f"created empty database {SMOKE_DB}")

    settings = get_settings()
    base = settings.database_url_sync_migrate or settings.database_url_sync
    smoke_sync = base.replace("/cip", f"/{SMOKE_DB}").replace(
        "cip?", f"{SMOKE_DB}?"
    )
    # Prefer precise replace of db name at end
    if "/cip" in base:
        smoke_sync = base.rsplit("/cip", 1)[0] + f"/{SMOKE_DB}"
    env = os.environ.copy()
    env["DATABASE_URL_SYNC"] = smoke_sync
    env["DATABASE_URL_SYNC_MIGRATE"] = smoke_sync
    # async URL if present
    if settings.database_url and "/cip" in settings.database_url:
        env["DATABASE_URL"] = settings.database_url.rsplit("/cip", 1)[0] + f"/{SMOKE_DB}"

    print("DATABASE_URL_SYNC=", smoke_sync)
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(API_ROOT),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    print(proc.stdout)
    print(proc.stderr)
    if proc.returncode != 0:
        raise SystemExit(f"alembic upgrade head failed: {proc.returncode}")

    eng = create_engine(sqlalchemy_sync_engine_url(smoke_sync))
    with eng.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar()
        tip = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        has_table = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name='fact_demand_forecast'"
            )
        ).scalar()
        has_view = conn.execute(
            text(
                "SELECT 1 FROM information_schema.views "
                "WHERE table_schema='public' AND table_name='shipment_evidence_current'"
            )
        ).scalar()
        oc = conn.execute(
            text("SELECT 1 FROM dim_customer WHERE code = 'OPEN_CHANNEL'")
        ).scalar()
        print(f"db={db} tip={tip} fact_demand_forecast={has_table} view={has_view} OPEN_CHANNEL={oc}")
        assert db == SMOKE_DB, db
        assert tip == "20260801_0001", tip
        assert has_table
        assert has_view
        assert oc
    print("EMPTY_DB_REPLAY_OK")


if __name__ == "__main__":
    main()
