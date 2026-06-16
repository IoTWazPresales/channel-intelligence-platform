"""Apply Unit 4 cross-distributor misassignment corrections for a DSI job.

Usage::

  node scripts/run-api-python.cjs scripts/apply_dsi_cross_distributor_misassignments.py --job-id 43
  node scripts/run-api-python.cjs scripts/apply_dsi_cross_distributor_misassignments.py --job-id 43 --apply
"""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import text

from app.db.session_sync import SessionLocal, sync_engine
from app.services.imports.cip_db_identity import is_cip_application_database
from app.services.imports.dsi_distributor_receipt_disambiguation import (
    DistributorReceiptProductIndex,
    apply_cross_distributor_misassignment_corrections,
)
from app.services.imports.provisional_entity_consolidation import build_distributor_id_to_canonical_key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", type=int, required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist corrections (default is dry-run only).",
    )
    args = parser.parse_args()

    with sync_engine.connect() as conn:
        dbname = conn.execute(text("select current_database()")).scalar_one()
    print(f"current_database={dbname!r}")
    if not is_cip_application_database(str(dbname)):
        print("Refusing: expected CIP application database (cip or postgres).", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        dist_map = build_distributor_id_to_canonical_key(db)
        idx = DistributorReceiptProductIndex.load(db, dist_map)
        out = apply_cross_distributor_misassignment_corrections(
            db,
            import_job_id=int(args.job_id),
            receipt_index=idx,
            dist_id_to_canonical=dist_map,
            dry_run=not bool(args.apply),
        )
        print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
