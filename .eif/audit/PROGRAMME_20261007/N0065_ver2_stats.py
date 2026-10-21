"""GOV-008 N-0065 VER2: planner statistics, indexes and per-row RLS predicate cost on cip (READ ONLY).

Run from the project root with the API virtualenv. Prints current_database() first.
No ANALYZE, no DDL, no writes: default_transaction_read_only=on, statement_timeout=60s.
"""

from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
API = os.path.join(ROOT, "apps", "api")
os.chdir(API)
sys.path.insert(0, API)

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402

TABLES = ("dim_product", "weeks_of_cover_observation", "fact_inbound_shipment", "shipment_evidence_observation",
          "shipment_evidence_line", "fact_sales_sellout", "fact_inventory_distributor", "fact_demand_forecast",
          "fact_inventory_reconciliation", "cpor_case", "cpor_case_line", "dim_distributor")

url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
eng = sa.create_engine(url, poolclass=NullPool, connect_args={
    "options": "-c default_transaction_read_only=on -c statement_timeout=60000", "prepare_threshold": None})


def t(c, sql, **kw):
    return c.execute(sa.text(sql), kw)


with eng.connect() as c:
    print("current_database() =", t(c, "select current_database()").scalar_one(),
          "| read_only =", t(c, "show transaction_read_only").scalar_one())
    for name in ("autovacuum", "autovacuum_analyze_threshold", "autovacuum_analyze_scale_factor", "work_mem",
                 "shared_buffers", "effective_cache_size", "jit", "jit_above_cost", "random_page_cost",
                 "default_statistics_target", "max_parallel_workers_per_gather"):
        print(f"  {name} = {t(c, f'show {name}').scalar_one()}")
    print("\npg_stat_user_tables (n_live_tup, n_mod_since_analyze, last_analyze, last_autoanalyze, reltuples, relpages, cols with pg_stats, threshold)")
    for tb in TABLES:
        r = t(c, """select s.n_live_tup, s.n_mod_since_analyze, s.last_analyze, s.last_autoanalyze, c.reltuples, c.relpages,
                         (select count(*) from pg_stats p where p.tablename = s.relname and p.schemaname='public'),
                         s.autoanalyze_count, s.analyze_count, c.reloptions
                  from pg_stat_user_tables s join pg_class c on c.oid = s.relid
                  where s.relname = :t and s.schemaname = 'public'""", t=tb).one_or_none()
        if r is None:
            print(f"  {tb}: not found")
            continue
        thr = 50 + 0.1 * max(r[4], 0)
        print(f"  {tb:30} live={r[0]:>7} mod_since_analyze={r[1]:>6} last_analyze={r[2]} last_autoanalyze={r[3]} "
              f"reltuples={r[4]:>9.0f} relpages={r[5]:>6} pg_stats_cols={r[6]:>3} autoanalyze_count={r[7]} "
              f"analyze_count={r[8]} threshold~{thr:.0f} reloptions={r[9]}")
    print("\nindexes on weeks_of_cover_observation:")
    for (d,) in t(c, "select indexdef from pg_indexes where tablename='weeks_of_cover_observation' order by 1"):
        print("  ", d)
    print("table size weeks_of_cover_observation =", t(c, "select pg_size_pretty(pg_table_size('weeks_of_cover_observation'))").scalar_one(),
          "| avg row width (pg_stats sum) =", t(c, "select sum(avg_width) from pg_stats where tablename='weeks_of_cover_observation'").scalar_one())

    # Estimated vs actual for simple predicates the heavy statements use.
    print("\nestimate vs actual (EXPLAIN ANALYZE, as role cip under '*'):")
    t(c, "select set_config('cip.product_lines', '*', true)")
    for sql in ("select count(*) from dim_product where tenant_id = 'default'",
                "select count(*) from dim_product where product_line = 'NB'",
                "select count(*) from weeks_of_cover_observation where tenant_id = 'default'",
                "select count(*) from fact_inbound_shipment where tenant_id = 'default' and status <> 'received'"):
        plan = [r[0] for r in t(c, "explain (analyze, costs on, timing off, summary off) " + sql)]
        scan = [p for p in plan if "Scan" in p][:1]
        print(f"   {sql}\n      {scan[0].strip() if scan else plan}")
    c.rollback()

    # Per-row predicate cost: 194,349 real product ids from weeks_of_cover_observation.
    def bench(label, setting, expr):
        best = None
        for _ in range(3):
            if setting is not None:
                t(c, "select set_config('cip.product_lines', :v, true)", v=setting)
            t(c, "select set_config('cip.product_lines', '*', true)") if setting is None else None
            ids_sql = "(select product_id as pid from weeks_of_cover_observation) w"
            if setting is None:
                # read the ids under '*', then measure the expression with the setting unset
                pass
            t0 = time.perf_counter()
            n = t(c, f"select count(*) filter (where {expr}) from {ids_sql}").scalar_one()
            ms = (time.perf_counter() - t0) * 1000
            c.rollback()
            best = ms if best is None else min(best, ms)
        return n, best

    print("\nper-row predicate cost over the 194k product ids of weeks_of_cover_observation (best of 3 wall ms; the "
          "base read itself passes the table's own policy under the given setting):")
    base_star = None
    for setting in ("*", "NB"):
        n0, ms0 = bench("base", setting, "true")
        n1, ms1 = bench("0025 inline", setting,
                        "(pid is null or coalesce(current_setting('cip.product_lines', true), '') in ('', '*') or "
                        "pid::bigint in (select p.id from dim_product p where cip_product_line_visible(p.product_line)))")
        n2, ms2 = bench("0024 definer fn", setting, "cip_product_id_visible(pid::bigint)")
        print(f"  setting={setting!r}: rows={n0} base={ms0:.0f} ms | 0025 inline predicate: pass={n1} +{ms1 - ms0:.0f} ms "
              f"({(ms1 - ms0) * 1000 / max(n0, 1):.2f} us/row) | 0024 definer function: pass={n2} +{ms2 - ms0:.0f} ms "
              f"({(ms2 - ms0) * 1000 / max(n0, 1):.2f} us/row)")
eng.dispose()
