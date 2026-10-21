"""Read-only: import jobs that look like they are running (so a worker restart does not cut one off)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.getcwd())

from sqlalchemy import text

from app.db.session_sync import SessionLocal

with SessionLocal() as s:
    print("current_database()=" + s.execute(text("select current_database()")).scalar())
    rows = s.execute(
        text(
            "select id, template_slug, status, stage, updated_at from import_job "
            "where status in ('running','processing','queued','pending') or stage in ('applying','validating','parsing') "
            "order by updated_at desc limit 15"
        )
    ).all()
    print(f"active-looking jobs: {len(rows)}")
    for r in rows:
        print(f"  job {r.id} {r.template_slug} status={r.status} stage={r.stage} updated={r.updated_at}")
