"""N-0065 round 3: read-only row counts of product-keyed tables (cip_test or cip)."""

from __future__ import annotations

import sys

import sqlalchemy as sa

from app.core.config import get_settings


def url_for(db: str) -> str:
    u = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
    base, _, tail = u.rpartition("/")
    q = ("?" + tail.split("?", 1)[1]) if "?" in tail else ""
    return f"{base}/{db}{q}"


TABLES_SQL = """
select c.table_name,
       coalesce(max(c.column_name) filter (where c.column_name = 'product_id'),
                max(c.column_name) filter (where c.column_name = 'canonical_product_id')) col
from information_schema.columns c
join information_schema.tables t on t.table_schema=c.table_schema and t.table_name=c.table_name
where c.table_schema='public' and t.table_type='BASE TABLE'
  and c.column_name in ('product_id','canonical_product_id')
  and c.data_type in ('integer','bigint','smallint') and c.table_name <> 'dim_product'
group by 1 order by 1
"""

target = sys.argv[1]
assert target in ("cip_test", "cip")
eng = sa.create_engine(url_for(target), poolclass=sa.pool.NullPool)
with eng.connect() as c:
    c.execute(sa.text("SET TRANSACTION READ ONLY"))
    c.execute(sa.text("SET LOCAL statement_timeout = '60s'"))
    db = c.execute(sa.text("select current_database()")).scalar_one()
    print("current_database() =", db)
    assert db == target
    for t, col in c.execute(sa.text(TABLES_SQL)).all():
        n, nn, d = c.execute(sa.text(
            f'select count(*), count(*) filter (where "{col}" is null), count(distinct "{col}") from "{t}"'
        )).one()
        print(f"{t:45} {col:22} rows={n:8} null={nn:6} distinct={d}")
    c.rollback()
eng.dispose()
