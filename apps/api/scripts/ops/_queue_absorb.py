"""Read-only: absorb evidence and whether distributor ids survived."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "apps" / "api"))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402


def main() -> int:
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar()
        print("current_database()", db)
        if db != "cip":
            return 2
        note = conn.execute(text("SELECT notes_summary FROM dim_customer WHERE id = 1")).scalar()
        print("oc_notes", (note or "")[-400:])
        print("audit")
        rows = conn.execute(
            text(
                "SELECT id, created_at, action, entity_token, target_id "
                "FROM steward_audit_event "
                "WHERE action ILIKE '%absorb%' OR action ILIKE '%open_channel%' "
                "OR target_id IN (1152, 4145, 12, 51) "
                "ORDER BY id DESC LIMIT 30"
            )
        ).fetchall()
        for row in rows:
            print(" ", row[0], row[1], row[2], row[3], row[4])
        for sql, label in (
            ("SELECT count(*) FROM fact_sales_sellout WHERE distributor_id IN (12, 51)", "sellout_dist"),
            ("SELECT count(*) FROM fact_sales_sellout WHERE customer_id IN (1152, 4145)", "sellout_old_cust"),
            ("SELECT count(*) FROM fact_sales_sellout WHERE customer_id = 1 AND distributor_id IN (12, 51)", "sellout_oc_and_dist"),
            ("SELECT distributor_id, count(*) FROM fact_sales_sellout WHERE distributor_id IN (12, 51) GROUP BY 1", "sellout_by_dist"),
        ):
            try:
                result = conn.execute(text(sql)).fetchall()
                print(label, [tuple(r) for r in result])
            except Exception as exc:  # noqa: BLE001
                print(label, type(exc).__name__)
                conn.rollback()
        sizes = conn.execute(
            text(
                "SELECT datname, pg_size_pretty(pg_database_size(datname)) "
                "FROM pg_database WHERE datname IN ('cip_queue_s6', 'cip') ORDER BY 1"
            )
        ).fetchall()
        for item in sizes:
            print("size", item[0], item[1])
        conn.rollback()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
