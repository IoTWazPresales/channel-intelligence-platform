"""Print one live shipment id whose receipt has a cancelled candidate. Ids only."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))
os.chdir(ROOT / "apps" / "api")

from sqlalchemy import text

from app.db.session_sync import SessionLocal


def main() -> None:
    with SessionLocal() as session:
        dbname = session.execute(text("SELECT current_database()")).scalar()
        print(f"database={dbname}")
        if dbname != "cip":
            print("receipt_id=none reason=wrong_database")
            return
        hit = session.execute(
            text(
                """
                WITH jobs AS (
                    SELECT delivery_no, operating_unit, import_job_id, MIN(valid_from) AS vf
                    FROM shipment_evidence_observation
                    WHERE COALESCE(btrim(delivery_no), '') <> ''
                    GROUP BY delivery_no, operating_unit, import_job_id
                ),
                latest AS (
                    SELECT DISTINCT ON (delivery_no, operating_unit)
                           delivery_no, operating_unit, import_job_id
                    FROM jobs
                    ORDER BY delivery_no, operating_unit, vf DESC, import_job_id DESC
                )
                SELECT s.delivery_no, s.operating_unit, COUNT(DISTINCT s.line_identity_key) AS vanished
                FROM shipment_evidence_observation s
                JOIN latest l
                  ON l.delivery_no = s.delivery_no
                 AND l.operating_unit IS NOT DISTINCT FROM s.operating_unit
                WHERE s.import_job_id <> l.import_job_id
                  AND NOT EXISTS (
                      SELECT 1
                      FROM shipment_evidence_observation n
                      WHERE n.delivery_no = s.delivery_no
                        AND n.operating_unit IS NOT DISTINCT FROM s.operating_unit
                        AND n.import_job_id = l.import_job_id
                        AND n.line_identity_key = s.line_identity_key
                  )
                GROUP BY s.delivery_no, s.operating_unit
                ORDER BY vanished DESC
                LIMIT 1
                """
            )
        ).first()
        if hit is None:
            print("receipt_id=none reason=no_vanished_delivery")
            return
        delivery_no, operating_unit, vanished = hit
        shipment_id = session.execute(
            text(
                """
                SELECT id
                FROM fact_inbound_shipment
                WHERE delivery_no = :delivery_no
                  AND operating_unit IS NOT DISTINCT FROM :operating_unit
                ORDER BY id
                LIMIT 1
                """
            ),
            {"delivery_no": delivery_no, "operating_unit": operating_unit},
        ).scalar()
        print(f"receipt_id={shipment_id or 'none'} vanished={int(vanished)}")
        if shipment_id:
            Path(__file__).with_name("receipt_target.txt").write_text(str(int(shipment_id)), encoding="utf-8")


if __name__ == "__main__":
    main()
