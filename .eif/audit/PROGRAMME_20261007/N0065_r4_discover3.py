"""N-0065 round 4 discovery 3, READ ONLY, app role cip, scope '*': plans for the current pick and
line inheritance by hash joins. Prints current_database() first; read only; 60 s timeout.
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

url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
eng = sa.create_engine(url, poolclass=NullPool, connect_args={
    "options": "-c default_transaction_read_only=on -c statement_timeout=60000", "prepare_threshold": None})

IDENT = """SELECT DISTINCT ON (r.line_identity_key) r.line_identity_key, r.product_id
  FROM shipment_evidence_observation r WHERE r.product_id IS NOT NULL
  ORDER BY r.line_identity_key, r.valid_from DESC NULLS LAST, r.id DESC"""

with eng.connect() as c:
    db = c.execute(sa.text("select current_database()")).scalar_one()
    print("current_database() =", db, "| read_only =", c.execute(sa.text("show transaction_read_only")).scalar_one())
    assert db == "cip"
    c.execute(sa.text("select set_config('cip.product_lines', '*', true)"))
    print("obs size/pages/allvisible:", c.execute(sa.text("""select pg_size_pretty(pg_total_relation_size('shipment_evidence_observation')),
        relpages, relallvisible from pg_class where relname='shipment_evidence_observation'""")).all())
    print("obs stats:", c.execute(sa.text("""select n_live_tup, n_dead_tup, last_vacuum, last_autovacuum, last_analyze, last_autoanalyze
        from pg_stat_user_tables where relname='shipment_evidence_observation'""")).all())
    print("work_mem:", c.execute(sa.text("show work_mem")).scalar())
    for label, sql in (
        ("current pick", """explain (analyze, buffers) select distinct on (line_identity_key) id from shipment_evidence_observation
            where superseded_by_id is null order by line_identity_key, valid_from desc nulls last, id desc"""),
        ("line inherit (hash)", f"""explain (analyze, buffers) select s.id, i.product_id from shipment_evidence_line s
            left join shipment_evidence_observation o on o.evidence_line_id = s.id
            left join ({IDENT}) i on i.line_identity_key = o.line_identity_key where s.product_id is null"""),
        ("view count '*'", "explain (analyze, buffers) select count(*) from shipment_evidence_current"),
    ):
        t0 = time.perf_counter()
        rows = c.execute(sa.text(sql)).all()
        print(f"--- {label} ({round((time.perf_counter()-t0)*1000)} ms)")
        for r in rows:
            print("   ", r[0])
    c.rollback()
eng.dispose()
