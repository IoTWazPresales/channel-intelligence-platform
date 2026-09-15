"""Read-only cip figures for GOV-008. Prints current_database() first. No writes."""
from __future__ import annotations

import sys
from pathlib import Path

API = Path(__file__).resolve().parents[3] / "apps" / "api"
sys.path.insert(0, str(API))

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url

QUERIES = [
    (
        "failed_unarchived",
        """
        SELECT count(*) FROM import_job
        WHERE status = 'failed' AND archived_at IS NULL
        """,
    ),
    (
        "failed_last_7d",
        """
        SELECT count(*) FROM import_job
        WHERE status = 'failed' AND archived_at IS NULL
          AND coalesce(completed_at, updated_at, created_at) >= (now() AT TIME ZONE 'utc') - interval '7 days'
        """,
    ),
    (
        "candidates_needs_review",
        """
        SELECT count(*) FROM import_entity_mapping_candidate
        WHERE status = 'needs_review'
        """,
    ),
    (
        "candidates_by_entity_type",
        """
        SELECT c.entity_type, count(*) AS n
        FROM import_entity_mapping_candidate c
        JOIN import_job j ON j.id = c.import_job_id
        WHERE c.status = 'needs_review'
        GROUP BY c.entity_type
        ORDER BY n DESC, c.entity_type
        """,
    ),
    (
        "lineup_plan_items",
        """
        SELECT count(*) AS lines,
               coalesce(sum(planned_volume_units),0) AS planned_units
        FROM fact_lineup_plan_item
        """,
    ),
    (
        "computer_mania_id",
        """
        SELECT id, code, name FROM dim_customer
        WHERE code = 'CUST-000011' OR name ILIKE 'Computer Mania'
        ORDER BY id
        LIMIT 10
        """,
    ),
    (
        "cpor_case_status",
        """
        SELECT status, count(*) FROM cpor_case
        GROUP BY status
        ORDER BY count(*) DESC
        """,
    ),
]


def main() -> None:
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as c:
        db = c.execute(text("SELECT current_database()")).scalar()
        print("current_database()", db)
        if db != "cip":
            raise SystemExit("refusing: not cip")
        for name, sql in QUERIES:
            print("---", name)
            try:
                rows = c.execute(text(sql)).fetchall()
                for r in rows:
                    print(tuple(r))
            except Exception as exc:
                print("ERR", type(exc).__name__, str(exc).split("\n")[0][:240])


if __name__ == "__main__":
    main()
