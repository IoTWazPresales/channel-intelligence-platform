"""N-0068 read-only probe of the configured database (SELECT only, read-only transaction).

Run from apps/api with its virtualenv. Prints current_database() first. Never prints secrets.
"""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def main() -> int:
    url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
    eng = create_engine(url)
    with eng.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        print("current_database() =", c.execute(text("select current_database()")).scalar_one())
        print(
            "alembic_version =",
            c.execute(text("select version_num from alembic_version")).scalars().all(),
        )
        print(
            "tenant_column_grain rows =",
            [tuple(r) for r in c.execute(text("select tenant_id, grain from tenant_column_grain order by 1"))],
        )
        print(
            "tenant rows =",
            c.execute(text("select count(*) from tenant")).scalar_one(),
        )
        idx = c.execute(
            text(
                "select indexname, indexdef from pg_indexes "
                "where schemaname='public' and tablename='dim_product' and indexdef ilike '%ean%'"
            )
        ).all()
        print("dim_product indexes mentioning ean =", [tuple(r) for r in idx])
        uq = c.execute(
            text(
                "select conname, pg_get_constraintdef(oid) from pg_constraint "
                "where conrelid='dim_product'::regclass and contype in ('u','x')"
            )
        ).all()
        print("dim_product unique/exclusion constraints =", [tuple(r) for r in uq])
        print(
            "catalog_product rows =",
            c.execute(text("select count(*) from catalog_product")).scalar_one(),
            "product_catalog rows =",
            c.execute(text("select count(*) from product_catalog")).scalar_one(),
        )
        dup = c.execute(
            text(
                "select count(*) from (select ean from dim_product where ean is not null and btrim(ean)<>'' "
                "group by ean having count(*)>1) d"
            )
        ).scalar_one()
        print("duplicate EAN values in dim_product (visible to this role) =", dup)
        mem = c.execute(
            text(
                "select sd.id, sd.name, "
                "coalesce(jsonb_object_keys_count, 0) from ("
                "select id, name, column_mapping_memory from source_definition) sd "
                "left join lateral (select count(*) as jsonb_object_keys_count from jsonb_object_keys("
                "coalesce(sd.column_mapping_memory->'mapping_profile'->'by_product_line','{}'::jsonb))) k on true "
                "where sd.column_mapping_memory ? 'mapping_profile'"
            )
        ).all()
        print("sources with per-line mapping profiles (id, slug, line count) =", [tuple(r) for r in mem])
        by_grain = c.execute(
            text(
                "select count(*) from source_definition "
                "where column_mapping_memory->'mapping_profile' ? 'by_grain'"
            )
        ).scalar_one()
        print("sources with by_grain overlays =", by_grain)
        c.rollback()
    eng.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
