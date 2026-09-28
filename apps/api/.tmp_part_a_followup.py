"""Read-only PART A follow-up. Prints current_database() first. No DML."""
from __future__ import annotations

from sqlalchemy import text

from app.db.session_sync import SessionLocal

QUERIES = [
    ("current_database", "SELECT current_database()"),
    (
        "product_line_x_business_unit",
        """
        SELECT product_line, business_unit, count(*) AS n
        FROM dim_product
        GROUP BY product_line, business_unit
        ORDER BY product_line NULLS LAST, n DESC
        """,
    ),
    (
        "product_line_samples",
        """
        SELECT product_line, sku, left(coalesce(sales_model_name, name, ''), 80) AS name
        FROM (
          SELECT product_line, sku, sales_model_name, name,
                 row_number() OVER (PARTITION BY product_line ORDER BY id) AS rn
          FROM dim_product
        ) t
        WHERE rn <= 3
        ORDER BY product_line NULLS LAST, rn
        """,
    ),
    (
        "specs_json_coverage",
        """
        SELECT
          count(*) AS n,
          count(specs_json) AS has_specs,
          count(*) FILTER (WHERE specs_json IS NOT NULL AND specs_json <> '{}'::jsonb) AS nonempty_specs
        FROM dim_product
        """,
    ),
    (
        "catalog_jobs",
        """
        SELECT last_import_job_id, count(*) 
        FROM catalog_product
        GROUP BY 1
        ORDER BY 2 DESC
        """,
    ),
    (
        "cpor_case_columns",
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'cpor_case'
        ORDER BY ordinal_position
        """,
    ),
    (
        "cpor_status_check",
        """
        SELECT conname, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = 'cpor_case'::regclass
          AND contype IN ('c', 'u')
        """,
    ),
]


def main() -> None:
    s = SessionLocal()
    try:
        for title, sql in QUERIES:
            print(f"=== {title} ===")
            rows = s.execute(text(sql)).all()
            for row in rows:
                print(tuple(row))
            print(f"rows={len(rows)}")
            print()
    finally:
        s.close()


if __name__ == "__main__":
    main()
