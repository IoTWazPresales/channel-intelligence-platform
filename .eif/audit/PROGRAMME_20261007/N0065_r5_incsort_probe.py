"""N-0065 round 5 probe (READ ONLY): does enable_sort=off alone guarantee the ordered index-only
scan of the pick, or can the planner fall back to an Incremental Sort (governed by the separate
enable_incremental_sort)? Usage (API virtualenv): python <this> cip|cip_test
App role only, READ ONLY transactions, statement_timeout 60 s. Prints no URL.
"""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "apps" / "api"))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402

target = sys.argv[1]
assert target in ("cip", "cip_test")
url = get_settings().database_url_sync
base, _, tail = url.rpartition("/")
q = ("?" + tail.split("?", 1)[1]) if "?" in tail else ""
url = f"{base}/{target}{q}".replace("postgresql://", "postgresql+psycopg://", 1)
eng = sa.create_engine(url, poolclass=NullPool,
                       connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=60000"})

with eng.connect() as c:
    print("current_database() =", c.execute(sa.text("select current_database()")).scalar_one(),
          "| role =", c.execute(sa.text("select current_user")).scalar_one(),
          "|", c.execute(sa.text("show server_version")).scalar_one())
    cfg, src = c.execute(sa.text("select proconfig, prosrc from pg_proc where proname = 'cip_sev_current_observation_ids'")).one()
    query = src.split("RETURN QUERY", 1)[1].split(";", 1)[0]
    print("proconfig:", cfg)
    st = c.execute(sa.text("select n_live_tup, n_mod_since_analyze, last_autovacuum, last_vacuum, last_autoanalyze "
                           "from pg_stat_user_tables where relname = 'shipment_evidence_observation'")).one()
    print("stats:", tuple(st))
    vm = c.execute(sa.text("select relpages, relallvisible from pg_class where relname = 'shipment_evidence_observation'")).one()
    print("relpages, relallvisible:", tuple(vm))
    c.rollback()
    variants = [
        ("defaults", []),
        ("enable_sort=off", [("enable_sort", "off")]),
        ("enable_sort=off + enable_incremental_sort=off", [("enable_sort", "off"), ("enable_incremental_sort", "off")]),
        ("rpc=1000 + enable_sort=off", [("random_page_cost", "1000"), ("enable_sort", "off")]),
        ("rpc=1000 + enable_sort=off + enable_incremental_sort=off",
         [("random_page_cost", "1000"), ("enable_sort", "off"), ("enable_incremental_sort", "off")]),
    ]
    for label, sets in variants:
        c.execute(sa.text("select set_config('cip.product_lines', '*', true)"))
        for n, v in sets:
            c.execute(sa.text("select set_config(:n, :v, true)"), {"n": n, "v": v})
        plan = [r[0] for r in c.execute(sa.text("explain " + query)).all()]
        nodes = [ln.strip().removeprefix("->").strip()[:110] for ln in plan
                 if any(k in ln for k in ("Scan", "Sort", "Unique"))]
        best = None
        for _ in range(3):
            t0 = time.perf_counter()
            n = len(c.execute(sa.text(query)).all())
            ms = (time.perf_counter() - t0) * 1000
            best = ms if best is None else min(best, ms)
        print(f"--- {label}: rows={n} best of 3 {round(best, 1)} ms")
        for ln in nodes:
            print("     ", ln)
        c.rollback()
