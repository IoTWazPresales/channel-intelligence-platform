"""N-0065 round 4: READ ONLY timing of the 0026 helpers on cip (app role). Prints current_database() first."""
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

url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
eng = sa.create_engine(url, poolclass=NullPool, connect_args={
    "options": "-c default_transaction_read_only=on -c statement_timeout=60000", "prepare_threshold": None})
SETTING = "select current_setting('cip.product_lines', true)"
with eng.connect() as c:
    print("current_database() =", c.execute(sa.text("select current_database()")).scalar_one(),
          "| read_only =", c.execute(sa.text("show transaction_read_only")).scalar_one())
    c.execute(sa.text("select set_config('cip.product_lines', 'NB', true)"))
    for fn in ("cip_sev_current_observation_ids", "cip_sev_observation_lineage", "cip_sev_line_lineage",
               "cip_inbound_shipment_lineage"):
        best = None
        for _ in range(3):
            t0 = time.perf_counter()
            n = c.execute(sa.text(f"select count(*) from public.{fn}()")).scalar_one()
            ms = (time.perf_counter() - t0) * 1000
            best = ms if best is None else min(best, ms)
        print(f"{fn:34} rows={n:6} best of 3 {round(best)} ms; setting after = {c.execute(sa.text(SETTING)).scalar()!r}")
    c.execute(sa.text("select set_config('cip.product_lines', '*', true)"))
    rows = c.execute(sa.text(
        "explain (analyze, buffers) select distinct on (line_identity_key) id from shipment_evidence_observation "
        "where superseded_by_id is null order by line_identity_key, valid_from desc nulls last, id desc")).all()
    print("--- pick inner query plan ('*')")
    for r in rows:
        print("   ", r[0])
    # Candidate fixes, measured with SET LOCAL inside this READ ONLY transaction (nothing persists).
    for label, setting in (("work_mem=32MB", "set local work_mem = '32MB'"),
                           ("enable_sort=off (index order, diagnostic)", "set local enable_sort = off")):
        c.execute(sa.text("reset work_mem"))
        c.execute(sa.text("reset enable_sort"))
        c.execute(sa.text(setting))
        best = None
        plan = None
        for _ in range(3):
            plan = c.execute(sa.text(
                "explain (analyze) select distinct on (line_identity_key) id from shipment_evidence_observation "
                "where superseded_by_id is null order by line_identity_key, valid_from desc nulls last, id desc")).all()
            ms = float(plan[-1][0].split(":")[1].split()[0])
            best = ms if best is None else min(best, ms)
        print(f"--- {label}: best of 3 {round(best)} ms; top nodes:", [p[0].strip()[:90] for p in plan[:3]])
    c.rollback()
eng.dispose()
