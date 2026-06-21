"""Resolve approved customer alias scope conflicts (Unit 2b).

Usage::

  node scripts/run-api-python.cjs scripts/resolve_customer_alias_scope_conflicts.py
  node scripts/run-api-python.cjs scripts/resolve_customer_alias_scope_conflicts.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import text

from app.db.session_sync import SessionLocal, sync_engine
from app.services.imports.cip_db_identity import is_cip_application_database
from app.services.imports.provisional_entity_consolidation import resolve_approved_customer_alias_scope_conflicts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    with sync_engine.connect() as conn:
        dbname = conn.execute(text("select current_database()")).scalar_one()
    print(f"current_database={dbname!r}")
    if not is_cip_application_database(str(dbname)):
        print("Refusing: expected CIP application database (cip or postgres).", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        preview = resolve_approved_customer_alias_scope_conflicts(db, dry_run=True)
        print(json.dumps(preview, indent=2, default=str))
        if not args.apply:
            print("No changes made (pass --apply to execute).")
            return 0
        out = resolve_approved_customer_alias_scope_conflicts(db, dry_run=False)
        print("Applied:", json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
