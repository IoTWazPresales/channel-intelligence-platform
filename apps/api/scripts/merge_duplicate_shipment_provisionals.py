"""One-off cleanup: merge duplicate TMP-CUST provisional customers with the same normalised name.

Usage (from repo root, same env as API / Alembic):

  node scripts/run-api-python.cjs scripts/merge_duplicate_shipment_provisionals.py
  node scripts/run-api-python.cjs scripts/merge_duplicate_shipment_provisionals.py --apply

Without ``--apply``, prints ``current_database()`` and a dry-run plan only.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

from app.db.session_sync import SessionLocal, sync_engine
from app.services.imports.cip_db_identity import is_cip_application_database
from app.services.imports.shipment_evidence_steward_ops import merge_duplicate_shipment_provisional_customers_by_display_name


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Execute merge (default is dry-run only)")
    args = parser.parse_args()

    with sync_engine.connect() as conn:
        dbname = conn.execute(text("select current_database()")).scalar_one()
    print(f"current_database={dbname!r}")
    if not is_cip_application_database(str(dbname)):
        print("Refusing to run: expected CIP application database (cip or postgres).", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        preview = merge_duplicate_shipment_provisional_customers_by_display_name(db, dry_run=True)
        print("Dry-run planned_merges (merge_group_count=%s):" % preview.get("merge_group_count"))
        for m in preview.get("planned_merges") or []:
            print(
                f"  keeper_id={m['keeper_id']} code={m['keeper_code']!r} name={m['keeper_name']!r} "
                f"merge_loser_ids={m['loser_ids']}"
            )

        if not args.apply:
            print("No changes made (pass --apply to execute merge).")
            return 0

        out = merge_duplicate_shipment_provisional_customers_by_display_name(db, dry_run=False)
        print("Applied. deleted_customer_ids:", out.get("deleted_customer_ids"))
        print("skipped:", out.get("skipped"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
