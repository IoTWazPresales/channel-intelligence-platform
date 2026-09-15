"""Read-only failure-type recon against cip. SELECT only; never commit."""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[3] / "apps" / "api"
sys.path.insert(0, str(ROOT))

from app.db.session_sync import SessionLocal  # noqa: E402


def main() -> int:
    db = SessionLocal()
    try:
        dbname = db.execute(text("SELECT current_database()")).scalar()
        print(f"current_database()={dbname!r}")
        if str(dbname) != "cip":
            print("STOP: refusing to run against any database other than cip")
            return 2
        db.rollback()
        db.execute(text("SET TRANSACTION READ ONLY"))

        print("--- entity_type x status (all jobs) ---")
        rows = db.execute(
            text(
                "SELECT c.entity_type, c.status, count(1) AS n, "
                "count(DISTINCT c.import_job_id) AS jobs "
                "FROM import_entity_mapping_candidate c "
                "GROUP BY 1, 2 ORDER BY 1, 2"
            )
        ).all()
        for r in rows:
            print(tuple(r))

        print("--- needs_review by entity_type x job.status x template ---")
        rows = db.execute(
            text(
                "SELECT c.entity_type, j.status, j.template_slug, count(1) AS n, "
                "count(DISTINCT c.import_job_id) AS jobs "
                "FROM import_entity_mapping_candidate c "
                "JOIN import_job j ON j.id = c.import_job_id "
                "WHERE c.status = 'needs_review' "
                "GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"
            )
        ).all()
        for r in rows:
            print(tuple(r))

        print("--- import_job status (unarchived) ---")
        for r in db.execute(
            text(
                "SELECT status, count(1) FROM import_job "
                "WHERE archived_at IS NULL GROUP BY 1 ORDER BY 1"
            )
        ).all():
            print(tuple(r))

        print("--- entity_mapping_queue ---")
        for r in db.execute(
            text("SELECT status, count(1) FROM entity_mapping_queue GROUP BY 1 ORDER BY 1")
        ).all():
            print(tuple(r))

        print("--- shipment_evidence_current product_resolution_status ---")
        for r in db.execute(
            text(
                "SELECT product_resolution_status, count(1) "
                "FROM shipment_evidence_current GROUP BY 1 ORDER BY 1"
            )
        ).all():
            print(tuple(r))

        print("--- fact_inbound_shipment product_resolution_status ---")
        for r in db.execute(
            text(
                "SELECT product_resolution_status, count(1) "
                "FROM fact_inbound_shipment GROUP BY 1 ORDER BY 1"
            )
        ).all():
            print(tuple(r))

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
