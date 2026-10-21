"""Confirm product-line row security on cip. Prints counts only."""

from __future__ import annotations

import os
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[3] / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)

from sqlalchemy import text

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from sqlalchemy import create_engine

settings = get_settings()
engine = create_engine(sqlalchemy_sync_engine_url(settings.database_url_sync))
with engine.connect() as conn:
    who = conn.execute(text("SELECT current_database(), current_user")).one()
    print(f"database={who[0]} user={who[1]}")
    if who[0] != "cip":
        raise SystemExit("refusing non-cip database")
    open_count = conn.execute(text("SELECT count(*) FROM dim_product")).scalar()
    conn.execute(text("SELECT set_config('cip.product_lines', '', true)"))
    none_count = conn.execute(text("SELECT count(*) FROM dim_product")).scalar()
    conn.execute(text("SELECT set_config('cip.product_lines', '*', true)"))
    star_count = conn.execute(text("SELECT count(*) FROM dim_product")).scalar()
    grain = conn.execute(text("SELECT count(*) FROM tenant_column_grain")).scalar()
    grants = conn.execute(text("SELECT count(*) FROM user_product_line_access")).scalar()
print(f"open={open_count} none={none_count} star={star_count} grain_rows={grain} grants={grants}")
