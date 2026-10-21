"""N-0065 round 4 discovery 2, READ ONLY, app role cip, scope '*'. Timings of candidate helper bodies.

Prints current_database() first; default_transaction_read_only=on, statement_timeout 60 s.
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

IDENT_LATEST = """
  SELECT DISTINCT ON (r.line_identity_key) r.line_identity_key, r.product_id
  FROM shipment_evidence_observation r WHERE r.product_id IS NOT NULL
  ORDER BY r.line_identity_key, r.valid_from DESC NULLS LAST, r.id DESC"""

CANDIDATES = {
    "current_ids": """select count(*) from (select distinct on (line_identity_key) id from shipment_evidence_observation
        where superseded_by_id is null order by line_identity_key, valid_from desc nulls last, id desc) x""",
    "obs_inherit_cte": f"""select count(*), count(i.product_id) from shipment_evidence_observation o
        left join ({IDENT_LATEST}) i on i.line_identity_key = o.line_identity_key where o.product_id is null""",
    "obs_inherit_lateral": """select count(*), count(i.product_id) from shipment_evidence_observation o
        left join lateral (select r.product_id from shipment_evidence_observation r
           where r.line_identity_key = o.line_identity_key and r.product_id is not null
           order by r.valid_from desc nulls last, r.id desc limit 1) i on true where o.product_id is null""",
    "line_inherit_lateral": """select count(*), count(i.product_id) from shipment_evidence_line s
        left join lateral (select r.product_id from shipment_evidence_observation o
           join shipment_evidence_observation r on r.line_identity_key = o.line_identity_key and r.product_id is not null
           where o.evidence_line_id = s.id
           order by r.valid_from desc nulls last, r.id desc limit 1) i on true where s.product_id is null""",
    "inbound_null_inherit": """select count(*), count(f.shipment_evidence_line_id), count(i.product_id) from fact_inbound_shipment f
        left join lateral (select r.product_id from shipment_evidence_observation o
           join shipment_evidence_observation r on r.line_identity_key = o.line_identity_key and r.product_id is not null
           where o.evidence_line_id = f.shipment_evidence_line_id
           order by r.valid_from desc nulls last, r.id desc limit 1) i on true where f.product_id is null""",
}

with eng.connect() as c:
    db = c.execute(sa.text("select current_database()")).scalar_one()
    print("current_database() =", db, "| read_only =", c.execute(sa.text("show transaction_read_only")).scalar_one())
    assert db == "cip"
    c.execute(sa.text("select set_config('cip.product_lines', '*', true)"))
    print("line_identity_key nullable:", c.execute(sa.text("""select is_nullable from information_schema.columns
        where table_name='shipment_evidence_observation' and column_name='line_identity_key'""")).scalar())
    print("null keys:", c.execute(sa.text("select count(*) from shipment_evidence_observation where line_identity_key is null")).scalar())
    for name, sql in CANDIDATES.items():
        best = None
        for _ in range(3):
            t0 = time.perf_counter()
            res = c.execute(sa.text(sql)).all()
            ms = (time.perf_counter() - t0) * 1000
            best = ms if best is None else min(best, ms)
        print(f"{name:24} {res} best of 3: {round(best)} ms")
    # inbound: null-product rows with an evidence line whose line is resolved / unresolved
    print("inbound null rows by evidence-line product:", c.execute(sa.text("""select (s.product_id is not null) as line_resolved, count(*)
        from fact_inbound_shipment f left join shipment_evidence_line s on s.id = f.shipment_evidence_line_id
        where f.product_id is null group by 1""")).all())
    print("inbound fk to evidence line?", c.execute(sa.text("""select conname, pg_get_constraintdef(oid) from pg_constraint
        where conrelid='fact_inbound_shipment'::regclass and contype='f'""")).all())
    c.rollback()
eng.dispose()
