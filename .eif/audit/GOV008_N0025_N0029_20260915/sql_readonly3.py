"""Probe lineup period labels for customer 18. Read-only."""
from __future__ import annotations

import sys
from pathlib import Path

API = Path(__file__).resolve().parents[3] / "apps" / "api"
sys.path.insert(0, str(API))

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url


def main() -> None:
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar()
        print("current_database()", db)
        rows = conn.execute(
            text(
                """
                SELECT c.period_label, c.commercial_status, count(*) AS n
                FROM commercial_lineup_line l
                JOIN commercial_lineup_case c ON c.id = l.case_id
                WHERE l.customer_id = 18 AND l.product_id IS NOT NULL
                GROUP BY c.period_label, c.commercial_status
                ORDER BY n DESC
                LIMIT 20
                """
            )
        ).fetchall()
        print("--- cm lines by case period")
        for r in rows:
            print(tuple(r))
        active = conn.execute(
            text(
                """
                SELECT count(*) AS lines,
                       count(DISTINCT l.product_id) AS products
                FROM commercial_lineup_line l
                JOIN commercial_lineup_case c ON c.id = l.case_id
                WHERE l.customer_id = 18
                  AND l.product_id IS NOT NULL
                  AND l.row_status IS DISTINCT FROM 'superseded'
                  AND c.superseded_by_case_id IS NULL
                  AND c.commercial_status NOT IN ('cancelled', 'superseded')
                  AND replace(upper(c.period_label), ' ', '') IN ('2026Q2', '26Q2')
                """
            )
        ).one()
        print("--- active cm 2026q2 lines, distinct products", tuple(active))


if __name__ == "__main__":
    main()
