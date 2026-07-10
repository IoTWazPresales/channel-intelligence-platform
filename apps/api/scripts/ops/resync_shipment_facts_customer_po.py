"""Re-sync fact_inbound_shipment PO fields from evidence after backfill (facts upsert only)."""
from __future__ import annotations

import argparse

from sqlalchemy import select, text

from app.db.session_sync import SessionLocal
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.cip_db_identity import is_cip_application_database
from app.services.imports.shipment_inbound_facts import upsert_inbound_shipment_facts_for_job


def run(*, dry_run: bool) -> dict[str, int]:
    stats = {"jobs": 0, "facts_before_po": 0, "facts_after_po": 0, "rows_upserted": 0}
    with SessionLocal() as db:
        dbname = db.scalar(text("SELECT current_database()"))
        if not is_cip_application_database(str(dbname)):
            raise SystemExit(f"Refusing: current_database()={dbname!r}")

        stats["facts_before_po"] = int(
            db.scalar(text("SELECT count(*) FROM fact_inbound_shipment WHERE customer_po IS NOT NULL")) or 0
        )
        job_ids = [
            int(x)
            for x in db.scalars(
                select(ShipmentEvidenceLine.import_job_id)
                .where(ShipmentEvidenceLine.customer_po.is_not(None))
                .distinct()
                .order_by(ShipmentEvidenceLine.import_job_id)
            ).all()
        ]
        stats["jobs"] = len(job_ids)
        if dry_run:
            return stats

        for jid in job_ids:
            n = upsert_inbound_shipment_facts_for_job(db, jid)
            stats["rows_upserted"] += int(n)
        db.commit()
        stats["facts_after_po"] = int(
            db.scalar(text("SELECT count(*) FROM fact_inbound_shipment WHERE customer_po IS NOT NULL")) or 0
        )
    return stats


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--confirm", action="store_true", help="Run upsert (default dry-run)")
    args = p.parse_args()
    stats = run(dry_run=not args.confirm)
    mode = "CONFIRM" if args.confirm else "DRY-RUN"
    print(f"[{mode}] resync_shipment_facts_customer_po")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
