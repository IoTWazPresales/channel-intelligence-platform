"""Login check for the registry owner. Booleans only."""
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

spec = importlib.util.spec_from_file_location(
    "prove_n0079",
    ROOT / ".eif" / "audit" / "PROGRAMME_20261011" / "prove_n0079_clone.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

from app.core.config import get_settings  # noqa: E402

settings = get_settings()
sync = make_url(settings.database_url_sync)
admin, source = module.resolve_admin(settings, sync)
print(f"admin_source {source}")
try:
    engine = create_engine(
        admin.set(database="postgres").render_as_string(hide_password=False),
        connect_args={"connect_timeout": 5},
    )
    with engine.connect() as conn:
        who = conn.execute(text("SELECT current_user")).scalar()
        superuser = conn.execute(
            text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        ).scalar()
    print("login_ok True")
    print(f"user_is_postgres {who == 'postgres'}")
    print(f"superuser {bool(superuser)}")
except SQLAlchemyError as exc:
    message = str(getattr(exc, "orig", exc)).lower()
    print("login_ok False")
    print(f"auth_failed {'password authentication failed' in message}")
