"""Print job 642 column_samples from cip_test inferred_schema."""
from __future__ import annotations

import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402
from session_e_cip_test_walk import q, rewrite_dbname  # noqa: E402


def main() -> int:
    sync = get_settings().database_url_sync
    target = sqlalchemy_sync_engine_url(rewrite_dbname(sync, "cip_test"))
    engine = create_engine(target)
    with Session(engine) as session:
        q(session, "SELECT current_database()", "db")
        rows = session.execute(
            text(
                """
                SELECT id,
                       inferred_schema->'selected_sheet_details'->0->'column_samples' AS column_samples
                FROM import_job
                WHERE id = 642
                """
            )
        ).all()
        print("JOB_642_COLUMN_SAMPLES", json.dumps(rows[0][1] if rows else None, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
