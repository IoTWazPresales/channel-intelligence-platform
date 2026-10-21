"""Read-only cip identity. Prints database, role, revision, and whether new objects exist."""

from __future__ import annotations

import os
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[3] / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url

engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
with engine.connect() as conn:
    who = conn.execute(text("SELECT current_database(), current_user")).one()
    if who[0] != "cip":
        raise SystemExit(f"refusing database {who[0]}")
    rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    access = conn.execute(text("SELECT to_regclass('public.user_product_line_access')")).scalar()
    grain = conn.execute(text("SELECT to_regclass('public.tenant_column_grain')")).scalar()
    window = conn.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'cpor_case_line' AND column_name = 'window_start'"
        )
    ).scalar()
print(f"database={who[0]} user={who[1]} alembic={rev} access={access} grain={grain} window_start={window}")
