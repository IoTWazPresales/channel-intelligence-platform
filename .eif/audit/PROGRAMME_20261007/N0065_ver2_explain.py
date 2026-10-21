"""GOV-008 N-0065 VER2: EXPLAIN (ANALYZE, BUFFERS) the heaviest captured statements of a path, READ ONLY on cip.

Run from the project root with the API virtualenv:
  python N0065_ver2_explain.py <path-substring> <rank: 1=top,2=second> <setting|None> [SET-k=v ...]
Statements come from N0065_r3_cap_cip_0025.json (captured after 0025 on cip). Connection options:
default_transaction_read_only=on, statement_timeout=60s. Prints current_database() first.
Extra args of the form k=v are applied with SET LOCAL (planner settings only; e.g. jit=off).
"""

from __future__ import annotations

import json
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

ALLOWED = {"jit", "enable_nestloop", "enable_hashjoin", "enable_mergejoin", "work_mem", "enable_seqscan",
           "enable_sort", "enable_incremental_sort", "random_page_cost", "max_parallel_workers_per_gather", "row_security"}

needle = sys.argv[1]
rank = int(sys.argv[2])
setting = None if sys.argv[3] == "None" else sys.argv[3]
sets = [a.split("=", 1) for a in sys.argv[4:] if "=" in a]
fmt_json = "json" in sys.argv[4:]
cap = json.load(open(os.path.join(HERE, "N0065_r3_cap_cip_0025.json"), encoding="utf-8"))
mode_label = {"None": "unset", "*": "star"}.get(sys.argv[3], sys.argv[3])
stmts = [s for s in cap["stmts"] if s.get("ms") is not None and (s.get("label") or "").startswith(mode_label + " ")
         and needle in s["label"]]
stmts.sort(key=lambda s: -s["ms"])
s = stmts[rank - 1]
url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
eng = sa.create_engine(url, poolclass=NullPool, connect_args={
    "options": "-c default_transaction_read_only=on -c statement_timeout=60000", "prepare_threshold": None})
with eng.connect() as c:
    print("current_database() =", c.execute(sa.text("select current_database()")).scalar_one(),
          "| read_only =", c.execute(sa.text("show transaction_read_only")).scalar_one(),
          "| jit =", c.execute(sa.text("show jit")).scalar_one(),
          "| work_mem =", c.execute(sa.text("show work_mem")).scalar_one(),
          "| server =", c.execute(sa.text("show server_version")).scalar_one())
    print("captured:", s["label"], s["ms"], "ms | engine:", s["engine"], "| setting:", setting, "| sets:", sets)
    if setting is not None:
        c.execute(sa.text("select set_config('cip.product_lines', :v, true)"), {"v": setting})
        c.execute(sa.text("select set_config('cip.editable_product_lines', :v, true)"), {"v": setting})
    for k, v in sets:
        assert k in ALLOWED, k
        c.execute(sa.text(f"set local {k} = '{v}'"))
    print("SQL:", " ".join(s["sql"].split())[:3000])
    print("PARAMS:", s["params"])
    t0 = time.perf_counter()
    rows = c.exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS, SETTINGS, VERBOSE OFF) " + s["sql"], s["params"] or {}).all()
    print(f"explain wall ms: {round((time.perf_counter() - t0) * 1000)}")
    for (line,) in rows:
        print(line)
    t0 = time.perf_counter()
    n = len(c.exec_driver_sql(s["sql"], s["params"] or {}).all())
    print(f"plain execution wall ms: {round((time.perf_counter() - t0) * 1000)} rows={n}")
    c.rollback()
eng.dispose()
