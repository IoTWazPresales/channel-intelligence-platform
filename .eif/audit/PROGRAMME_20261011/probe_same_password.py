"""One local-dev login check. Prints booleans only."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)

from app.core.config import get_settings  # noqa: E402
from sqlalchemy.engine.url import make_url  # noqa: E402


def main() -> None:
    names = [name for name in os.environ if "MIGRATE" in name.upper() or name.upper() in {"PGPASSWORD", "PGUSER"}]
    print("env_names", ",".join(names))
    settings = get_settings()
    sync = make_url(settings.database_url_sync)
    print("migrate_url_set", bool((settings.database_url_sync_migrate or "").strip()))
    print("sync_user_is_cip", sync.username == "cip")
    url = sync.set(drivername="postgresql+psycopg", username="postgres", database="postgres")
    try:
        engine = create_engine(url.render_as_string(hide_password=False), connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            superuser = conn.execute(
                text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
            ).scalar()
        print("same_password_ok True")
        print("same_password_super", bool(superuser))
    except SQLAlchemyError as exc:
        message = str(getattr(exc, "orig", exc)).lower()
        print("same_password_ok False")
        print("same_password_auth_failed", "password authentication failed" in message)


if __name__ == "__main__":
    main()
