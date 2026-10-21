"""EXPLAIN ANALYZE (text) the slowest captured statement for one path, READ ONLY, 60 s timeout.

Run from apps/api with its venv:
  python N0065_r3_explain_one.py <capture.json> <label-substrings joined by +> [setting|None] [nestloop_off]
Prints current_database() first. No writes (default_transaction_read_only=on).
"""

import json
import sys

import sqlalchemy as sa
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

cap = json.load(open(sys.argv[1], encoding="utf-8"))
needles = sys.argv[2].split("+")
setting = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "None" else None
nestloop_off = len(sys.argv) > 4 and sys.argv[4] == "nestloop_off"
stmts = [s for s in cap["stmts"] if s.get("ms") is not None and all(n in (s["label"] or "") for n in needles)]
s = max(stmts, key=lambda x: x["ms"])
url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
eng = sa.create_engine(
    url,
    poolclass=NullPool,
    connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=60000", "prepare_threshold": None},
)
with eng.connect() as c:
    print("current_database() =", c.execute(sa.text("select current_database()")).scalar_one(),
          "| read_only =", c.execute(sa.text("show transaction_read_only")).scalar_one())
    print("captured ms:", s["ms"], "| setting:", setting, "| nestloop_off:", nestloop_off)
    if setting is not None:
        c.execute(sa.text("select set_config('cip.product_lines', :v, true)"), {"v": setting})
    if nestloop_off:
        c.execute(sa.text("set local enable_nestloop = off"))
    rows = c.exec_driver_sql("EXPLAIN (ANALYZE, COSTS ON, TIMING ON) " + s["sql"], s["params"] or {}).all()
    for (line,) in rows:
        print(line)
    c.rollback()
eng.dispose()
