"""GOV-008 N-0065: read-only state of cip_test after the DB gate tests. Run from apps/api."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def main() -> int:
    url = get_settings().database_url_sync
    base, _, tail = url.rpartition("/")
    q = ("?" + tail.split("?", 1)[1]) if "?" in tail else ""
    eng = create_engine(f"{base}/cip_test{q}".replace("postgresql://", "postgresql+psycopg://", 1))
    with eng.connect() as c:
        db = c.execute(text("select current_database()")).scalar_one()
        print("current_database() =", db)
        assert db == "cip_test"
        c.execute(text("SET TRANSACTION READ ONLY"))
        print("alembic =", c.execute(text("select version_num from alembic_version")).scalars().all())
        print("cip_product_% functions =", c.execute(text("select count(*) from pg_proc where proname like 'cip_product_%'")).scalar_one())
        print("dim_product rls =", c.execute(text("select relrowsecurity from pg_class where relname='dim_product'")).scalar_one())
        print("products =", c.execute(text("select count(*) from dim_product")).scalar_one())
        print("N0065 fixture skus =", c.execute(text("select count(*) from dim_product where sku like 'N0065-%'")).scalar_one())
        c.rollback()
    eng.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
