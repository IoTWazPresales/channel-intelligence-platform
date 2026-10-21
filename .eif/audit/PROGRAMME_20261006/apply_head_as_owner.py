"""Apply Alembic head as the database owner.

The owner password is read from PG_OWNER. This script prints only the database
name, the role, and the revision. It refuses any database other than cip.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote, urlparse

API = Path(__file__).resolve().parents[3] / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)

owner_pw = os.environ.get("PG_OWNER") or ""
if not owner_pw:
    raise SystemExit("PG_OWNER is not set")

from app.core.config import get_settings  # noqa: E402

settings = get_settings()
parsed = urlparse(settings.database_url_sync)
db_name = (parsed.path or "").lstrip("/").split("?")[0]
if db_name != "cip":
    raise SystemExit(f"refusing database {db_name}")

host = parsed.hostname or "localhost"
port = parsed.port or 5432
owner_url = f"postgresql+psycopg://postgres:{quote(owner_pw, safe='')}@{host}:{port}/cip"

from sqlalchemy import create_engine, text  # noqa: E402

engine = create_engine(owner_url)
with engine.connect() as conn:
    row = conn.execute(text("SELECT current_database(), current_user")).one()
print(f"database={row[0]} user={row[1]}")
if row[0] != "cip" or row[1] != "postgres":
    raise SystemExit("identity check failed")

os.environ["DATABASE_URL_SYNC"] = owner_url
os.environ["DATABASE_URL_SYNC_MIGRATE"] = owner_url
os.environ.pop("CIP_SMOKE_MIGRATE", None)
get_settings.cache_clear()

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

cfg = Config(str(API / "alembic.ini"))
cfg.set_main_option("script_location", str(API / "alembic"))
command.upgrade(cfg, "head")

with engine.connect() as conn:
    rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
print(f"alembic={rev}")
