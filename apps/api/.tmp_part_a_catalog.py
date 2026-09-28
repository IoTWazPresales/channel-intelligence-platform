"""Read-only PART A catalogue probe. Prints current_database() first. No DML."""
from __future__ import annotations

from sqlalchemy import text

from app.db.session_sync import SessionLocal

QUERIES = [
    ("current_database", "SELECT current_database()"),
    (
        "business_unit",
        "SELECT id, code, name FROM business_unit ORDER BY id",
    ),
    (
        "product_catalog",
        "SELECT id, business_unit_id, code, name, is_active FROM product_catalog ORDER BY id",
    ),
    (
        "source_definition_all",
        """
        SELECT id, code, name, source_kind, is_active, product_catalog_id,
               (column_mapping_memory IS NOT NULL) AS has_mapping_memory,
               CASE WHEN column_mapping_memory IS NULL THEN 'null'
                    ELSE jsonb_typeof(column_mapping_memory) END AS mem_type
        FROM source_definition
        ORDER BY id
        """,
    ),
    (
        "source_definition_with_catalog",
        """
        SELECT id, code, name, source_kind, product_catalog_id
        FROM source_definition
        WHERE product_catalog_id IS NOT NULL
        ORDER BY id
        """,
    ),
    (
        "catalog_product_counts",
        """
        SELECT count(*) AS n,
               count(canonical_product_id) AS linked,
               count(*) FILTER (WHERE canonical_product_id IS NULL) AS unlinked,
               count(DISTINCT catalog_id) AS catalogs,
               count(DISTINCT last_import_job_id) AS distinct_jobs
        FROM catalog_product
        """,
    ),
    (
        "attribute_definition_count",
        "SELECT count(*) FROM attribute_definition",
    ),
    (
        "product_attribute_value_count",
        "SELECT count(*) FROM product_attribute_value",
    ),
    (
        "attr_by_data_type",
        "SELECT data_type, count(*) FROM attribute_definition GROUP BY 1 ORDER BY 2 DESC",
    ),
    (
        "attr_by_kind",
        """
        SELECT CASE
                 WHEN namespace LIKE 'catalog:%:staged:%' THEN 'staged'
                 WHEN namespace LIKE 'catalog:%:candidate:%' THEN 'candidate'
                 WHEN namespace LIKE 'global:%' THEN 'global'
                 WHEN namespace LIKE 'catalog:%:cat:%' THEN 'catalog_category'
                 ELSE 'other'
               END AS kind,
               count(*)
        FROM attribute_definition
        GROUP BY 1
        ORDER BY 2 DESC
        """,
    ),
    (
        "attr_catalog_ids",
        "SELECT catalog_id, count(*) FROM attribute_definition GROUP BY 1 ORDER BY 2 DESC",
    ),
    (
        "attr_all",
        """
        SELECT namespace, display_name, left(coalesce(description,''), 80) AS description,
               data_type, catalog_id
        FROM attribute_definition
        ORDER BY namespace
        """,
    ),
    (
        "product_line_counts",
        """
        SELECT product_line, count(*) AS n
        FROM dim_product
        GROUP BY product_line
        ORDER BY n DESC
        """,
    ),
    (
        "cpor_case_status",
        """
        SELECT status, count(*) FROM cpor_case GROUP BY status ORDER BY count(*) DESC
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
