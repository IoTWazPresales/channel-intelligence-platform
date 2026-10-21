"""N-0071 read-only: table size and timing of the strict-pair predicate. SELECT only."""
from __future__ import annotations

import time

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.services.shipment_strict_pair import OPEN_HAS_SHIPPED_TWIN_SQL as TWIN

url = get_settings().database_url_sync
if url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://"):]
eng = create_engine(url)
with eng.connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    c.execute(text("SET LOCAL statement_timeout = '60s'"))
    print("current_database =", c.execute(text("SELECT current_database()")).scalar(), flush=True)
    print("rows/open/shipped =", c.execute(text(
        "SELECT count(*), count(*) FILTER (WHERE lower(line_state)='open_order'), "
        "count(*) FILTER (WHERE lower(line_state)='shipped') FROM fact_inbound_shipment")).one(), flush=True)
    t = time.time()
    r = c.execute(text(
        f"SELECT count(*), coalesce(sum(quantity),0) FROM fact_inbound_shipment "
        f"WHERE lower(line_state)='open_order' AND {TWIN}")).one()
    print("strict_pair_open rows, qty =", r, "seconds", round(time.time() - t, 2), flush=True)
    c.rollback()
