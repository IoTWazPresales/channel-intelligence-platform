"""N-0065 round 5 discovery, READ ONLY, app role. Prints current_database() first.

Usage (from the project root with the API virtualenv):  python <this> [cip|cip_test]
  * the four no-product tables: product column, rows, rows with no product, policies;
  * app_user roles (who would be affected by the steward-only rule on request paths);
  * the pick and lineage helper inner queries: plan + time by planner setting (SET LOCAL in a
    READ ONLY transaction, nothing persists).
"""
import importlib.util
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "apps", "api")
os.chdir(API)
sys.path.insert(0, API)

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402

DB = sys.argv[1] if len(sys.argv) > 1 else "cip"
assert DB in ("cip", "cip_test")
FOUR = ("commercial_lineup_line", "cst_listing_seed", "customer_listing", "historical_lineup_import_line")

url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
if DB == "cip_test":
    base, _, tail = url.rpartition("/")
    url = f"{base}/cip_test" + (("?" + tail.split("?", 1)[1]) if "?" in tail else "")
eng = sa.create_engine(url, poolclass=NullPool, connect_args={
    "options": "-c default_transaction_read_only=on -c statement_timeout=60000", "prepare_threshold": None})

spec = importlib.util.spec_from_file_location(
    "_m26", os.path.join(API, "alembic", "versions", "20261009_0026_shipment_evidence_lineage_rls.py"))
m26 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m26)


def inner(fn: str) -> str:
    body = m26.HELPER_SQL[fn]
    return body.split("RETURN QUERY", 1)[1].split(";\n      PERFORM", 1)[0]


with eng.connect() as c:
    print("current_database() =", c.execute(sa.text("select current_database()")).scalar_one(),
          "| read_only =", c.execute(sa.text("show transaction_read_only")).scalar_one(),
          "| alembic =", c.execute(sa.text("select version_num from alembic_version")).scalars().all())
    c.execute(sa.text("select set_config('cip.product_lines', '*', true)"))
    for t in FOUR:
        cols = c.execute(sa.text("""select column_name from information_schema.columns where table_schema='public'
            and table_name=:t and column_name in ('product_id','canonical_product_id') order by 1"""), {"t": t}).scalars().all()
        col = "product_id" if "product_id" in cols else cols[0]
        n = c.execute(sa.text(f"select count(*), count(*) filter (where {col} is null) from {t}")).one()
        pols = c.execute(sa.text("select cmd, left(qual, 60), left(with_check, 60) from pg_policies where tablename=:t order by cmd"),
                         {"t": t}).all()
        rls = c.execute(sa.text("select relrowsecurity, relforcerowsecurity, pg_get_userbyid(relowner) from pg_class where relname=:t"),
                        {"t": t}).one()
        print(f"{t}: cols={cols} chosen={col} rows={n[0]} no_product={n[1]} rls/force/owner={tuple(rls)} policies={len(pols)}")
        for p in pols:
            print("    ", tuple(p))
    try:
        roles = c.execute(sa.text("select lower(coalesce(role,'')), count(*), count(*) filter (where coalesce(is_active, true)) "
                                  "from app_user group by 1 order by 1")).all()
        print("app_user roles (role, users, active):", [tuple(r) for r in roles])
    except Exception as exc:  # noqa: BLE001
        print("app_user roles: n/a", type(exc).__name__)
        c.rollback()
        c.execute(sa.text("select set_config('cip.product_lines', '*', true)"))
    for fn in m26.HELPERS:
        q = inner(fn)
        for label, setting in (("default", None), ("enable_sort=off", "set local enable_sort = off"),
                               ("enable_sort=off+enable_hashagg=off", "set local enable_sort = off; set local enable_hashagg = off")):
            c.execute(sa.text("reset enable_sort"))
            c.execute(sa.text("reset enable_hashagg"))
            if setting:
                for s in setting.split(";"):
                    c.execute(sa.text(s))
            best, plan = None, None
            for _ in range(3):
                plan = c.execute(sa.text("explain (analyze, buffers) " + q)).all()
                ms = float([p[0] for p in plan if p[0].startswith("Execution Time")][0].split(":")[1].split()[0])
                best = ms if best is None else min(best, ms)
            print(f"--- {fn} [{label}] best of 3 {round(best, 1)} ms")
            for p in plan:
                if any(k in p[0] for k in ("Scan", "Sort", "Unique", "Aggregate", "Join", "Limit", "SubPlan", "Heap Fetches", "Disk", "Execution")):
                    print("      ", p[0][:150])
    c.rollback()
eng.dispose()
