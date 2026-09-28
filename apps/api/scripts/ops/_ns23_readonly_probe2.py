"""Read-only follow-up. One connection with ROLLBACK after errors. No writes."""
from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402


QUERIES = [
    ("current_database", "SELECT current_database()"),
    (
        "tmp_by_status",
        """
        SELECT customer_status, count(*),
               count(*) FILTER (WHERE merged_into_customer_id IS NOT NULL) AS merged_ptr
        FROM dim_customer
        WHERE code LIKE 'TMP-CUST-%'
        GROUP BY customer_status
        """,
    ),
    (
        "tmp_active",
        """
        SELECT id, code, name, customer_status, merged_into_customer_id
        FROM dim_customer
        WHERE code LIKE 'TMP-CUST-%' AND customer_status <> 'merged'
        ORDER BY id
        LIMIT 20
        """,
    ),
    (
        "tmp_active_count",
        """
        SELECT count(*) FROM dim_customer
        WHERE code LIKE 'TMP-CUST-%' AND coalesce(customer_status,'') <> 'merged'
        """,
    ),
    (
        "cases_on_tmp_customers",
        """
        SELECT count(*) FROM cpor_case c
        JOIN dim_customer dc ON dc.id = c.customer_id
        WHERE dc.code LIKE 'TMP-CUST-%'
        """,
    ),
    (
        "claim_evidence_totals",
        "SELECT count(*) FROM cpor_claim_evidence_line",
    ),
    (
        "cases_with_claims",
        """
        SELECT c.id, c.case_code, c.status, dc.code, dc.name, count(*) AS claims
        FROM cpor_claim_evidence_line e
        JOIN cpor_case c ON c.id = e.case_id
        LEFT JOIN dim_customer dc ON dc.id = c.customer_id
        GROUP BY c.id, c.case_code, c.status, dc.code, dc.name
        ORDER BY count(*) DESC
        LIMIT 8
        """,
    ),
    (
        "cst_rows",
        "SELECT count(*) FROM fact_customer_sellthrough",
    ),
    (
        "product_line_counts",
        """
        SELECT coalesce(product_line, '<null>') AS product_line, count(*)
        FROM dim_product
        GROUP BY 1
        ORDER BY 2 DESC
        """,
    ),
    (
        "source_def_catalog",
        """
        SELECT id, name, product_catalog_id,
               (column_mapping_memory IS NOT NULL) AS has_mem
        FROM source_definition
        ORDER BY id
        """,
    ),
    (
        "specs_json_populated",
        """
        SELECT count(*) AS products,
               count(*) FILTER (
                 WHERE specs_json IS NOT NULL AND specs_json::text NOT IN ('null','{}')
               ) AS specs_populated
        FROM dim_product
        """,
    ),
    (
        "steward_audit_cols",
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'steward_audit_event'
        ORDER BY ordinal_position
        """,
    ),
    (
        "promote_like_events",
        """
        SELECT action, count(*) FROM steward_audit_event
        WHERE action ILIKE '%promote%' OR entity_type ILIKE '%customer%'
        GROUP BY action
        ORDER BY count(*) DESC
        LIMIT 20
        """,
    ),
]


def main() -> int:
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        for label, sql in QUERIES:
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
