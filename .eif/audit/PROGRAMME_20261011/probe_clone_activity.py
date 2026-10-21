"""Active queries on the clone. No connection strings."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

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
from sqlalchemy.engine.url import make_url  # noqa: E402

settings = get_settings()
sync = make_url(settings.database_url_sync)
admin, source = module.resolve_admin(settings, sync)
engine = create_engine(admin.set(database="postgres").render_as_string(hide_password=False))
with engine.connect() as conn:
    rows = conn.execute(
        text(
            """
            SELECT datname, state, wait_event_type, left(query, 80)
            FROM pg_stat_activity
            WHERE datname IN ('cip', 'cip_n0079')
              AND pid <> pg_backend_pid()
            """
        )
    ).all()
print(f"admin_source {source}")
print(f"sessions {len(rows)}")
for datname, state, wait, query in rows:
    print(f"{datname} {state} {wait} {query}")
