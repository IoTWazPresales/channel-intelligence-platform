"""Read-only follow-up. One transaction per query. current_database first."""
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
        "cm_2026q2_lineup_lines",
        """
        SELECT count(*) AS lines, count(DISTINCT l.product_id) AS products
        FROM commercial_lineup_line l
        JOIN commercial_lineup_case c ON c.id = l.case_id
        WHERE l.customer_id = 18 AND c.period_label = '2026Q2'
          AND l.product_id IS NOT NULL
        """,
    ),
    (
        "cm_2026q2_lineup_all_status",
        """
        SELECT c.commercial_status, count(*)
        FROM commercial_lineup_line l
        JOIN commercial_lineup_case c ON c.id = l.case_id
        WHERE l.customer_id = 18 AND c.period_label = '2026Q2'
        GROUP BY c.commercial_status
        """,
    ),
    (
        "settled_all",
        "SELECT count(*) FROM cpor_case WHERE status = 'settled'",
    ),
    (
        "settled_exclude",
        """
        SELECT count(*) FROM cpor_case
        WHERE status = 'settled' AND coalesce(intelligence_exclude, false) = false
        """,
    ),
    (
        "ended_all",
        "SELECT count(*) FROM cpor_case WHERE status = 'ended'",
    ),
    (
        "same_customer_cases_cm",
        """
        SELECT count(*) FROM cpor_case
        WHERE customer_id = 18 AND status IN ('ended','settled','approved','live')
        """,
    ),
]


def main() -> None:
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar()
        print("current_database()", db)
        if db != "cip":
            raise SystemExit("refusing: not cip")
    for name, sql in QUERIES:
        print("---", name)
        with engine.connect() as conn:
            try:
                rows = conn.execute(text(sql)).fetchall()
                for r in rows:
                    print(tuple(r))
            except Exception as exc:
                print("ERR", type(exc).__name__, str(exc).split("\n")[0][:240])


if __name__ == "__main__":
    main()
