"""Read-only: one settled case line grains + mint/promote facts."""
from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402

SQLS = [
    ("current_database", "SELECT current_database()"),
    (
        "case_311_lines",
        """
        SELECT l.id, p.sku, p.name, d.name AS distributor,
               l.estimate_qty, l.result_qty, l.support_unit, l.ttl_support, l.ttl_result,
               l.distributor_id
        FROM cpor_case_line l
        LEFT JOIN dim_product p ON p.id = l.product_id
        LEFT JOIN dim_distributor d ON d.id = l.distributor_id
        WHERE l.case_id = 311
        ORDER BY l.id
        """,
    ),
    (
        "case_311_cst",
        """
        SELECT p.sku, sum(f.units_sold)
        FROM fact_customer_sellthrough f
        JOIN dim_product p ON p.id = f.product_id
        JOIN cpor_case c ON c.id = 311
        WHERE f.customer_id = c.customer_id
          AND f.period_start_date <= c.window_end
          AND f.period_start_date >= c.window_start - interval '31 days'
          AND f.product_id IN (SELECT product_id FROM cpor_case_line WHERE case_id = 311)
        GROUP BY p.sku
        ORDER BY 1
        """,
    ),
    (
        "mint_setting",
        "SELECT tenant_id, prefix, separator, pad_width, next_seq, segment_mode FROM customer_code_mint_setting",
    ),
    (
        "promote_actions",
        """
        SELECT action, count(*) FROM steward_audit_event
        WHERE action ILIKE '%promote%'
        GROUP BY action
        """,
    ),
    (
        "code_prefix_counts",
        """
        SELECT
          CASE
            WHEN code LIKE 'TMP-CUST-%' THEN 'TMP-CUST'
            WHEN code ~ '^CUST-[0-9]+$' THEN 'CUST-seq'
            ELSE 'other'
          END AS kind,
          count(*)
        FROM dim_customer
        GROUP BY 1
        ORDER BY 2 DESC
        """,
    ),
    (
        "other_code_samples",
        """
        SELECT code, name FROM dim_customer
        WHERE code NOT LIKE 'TMP-CUST-%' AND code !~ '^CUST-[0-9]+$'
        ORDER BY id LIMIT 20
        """,
    ),
]

def main() -> int:
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        for label, sql in SQLS:
            print(f"--- {label} ---")
            try:
                rows = conn.execute(text(sql)).fetchall()
            except Exception as exc:
                print("ERROR", type(exc).__name__, str(exc).split("\n")[0][:240])
                conn.rollback()
                continue
            if not rows:
                print("(no rows)")
            for row in rows:
                print(tuple(row))
            print()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
