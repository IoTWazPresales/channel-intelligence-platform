#!/usr/bin/env python3
"""Run read-only PO↔lineup + shipment integrity audit (see data_integrity_audit module docstring)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.services.data_integrity_audit import format_summary_table, run_data_integrity_audit_sync
from app.services.imports.cip_db_identity import is_cip_application_database


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=None, help="Optional quarter filter e.g. 26Q2")
    parser.add_argument("--distributor-id", type=int, default=None, help="Optional distributor filter")
    parser.add_argument("--sample-limit", type=int, default=10, help="Max samples per check")
    parser.add_argument("--json-out", default=None, help="Write structured JSON report to path")
    args = parser.parse_args()

    with SessionLocal() as db:
        dbname = db.scalar(text("SELECT current_database()"))
        if not is_cip_application_database(str(dbname)):
            print(f"Refusing: current_database()={dbname!r} (expected cip/postgres)", file=sys.stderr)
            return 2
        print(f"current_database()={dbname}")
        report = run_data_integrity_audit_sync(
            db,
            period=args.period,
            distributor_id=args.distributor_id,
            sample_limit=args.sample_limit,
        )

    summary = format_summary_table(report)
    print(summary)

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
        print(f"\nJSON written: {out_path.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
