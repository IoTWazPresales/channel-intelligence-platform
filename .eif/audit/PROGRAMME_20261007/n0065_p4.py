"""N-0065 perf probe 4: lineup net-requirement statement -- plan shape vs RLS.
Runs the captured SQL (n0065_sql_0.sql) under '*' and 'NB', default planner and
enable_nestloop=off (SET LOCAL, session-only). Read-only; statement_timeout 60s."""
import json
import pathlib
import re
import time

from n0065_dbh import engine, ro, sa

here = pathlib.Path(__file__).parent
raw = (here / "n0065_sql_0.sql").read_text(encoding="utf-8").splitlines()
params = json.loads(raw[1].split("params: ", 1)[1])
sql = "\n".join(raw[2:])

e = engine()
for val in ("*", "NB"):
    for nl in ("on", "off"):
        with e.connect() as c:
            ro(c)
            c.execute(sa.text("select set_config('cip.product_lines', :v, true)"), {"v": val})
            c.exec_driver_sql(f"SET LOCAL enable_nestloop = {nl}")
            est = c.exec_driver_sql("EXPLAIN (FORMAT JSON) " + sql, params).scalar()
            est_rows = est[0]["Plan"]["Plan Rows"]
            t = time.perf_counter()
            try:
                n = len(c.exec_driver_sql(sql, params).fetchall())
                ms = round((time.perf_counter() - t) * 1000)
            except Exception as ex:  # noqa: BLE001
                n, ms = None, "timeout>60s" if "timeout" in str(ex) else str(ex)[:80]
            print(f"guc={val!r:5} nestloop={nl:3} est_rows={est_rows} actual_rows={n} wall={ms}ms")
            c.rollback()

# RLS selectivity: planner estimate vs actual for the plain scan of the inner table
with e.connect() as c:
    ro(c)
    c.execute(sa.text("select set_config('cip.product_lines', 'NB', true)"))
    for q in ("select * from fact_inbound_shipment where tenant_id = 'default'",
              "select * from weeks_of_cover_observation",
              "select * from fact_inventory_distributor"):
        p = c.exec_driver_sql("EXPLAIN (ANALYZE, FORMAT JSON) " + q).scalar()[0]
        pl = p["Plan"]
        print(f"{q[:60]:60} est={pl['Plan Rows']} actual={pl['Actual Rows']} removed={pl.get('Rows Removed by Filter')}"
              f" exec={round(p['Execution Time'])}ms filter={re.sub(r'\s+', ' ', pl.get('Filter', ''))[:90]}")
