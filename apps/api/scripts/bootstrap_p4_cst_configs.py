"""Bootstrap placeholder customer_report_config rows for the customers named on the command line.

Dry-run by default (prints what would change, rolls back). Warren runs with
--confirm to commit. Idempotent — safe to re-run. The customer list is an input;
ids that are not a dim_customer of the tenant are reported, and any customer whose
config already has richer structure (real `report_structure_type` or
`feed_profile_json.vat_basis`) is skipped, never overwritten.

Usage (from apps/api, venv activated):
    python scripts/bootstrap_p4_cst_configs.py --customer-id 101 --customer-id 102
        (dry-run)
    python scripts/bootstrap_p4_cst_configs.py --customer-id 101 --customer-id 102 --confirm
        (write)
"""

from __future__ import annotations

import argparse
import json

from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.services.imports.cip_db_identity import is_cip_application_database
from app.services.imports.cst_p4_customer_bootstrap import bootstrap_p4_customer_configs


def run(*, customer_ids: list[int], tenant_id: str | None, confirm: bool) -> dict:
    with SessionLocal() as db:
        dbname = db.scalar(text("SELECT current_database()"))
        if not is_cip_application_database(str(dbname)):
            raise SystemExit(f"Refusing: current_database()={dbname!r} is not CIP")

        result = bootstrap_p4_customer_configs(db, customer_ids, tenant_id=tenant_id)

        if confirm:
            db.commit()
        else:
            db.rollback()
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--customer-id",
        dest="customer_ids",
        type=int,
        action="append",
        required=True,
        help="dim_customer id to bootstrap (repeat for each customer).",
    )
    parser.add_argument(
        "--tenant",
        default=None,
        help="Tenant the customers must belong to (default tenant when omitted).",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Write changes (default is dry-run: rolls back after preview).",
    )
    args = parser.parse_args(argv)
    result = run(
        customer_ids=list(args.customer_ids),
        tenant_id=args.tenant,
        confirm=bool(args.confirm),
    )
    mode = "CONFIRM" if args.confirm else "DRY-RUN"
    print(f"[{mode}] bootstrap_p4_cst_configs")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
