"""N-0065 round 5: READ ONLY catalogue of what 0027 changes, as the app role. Prints current_database() first.

Usage (project root, API virtualenv):  python <this> cip|cip_test
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "apps", "api")
os.chdir(API)
sys.path.insert(0, API)

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402

DB = sys.argv[1] if len(sys.argv) > 1 else "cip_test"
assert DB in ("cip", "cip_test")
FOUR = ("commercial_lineup_line", "cst_listing_seed", "customer_listing", "historical_lineup_import_line")
url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
if DB == "cip_test":
    base, _, tail = url.rpartition("/")
    url = f"{base}/cip_test" + (("?" + tail.split("?", 1)[1]) if "?" in tail else "")
eng = sa.create_engine(url, poolclass=NullPool, connect_args={"options": "-c default_transaction_read_only=on"})
with eng.connect() as c:
    print("current_database() =", c.execute(sa.text("select current_database()")).scalar_one(),
          "| alembic =", c.execute(sa.text("select version_num from alembic_version")).scalars().all())
    print("  pick proconfig:", c.execute(sa.text(
        "select proconfig from pg_proc where proname = 'cip_sev_current_observation_ids'")).scalar())
    for t in FOUR:
        rows = c.execute(sa.text(
            "select cmd, coalesce(qual, '') like '%request_role%', coalesce(with_check, '') like '%request_role%', "
            "coalesce(qual, '') like '%product_id IS NULL) OR%' from pg_policies where tablename = :t order by cmd"),
            {"t": t}).all()
        print(f"  {t:32} (cmd, using has steward rule, check has steward rule, using has 0025 null-open):",
              [tuple(r) for r in rows])
    print("  md5 of the four tables' policy texts:", c.execute(sa.text(
        "select md5(string_agg(tablename || cmd || coalesce(qual, '') || coalesce(with_check, ''), '|' "
        "order by tablename, cmd)) from pg_policies where tablename = any(:t)"), {"t": list(FOUR)}).scalar())
    c.rollback()
eng.dispose()
