"""N-0101 round 3: read-only look at cip_test (schema for the snapshot tests). No writes.

Run from apps/api with its virtualenv. The cip_test URL is derived in-process from the
configured settings; no credential is printed.
"""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def _swap(url: str) -> str:
    base, _, tail = url.rpartition("/")
    query = "?" + tail.split("?", 1)[1] if "?" in tail else ""
    return f"{base}/cip_test{query}"


def main() -> None:
    url = _swap(get_settings().database_url_sync).replace("postgresql://", "postgresql+psycopg://", 1)
    eng = create_engine(url)
    with eng.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        print("current_database() =", c.execute(text("select current_database()")).scalar_one())
        print("alembic =", c.execute(text("select version_num from alembic_version")).scalars().all())
        for t in ("customer_listing", "listing_observation", "dim_customer"):
            n = c.execute(text(f"select count(*) from {t}")).scalar_one()
            print(t, "rows =", n)
        print(
            "listing_observation older than 90 d with snapshot =",
            c.execute(
                text(
                    "select count(*) from listing_observation where raw_snapshot is not null "
                    "and fetched_at < now() - interval '90 days'"
                )
            ).scalar_one(),
        )
        rows = c.execute(
            text(
                "select column_name, is_nullable, column_default from information_schema.columns "
                "where table_name = 'dim_customer' and is_nullable = 'NO' order by ordinal_position"
            )
        ).all()
        print("dim_customer NOT NULL columns:", [(r[0], r[2]) for r in rows])
        rows = c.execute(
            text(
                "select column_name, is_nullable from information_schema.columns "
                "where table_name = 'listing_observation' order by ordinal_position"
            )
        ).all()
        print("listing_observation columns:", [(r[0], r[1]) for r in rows])
    eng.dispose()


if __name__ == "__main__":
    main()
