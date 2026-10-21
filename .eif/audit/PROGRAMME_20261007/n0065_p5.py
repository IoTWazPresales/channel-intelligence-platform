"""N-0065 perf probe 5: plan-vs-executed -- where is the RLS qual in its heaviest statements,
and the sum over its 58 statements under '*' vs NB. Read-only."""
import json
import pathlib
import time

from n0065_dbh import engine, ro, sa

here = pathlib.Path(__file__).parent
d = json.loads((here / "n0065_cap_unset.json").read_text(encoding="utf-8"))
st = [s for s in d["stmts"] if s.get("label") == "unset /api/v1/plan-vs-executed" and s.get("ms") is not None]
st.sort(key=lambda s: -s["ms"])
print("statements:", len(st), "sum ms (capture, unset):", round(sum(s["ms"] for s in st)))
for s in st[:6]:
    print(round(s["ms"]), s["engine"], " ".join(s["sql"].split())[:160])
e = engine()
with e.connect() as c:
    ro(c)
    c.execute(sa.text("select set_config('cip.product_lines', '*', true)"))
    top = st[0]
    plan = c.exec_driver_sql("EXPLAIN (FORMAT TEXT) " + top["sql"], top["params"] or None).fetchall()
    lines = [r[0] for r in plan]
    print("plan lines:", len(lines), "lines naming cip_product:", sum("cip_product" in x for x in lines))
    for x in lines[:40]:
        print(x[:170])
