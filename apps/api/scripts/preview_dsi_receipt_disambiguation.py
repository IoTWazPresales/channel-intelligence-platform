"""Dry-run receipt disambiguation tier counts for a DSI import job.

Usage::

  node scripts/run-api-python.cjs scripts/preview_dsi_receipt_disambiguation.py --job-id 43
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
    preview_receipt_disambiguation_for_staging_rows,
)
from app.services.imports.provisional_entity_consolidation import build_distributor_id_to_canonical_key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", type=int, required=True)
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
        out = preview_receipt_disambiguation_for_staging_rows(
            db, import_job_id=int(args.job_id), receipt_index=idx, dist_id_to_canonical=dist_map
        )
        print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
