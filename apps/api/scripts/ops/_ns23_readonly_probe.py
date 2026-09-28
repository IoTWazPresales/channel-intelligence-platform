"""Read-only NUMBER RULE probe. No writes. Prints current_database() first."""
from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402


def main() -> int:
    settings = get_settings()
    engine = create_engine(sqlalchemy_sync_engine_url(settings.database_url_sync))
    queries = [
        ("current_database", "SELECT current_database()"),
        ("auth_mode_setting", "SELECT 1"),  # printed from settings, not SQL
        (
            "app_user",
            "SELECT id, email, role, is_active FROM app_user ORDER BY id",
        ),
        (
            "cpor_status_counts",
            "SELECT status, count(*) FROM cpor_case GROUP BY status ORDER BY count(*) DESC",
        ),
        (
            "ended_or_settled_sample",
            """
            SELECT c.id, c.case_code, c.status, c.customer_id, dc.code, dc.name,
                   c.window_start, c.window_end, c.currency_code,
                   (SELECT count(*) FROM cpor_case_line l WHERE l.case_id = c.id) AS lines,
                   (SELECT count(*) FROM cpor_claim_evidence_line e WHERE e.case_id = c.id) AS claims
            FROM cpor_case c
            LEFT JOIN dim_customer dc ON dc.id = c.customer_id
            WHERE c.status IN ('ended', 'settled', 'active')
            ORDER BY (SELECT count(*) FROM cpor_claim_evidence_line e WHERE e.case_id = c.id) DESC,
                     (SELECT count(*) FROM cpor_case_line l WHERE l.case_id = c.id) DESC
            LIMIT 8
            """,
        ),
        (
            "tmp_cust_total",
            "SELECT count(*) FROM dim_customer WHERE code LIKE 'TMP-CUST-%'",
        ),
        (
            "tmp_cust_name_split",
            """
            SELECT
              count(*) FILTER (WHERE name IS NOT NULL AND btrim(name) <> '' AND name NOT ILIKE 'TMP-CUST%') AS real_name,
              count(*) FILTER (WHERE name IS NULL OR btrim(name) = '' OR name ILIKE 'TMP-CUST%') AS provisional_name,
              count(*) AS tmp_rows
            FROM dim_customer
            WHERE code LIKE 'TMP-CUST-%'
            """,
        ),
        (
            "tmp_name_samples",
            """
            SELECT code, name, customer_status, no_code_disposition
            FROM dim_customer
            WHERE code LIKE 'TMP-CUST-%'
            ORDER BY id
            LIMIT 12
            """,
        ),
        (
            "non_tmp_code_samples",
            """
            SELECT code, name, customer_status
            FROM dim_customer
            WHERE code NOT LIKE 'TMP-CUST-%'
            ORDER BY id
            LIMIT 15
            """,
        ),
        (
            "non_tmp_count",
            "SELECT count(*) FROM dim_customer WHERE code NOT LIKE 'TMP-CUST-%'",
        ),
        (
            "customer_total",
            "SELECT count(*) FROM dim_customer",
        ),
        (
            "promote_audit",
            """
            SELECT event_type, count(*)
            FROM steward_audit_event
            WHERE event_type ILIKE '%promote%' OR event_type ILIKE '%customer%'
            GROUP BY event_type
            ORDER BY count(*) DESC
            LIMIT 30
            """,
        ),
        (
            "product_line_counts",
            """
            SELECT coalesce(product_line, '<null>') AS product_line, count(*)
            FROM dim_product
            GROUP BY product_line
            ORDER BY count(*) DESC
            """,
        ),
        (
            "source_def_catalog",
            """
            SELECT id, name, product_catalog_id,
                   (column_mapping_memory IS NOT NULL) AS has_mem,
                   CASE WHEN column_mapping_memory IS NULL THEN 'null'
                        ELSE jsonb_typeof(column_mapping_memory::jsonb) END AS mem_type
            FROM source_definition
            ORDER BY id
            """,
        ),
        (
            "specs_json_populated",
            """
            SELECT
              count(*) AS products,
              count(*) FILTER (WHERE specs_json IS NOT NULL AND specs_json::text NOT IN ('null','{}')) AS specs_populated
            FROM dim_product
            """,
        ),
    ]
    print("CIP_AUTH_MODE", settings.cip_auth_mode)
    with engine.connect() as conn:
        for label, sql in queries:
            if label == "auth_mode_setting":
                continue
            print(f"--- {label} ---")
            try:
                rows = conn.execute(text(sql)).fetchall()
            except Exception as exc:
                print("ERROR", type(exc).__name__, str(exc)[:300])
                continue
            if not rows:
                print("(no rows)")
            for row in rows:
                print(tuple(row))
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
