"""Read-only: how the voyage headers appear in raw_source_row (type and sample values), per header.

    python -X utf8 -I .eif/audit/ON_THE_WATER_20261029/probe_water_samples.py <database>
"""
import sys

sys.path.insert(0, "apps/api")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402

db = sys.argv[1]
raw = make_url(get_settings().database_url_sync).set(database=db).render_as_string(hide_password=False)
engine = create_engine(sqlalchemy_sync_engine_url(raw))
HEADERS = ("On-Board Date", "ETA Date(Est Port Arrival)", "ATA Date(Actual Port Arrival)", "Container Number", "Shipway", "shipway")
with engine.connect() as c:
    c.execute(text("SET default_transaction_read_only = on"))
    for h in HEADERS:
        rows = c.execute(
            text(
                "SELECT jsonb_typeof(raw_source_row -> :h) t, count(*) n, min(raw_source_row ->> :h) lo, max(raw_source_row ->> :h) hi "
                "FROM shipment_evidence_line WHERE raw_source_row ? :h GROUP BY 1 ORDER BY 2 DESC"
            ),
            {"h": h},
        ).all()
        print(f"== {h!r}")
        for r in rows:
            print(f"   type={r.t} n={r.n} min={r.lo!r} max={r.hi!r}")
    # Any trigger on the three tables (append-only guards would block the backfill's UPDATE).
    for r in c.execute(
        text(
            "SELECT c.relname, t.tgname, t.tgenabled FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
            "WHERE NOT t.tgisinternal AND c.relname IN ('fact_inbound_shipment','shipment_evidence_line','shipment_evidence_observation')"
        )
    ):
        print("TRIGGER", tuple(r))
    for r in c.execute(
        text(
            "SELECT tablename, policyname, cmd FROM pg_policies "
            "WHERE tablename IN ('fact_inbound_shipment','shipment_evidence_line','shipment_evidence_observation') ORDER BY 1,2"
        )
    ):
        print("POLICY", tuple(r))
    print("RLS", [tuple(r) for r in c.execute(text("SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname IN ('fact_inbound_shipment','shipment_evidence_line','shipment_evidence_observation','port_condition')"))])
    c.rollback()
