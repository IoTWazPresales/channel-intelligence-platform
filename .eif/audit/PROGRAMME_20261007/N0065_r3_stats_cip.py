"""Read-only: planner statistics freshness for the N-0065 heavy-path tables. Run from apps/api.

python N0065_r3_stats_cip.py cip|cip_test
"""

import sys

import sqlalchemy as sa
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

target = sys.argv[1]
assert target in ("cip", "cip_test")
u = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
base, _, tail = u.rpartition("/")
q = ("?" + tail.split("?", 1)[1]) if "?" in tail else ""
eng = sa.create_engine(f"{base}/{target}{q}", poolclass=NullPool,
                       connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=60000"})
TABLES = ("dim_product", "fact_inventory_distributor", "fact_sales_sellout", "fact_inbound_shipment",
          "weeks_of_cover_observation", "fact_demand_forecast", "shipment_evidence_line",
          "shipment_evidence_observation")
with eng.connect() as c:
    print("current_database() =", c.execute(sa.text("select current_database()")).scalar_one(),
          "| read_only =", c.execute(sa.text("show transaction_read_only")).scalar_one())
    rows = c.execute(sa.text("""
        select relname, n_live_tup, n_mod_since_analyze, last_analyze, last_autoanalyze,
               (select reltuples::bigint from pg_class where oid = s.relid) as reltuples
        from pg_stat_user_tables s where relname = any(:t) order by relname"""), {"t": list(TABLES)}).all()
    for r in rows:
        print(tuple(r))
    st = c.execute(sa.text("""
        select tablename, null_frac, n_distinct, most_common_vals::text
        from pg_stats where schemaname='public' and attname='tenant_id' and tablename = any(:t)
        order by 1"""), {"t": list(TABLES)}).all()
    print("tenant_id stats:", [tuple(x) for x in st])
eng.dispose()
