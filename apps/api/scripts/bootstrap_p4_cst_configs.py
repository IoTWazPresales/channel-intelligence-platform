"""P4 — bootstrap placeholder customer_report_config rows for the remaining CST pilot roster.

Dry-run by default (prints what would change, rolls back). Warren runs with
--confirm to commit. Idempotent — safe to re-run; never touches Takealot
(customer_id=20) or any customer row that already has a richer config (real
`report_structure_type` or `feed_profile_json.vat_basis`).

Usage (from apps/api, venv activated):
    python scripts/bootstrap_p4_cst_configs.py            # dry-run
    python scripts/bootstrap_p4_cst_configs.py --confirm  # write
"""

from __future__ import annotations

import argparse
import json

from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.services.imports.cip_db_identity import is_cip_application_database
from app.services.imports.cst_p4_customer_bootstrap import bootstrap_p4_customer_configs


def run(*, confirm: bool) -> dict:
    with SessionLocal() as db:
        dbname = db.scalar(text("SELECT current_database()"))
        if not is_cip_application_database(str(dbname)):
            raise SystemExit(f"Refusing: current_database()={dbname!r} is not CIP")

        result = bootstrap_p4_customer_configs(db)

        if confirm:
            db.commit()
        else:
            db.rollback()
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write changes (default is dry-run: rolls back after preview).",
    )
    args = parser.parse_args(argv)
    result = run(confirm=bool(args.confirm))
    mode = "CONFIRM" if args.confirm else "DRY-RUN"
    print(f"[{mode}] bootstrap_p4_cst_configs")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
