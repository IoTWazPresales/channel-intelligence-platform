"""Read-only: confirm the N-0068 DB tests left no fixture rows in cip_test."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def main() -> int:
    url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
    base, _, tail = url.rpartition("/")
    q = ("?" + tail.split("?", 1)[1]) if "?" in tail else ""
    eng = create_engine(f"{base}/cip_test{q}")
    with eng.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        print("current_database() =", c.execute(text("select current_database()")).scalar_one())
        print("dim_product N0068 fixtures =", c.execute(text("select count(*) from dim_product where sku like 'N0068-%'")).scalar_one())
        print("tenant n0068 fixtures =", c.execute(text("select count(*) from tenant where id like 'n0068-%'")).scalar_one())
        print("import_job n0068 fixtures =", c.execute(text("select count(*) from import_job where file_name = 'n0068.xlsx'")).scalar_one())
        print(
            "sources with N0068 line keys =",
            c.execute(
                text(
                    "select count(*) from source_definition where "
                    "coalesce(column_mapping_memory->'mapping_profile'->'by_product_line','{}'::jsonb)::text like '%MB%' "
                    "and column_mapping_memory::text like '%chipset_socket%'"
                )
            ).scalar_one(),
        )
        c.rollback()
    eng.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
