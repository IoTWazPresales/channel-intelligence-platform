"""Apply 20261010_0029 as postgres. Prints database, role, and revision only."""

from __future__ import annotations

import os
import sys
import winreg
from pathlib import Path
from urllib.parse import quote, urlparse

REPO = Path(__file__).resolve().parents[3]
API = REPO / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)

with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
    owner_pw, _ = winreg.QueryValueEx(key, "PG_OWNER")
if not owner_pw:
    raise SystemExit("PG_OWNER is empty")

from app.core.config import get_settings  # noqa: E402

settings = get_settings()
parsed = urlparse(settings.database_url_sync)
db_name = (parsed.path or "").lstrip("/").split("?")[0]
if db_name != "cip":
    raise SystemExit("refusing non-cip database")

host = parsed.hostname or "localhost"
port = parsed.port or 5432
owner_url = f"postgresql+psycopg://postgres:{quote(owner_pw, safe='')}@{host}:{port}/cip"
del owner_pw

from sqlalchemy import create_engine, text  # noqa: E402

engine = create_engine(owner_url)
with engine.connect() as conn:
    row = conn.execute(text("SELECT current_database(), current_user")).one()
    before = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
print(f"database={row[0]} user={row[1]} before={before}")
if row[0] != "cip" or row[1] != "postgres":
    raise SystemExit("identity check failed")
if before != "20261010_0028":
    raise SystemExit(f"expected 20261010_0028 found {before}")

os.environ["DATABASE_URL_SYNC"] = owner_url
os.environ["DATABASE_URL_SYNC_MIGRATE"] = owner_url
os.environ.pop("CIP_SMOKE_MIGRATE", None)
get_settings.cache_clear()

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

cfg = Config(str(API / "alembic.ini"))
cfg.set_main_option("script_location", str(API / "alembic"))
try:
    command.upgrade(cfg, "20261010_0029")
except Exception as exc:
    text_exc = str(exc)
    safe = "redacted" if "://" in text_exc or "password" in text_exc.lower() else text_exc[:400]
    print(f"error_type={type(exc).__name__} detail={safe}")
    raise SystemExit(1) from None

with engine.connect() as conn:
    rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    exists = conn.execute(text("SELECT to_regclass('public.overview_report_pin')")).scalar()
print(f"alembic={rev} table={exists}")
