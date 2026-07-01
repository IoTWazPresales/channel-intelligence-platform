"""One-shot setup for cip_bulk_smoke (disposable clone). Not part of pytest collection."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

API_ROOT = Path(__file__).resolve().parents[1]
DB_NAME = "cip_bulk_smoke"
SYNC = f"postgresql+psycopg://cip:cip@127.0.0.1:5432/{DB_NAME}"


def _admin_url() -> str:
    try:
        from dotenv import load_dotenv

        load_dotenv(API_ROOT / ".env")
    except ImportError:
        pass
    migrate = os.environ.get("DATABASE_URL_SYNC_MIGRATE", "").strip()
    if migrate:
        url = migrate.replace("postgresql://", "postgresql+psycopg://", 1)
        if "/cip" in url:
            return url.rsplit("/", 1)[0] + "/postgres"
        return url
    return os.environ.get(
        "SMOKE_ADMIN_URL",
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres",
    )


def main() -> int:
    admin_url = _admin_url()
    print(f"admin url host/db for CREATE DATABASE: ...{admin_url.rsplit('@', 1)[-1]}")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :n AND pid <> pg_backend_pid()"
            ),
            {"n": DB_NAME},
        )
        c.execute(text(f"DROP DATABASE IF EXISTS {DB_NAME}"))
        c.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = 'cip' AND pid <> pg_backend_pid()"
            )
        )
        c.execute(text(f"CREATE DATABASE {DB_NAME} WITH TEMPLATE cip OWNER cip"))
        print(f"created {DB_NAME} from template cip")

    env = os.environ.copy()
    env["DATABASE_URL_SYNC"] = SYNC
    env["DATABASE_URL_SYNC_MIGRATE"] = SYNC
    env["DATABASE_URL"] = f"postgresql+asyncpg://cip:cip@127.0.0.1:5432/{DB_NAME}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        check=False,
    )
    if result.returncode != 0:
        return result.returncode

    with create_engine(SYNC).connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar_one()
        rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        bu = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='commercial_lineup_case' AND column_name='business_unit'"
            )
        ).first()
        sup = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='commercial_lineup_case' AND column_name='superseded_by_case_id'"
            )
        ).first()
        print(f"current_database()={db}")
        print(f"alembic={rev}")
        print(f"business_unit column={'yes' if bu else 'no'}")
        print(f"superseded_by_case_id column={'yes' if sup else 'no'}")
        assert db == DB_NAME
        assert rev == "20260701_0065"
        assert bu and sup
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
