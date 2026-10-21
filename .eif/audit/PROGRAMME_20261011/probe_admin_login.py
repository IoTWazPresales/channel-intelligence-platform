"""Booleans only: why the admin connection failed, and what role cip can do."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)

from app.core.config import get_settings  # noqa: E402
from app.db.session_sync import SessionLocal  # noqa: E402


def ops_admin_url() -> str:
    path = API / "scripts" / "ops" / "prove_open_channel_absorb_clone.py"
    spec = importlib.util.spec_from_file_location("n0079_ops_admin", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return str(module._admin_url())


def main() -> None:
    print("pgpass_appdata", Path(os.environ.get("APPDATA", ""), "postgresql", "pgpass.conf").is_file())
    print("pgpass_home", Path.home().joinpath(".pgpass").is_file())
    print("smoke_admin_url_env", bool((os.environ.get("SMOKE_ADMIN_URL") or "").strip()))
    print("smoke_admin_password_env", bool((os.environ.get("SMOKE_ADMIN_PASSWORD") or "").strip()))
    settings = get_settings()
    sync = make_url(settings.database_url_sync)
    admin = make_url(ops_admin_url())
    print("admin_host_is_loopback", admin.host in {"127.0.0.1", "localhost"})
    print("admin_db", admin.database)
    print("admin_user_is_postgres", admin.username == "postgres")
    try:
        engine = create_engine(
            admin.set(database="postgres").render_as_string(hide_password=False),
            connect_args={"connect_timeout": 5},
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("admin_postgres_db_ok True")
    except SQLAlchemyError as exc:
        orig = getattr(exc, "orig", None)
        message = str(orig or exc).lower()
        for secret in (admin.password, sync.password):
            if secret:
                message = message.replace(str(secret).lower(), "")
        print("admin_postgres_db_ok False")
        print("admin_sqlstate", getattr(orig, "sqlstate", None))
        print("admin_error_type", type(orig).__name__ if orig is not None else type(exc).__name__)
        print("auth_failed", "password authentication failed" in message)
        print("conn_refused", "refused" in message)
        print("conn_timeout", "timeout" in message)
        print("hba_rejected", "pg_hba" in message)
    with SessionLocal() as session:
        print("db_is_cip", session.execute(text("SELECT current_database()")).scalar() == "cip")
        print(
            "cip_can_create_schema_public",
            bool(session.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")).scalar()),
        )
        print(
            "cip_createdb",
            bool(
                session.execute(
                    text("SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user")
                ).scalar()
            ),
        )
        print("cip_user", session.execute(text("SELECT current_user")).scalar() == "cip")
        roles = session.execute(
            text(
                """
                SELECT rolname, rolsuper, rolcreatedb
                FROM pg_roles
                WHERE rolsuper OR rolcreatedb
                ORDER BY rolname
                """
            )
        ).all()
        for name, is_super, can_create in roles:
            print(f"role {name} super {bool(is_super)} createdb {bool(can_create)}")


if __name__ == "__main__":
    main()
