"""N-0071 round 2: EXPLAIN (read-only) of the D-0065 line filter forms on cip. Prints current_database() first."""
from __future__ import annotations

import sys
import time

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.dialects import postgresql

from app.core.config import get_settings
from app.models.facts import FactInboundShipment as F
from app.services import shipment_strict_pair as ssp

url = get_settings().database_url_sync
for pre in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://"):
    if url.startswith(pre):
        url = "postgresql+psycopg://" + url[len(pre):]
        break

mode = sys.argv[1] if len(sys.argv) > 1 else "plan"
form = sys.argv[2] if len(sys.argv) > 2 else "keep"
if form == "keep":
    stmt = select(func.count()).select_from(F).where(F.tenant_id == "default", ssp.keep_counted_line(F))
else:  # remainder join, as the quantity readers use it
    twin = ssp.twin_remainder(F)
    stmt = select(func.count(), func.sum(twin.counted_quantity)).select_from(F).outerjoin(twin.subquery, twin.onclause).where(
        F.tenant_id == "default", twin.kept
    )
    if form in ("join_keep", "kpi"):
        stmt = stmt.where(ssp.keep_counted_line(F))
    if form == "kpi":  # as the shipping KPI tile: plus the current-incoming cohort
        from datetime import date

        from app.services.shipping_commercial_kpis import predicate_current_incoming

        stmt = stmt.where(predicate_current_incoming(date(2026, 10, 7)))
sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
with create_engine(url).connect() as conn:
    conn.execute(text("SET TRANSACTION READ ONLY"))
    print("current_database:", conn.execute(text("SELECT current_database()")).scalar())
    print("work_mem:", conn.execute(text("SHOW work_mem")).scalar())
    kw = "EXPLAIN (ANALYZE, BUFFERS)" if mode == "analyze" else "EXPLAIN"
    t = time.perf_counter()
    for (line,) in conn.execute(text(f"{kw} {sql}")).all():
        print(line)
    print("elapsed_s", round(time.perf_counter() - t, 2))
    conn.rollback()
