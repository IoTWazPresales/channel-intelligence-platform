import os
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[3] / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)

from sqlalchemy import text
from app.db.session_sync import SessionLocal
from app.api.v1.endpoints.shipping import _receipt_cancelled

with SessionLocal() as session:
    db = session.execute(text("SELECT current_database()")).scalar()
    if db != "cip":
        raise SystemExit("refusing non-cip")
    row = session.execute(
        text(
            """
            SELECT operating_unit, delivery_no, count(DISTINCT import_job_id) AS jobs
            FROM shipment_evidence_observation
            WHERE delivery_no IS NOT NULL AND btrim(delivery_no) <> ''
            GROUP BY operating_unit, delivery_no
            HAVING count(DISTINCT import_job_id) > 1
            ORDER BY jobs DESC
            LIMIT 1
            """
        )
    ).first()
print(f"database={db} multi_job_sample={'yes' if row else 'no'} jobs={row[2] if row else 0}")
if row:
    missing, events = _receipt_cancelled(
        group="delivery",
        operating_unit=row[0],
        delivery_no=row[1],
        order_no=None,
    )
    print(f"missing={len(missing)} events={len(events)}")
with SessionLocal() as session:
    vanished = session.execute(
        text(
            """
            WITH job_time AS (
              SELECT operating_unit, delivery_no, import_job_id, min(valid_from) AS vf
              FROM shipment_evidence_observation
              WHERE delivery_no IS NOT NULL AND btrim(delivery_no) <> ''
              GROUP BY operating_unit, delivery_no, import_job_id
            ),
            latest AS (
              SELECT DISTINCT ON (operating_unit, delivery_no)
                     operating_unit, delivery_no, import_job_id
              FROM job_time
              ORDER BY operating_unit, delivery_no, vf DESC, import_job_id DESC
            )
            SELECT count(*) FROM (
              SELECT DISTINCT o.operating_unit, o.delivery_no, o.line_identity_key
              FROM shipment_evidence_observation o
              JOIN latest l
                ON l.operating_unit IS NOT DISTINCT FROM o.operating_unit
               AND l.delivery_no = o.delivery_no
              WHERE o.import_job_id <> l.import_job_id
                AND NOT EXISTS (
                  SELECT 1 FROM shipment_evidence_observation n
                  WHERE n.import_job_id = l.import_job_id
                    AND n.line_identity_key = o.line_identity_key
                    AND n.operating_unit IS NOT DISTINCT FROM o.operating_unit
                    AND n.delivery_no = o.delivery_no
                )
            ) gone
            """
        )
    ).scalar()
    print(f"vanished_line_shipments_keys={vanished}")
