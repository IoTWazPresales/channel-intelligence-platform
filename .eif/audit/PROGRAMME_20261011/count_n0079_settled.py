"""Count settled lines on the clone. Booleans and counts only."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402

settings = get_settings()
sync = make_url(settings.database_url_sync)
engine = create_engine(
    sqlalchemy_sync_engine_url(sync.set(database="cip_n0079").render_as_string(hide_password=False))
)
with engine.connect() as conn:
    dbname = conn.execute(text("SELECT current_database()")).scalar()
    revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    settled_lines = conn.execute(
        text(
            """
            SELECT count(*)
            FROM cpor_case_line l
            JOIN cpor_case c ON c.id = l.case_id
            WHERE c.status = 'settled'
            """
        )
    ).scalar()
    with_result = conn.execute(
        text(
            """
            SELECT count(*)
            FROM cpor_case_line l
            JOIN cpor_case c ON c.id = l.case_id
            WHERE c.status = 'settled' AND l.ttl_result_usd IS NOT NULL
            """
        )
    ).scalar()
    ledger = conn.execute(text("SELECT count(*) FROM budget_ledger_entry")).scalar()
print(f"clone_db_ok {dbname == 'cip_n0079'}")
print(f"revision {revision}")
print(f"settled_lines {settled_lines}")
print(f"settled_with_result {with_result}")
print(f"ledger_rows {ledger}")
