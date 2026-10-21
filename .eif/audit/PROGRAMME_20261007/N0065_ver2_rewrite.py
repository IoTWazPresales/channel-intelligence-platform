"""GOV-008 N-0065 VER2: does a narrow rewrite of the latest-cover statement remove the sort spill? (READ ONLY, cip)

Compares the captured statement (wide DISTINCT ON over every column) with a rewrite that runs DISTINCT ON over
the sort keys and id only and then fetches the full rows by id. Checks the two return the same ids.
Best of 3 wall ms per scope. No writes.
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

ORDER = ("w.distributor_id, w.product_id, w.cover_as_of_date DESC, "
         "CASE WHEN w.trigger = 'as_of_backfill' THEN 1 ELSE 0 END, w.observed_at DESC")
ORIG = f"""SELECT DISTINCT ON (w.distributor_id, w.product_id) w.* FROM weeks_of_cover_observation w
           WHERE w.tenant_id = 'default' ORDER BY {ORDER}"""
NARROW = f"""WITH cur AS MATERIALIZED (
               SELECT DISTINCT ON (w.distributor_id, w.product_id) w.id FROM weeks_of_cover_observation w
               WHERE w.tenant_id = 'default' ORDER BY {ORDER})
             SELECT w.* FROM weeks_of_cover_observation w JOIN cur ON cur.id = w.id
             ORDER BY w.distributor_id, w.product_id"""

url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
eng = sa.create_engine(url, poolclass=NullPool, connect_args={
    "options": "-c default_transaction_read_only=on -c statement_timeout=60000", "prepare_threshold": None})
with eng.connect() as c:
    print("current_database() =", c.execute(sa.text("select current_database()")).scalar_one(),
          "| read_only =", c.execute(sa.text("show transaction_read_only")).scalar_one())
    for scope in (None, "*", "NB"):
        res = {}
        for name, sql in (("original", ORIG), ("narrow", NARROW)):
            best, ids = None, None
            for _ in range(3):
                if scope is not None:
                    c.execute(sa.text("select set_config('cip.product_lines', :v, true)"), {"v": scope})
                t0 = time.perf_counter()
                rows = c.execute(sa.text(sql)).all()
                ms = (time.perf_counter() - t0) * 1000
                ids = sorted(r.id for r in rows)
                c.rollback()
                best = ms if best is None else min(best, ms)
            res[name] = (best, ids)
        same = res["original"][1] == res["narrow"][1]
        print(f"scope={scope!r:6} original={res['original'][0]:.0f} ms narrow={res['narrow'][0]:.0f} ms "
              f"rows={len(res['original'][1])}/{len(res['narrow'][1])} same_ids={same}")
    if True:
        plan = [r[0] for r in c.execute(sa.text("EXPLAIN (ANALYZE, BUFFERS) " + NARROW)).all()]
        for ln in plan:
            if any(k in ln for k in ("Sort Method", "Execution Time", "Unique", "Hash Join", "Seq Scan", "Index Scan")):
                print("   ", ln.strip()[:180])
        c.rollback()
eng.dispose()
