"""Read-only: which import jobs carry shipment evidence, their saved mapping, and the raw headers.

    python -I .eif/audit/ON_THE_WATER_20261029/probe_shipment_jobs.py <database>
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
WANT = ("on-board", "on board", "eta", "ata", "shipping method", "ship way", "shipway", "deliver port", "currency", "container")
with engine.connect() as c:
    c.execute(text("SET default_transaction_read_only = on"))
    print("==", db, c.execute(text("select version_num from alembic_version")).scalar())
    jobs = c.execute(
        text(
            """
            SELECT j.id, j.file_name, j.status, j.created_at::date AS d,
                   (SELECT count(*) FROM shipment_evidence_line l WHERE l.import_job_id = j.id) AS lines,
                   (SELECT count(*) FROM shipment_evidence_observation o WHERE o.import_job_id = j.id) AS obs,
                   (SELECT count(*) FROM fact_inbound_shipment f WHERE f.import_job_id = j.id) AS facts,
                   j.field_mapping IS NOT NULL AS has_map
            FROM import_job j
            WHERE EXISTS (SELECT 1 FROM shipment_evidence_line l WHERE l.import_job_id = j.id)
               OR EXISTS (SELECT 1 FROM shipment_evidence_observation o WHERE o.import_job_id = j.id)
            ORDER BY j.id
            """
        )
    ).all()
    print("jobs with shipment evidence:", len(jobs))
    for r in jobs[-25:]:
        print(f"  job {r.id} {r.d} {r.status} lines={r.lines} obs={r.obs} facts={r.facts} map={r.has_map} {r.file_name}")
    # Headers that look like the new fields, over all lines (distinct key counts).
    keys = c.execute(
        text(
            """
            SELECT k, count(*) n FROM shipment_evidence_line l, LATERAL jsonb_object_keys(l.raw_source_row) k
            GROUP BY k ORDER BY n DESC
            """
        )
    ).all()
    print("raw_source_row keys that match the new fields:")
    for k, n in keys:
        if any(w in k.lower() for w in WANT):
            print(f"  {n:>8}  {k!r}")
    c.rollback()
