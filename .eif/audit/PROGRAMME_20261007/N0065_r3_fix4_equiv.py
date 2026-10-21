"""Fix 4 equivalence on cip, READ ONLY: the pre-fix derived-stock statement (captured by the
perf study, n0065_cap_unset.json) and the fixed one (N0065_r3_cap_cip_0024_fix4b.json) return
the same rows under unset / '*' / 'NB'. enable_nestloop=off only so the old form finishes
inside the 60 s timeout; it does not change results. Run from apps/api with its venv.
"""

import json
import os
import sys
import time

import sqlalchemy as sa
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

H = os.path.dirname(os.path.abspath(__file__))


def pick(fname: str, needle: str) -> dict:
    cap = json.load(open(os.path.join(H, fname), encoding="utf-8"))
    c = [s for s in cap["stmts"] if s.get("ms") is not None and (s["label"] or "").startswith("unset ")
         and "net-requirement" in s["label"] and needle in s["sql"]]
    return max(c, key=lambda s: s["ms"])


old = pick("n0065_cap_unset.json", "inv_latest")
new = pick("N0065_r3_cap_cip_0024_fix4b.json", "latest_snapshot AS MATERIALIZED")
assert "MATERIALIZED" not in old["sql"]
print("old head:", " ".join(old["sql"].split())[:90])
print("new head:", " ".join(new["sql"].split())[:90])
url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
eng = sa.create_engine(url, poolclass=NullPool, connect_args={
    "options": "-c default_transaction_read_only=on -c statement_timeout=60000", "prepare_threshold": None})
ok = True
for scope in (None, "*", "NB"):
    res = {}
    for name, s in (("old", old), ("new", new)):
        with eng.connect() as c:
            if scope is None:
                print("current_database() =", c.execute(sa.text("select current_database()")).scalar_one(),
                      "| read_only =", c.execute(sa.text("show transaction_read_only")).scalar_one()) if name == "old" else None
            else:
                c.execute(sa.text("select set_config('cip.product_lines', :v, true)"), {"v": scope})
            c.execute(sa.text("set local enable_nestloop = off"))
            t0 = time.perf_counter()
            rows = c.exec_driver_sql(s["sql"], s["params"] or {}).all()
            ms = round((time.perf_counter() - t0) * 1000)
            res[name] = sorted(tuple(str(v) for v in r) for r in rows)
            print(f"  scope={scope!r:6} {name}: {len(rows)} rows in {ms} ms (nestloop off)")
            c.rollback()
    same = res["old"] == res["new"]
    ok = ok and same
    print(f"  scope={scope!r:6} identical rows: {same}")
eng.dispose()
sys.exit(0 if ok else 1)
