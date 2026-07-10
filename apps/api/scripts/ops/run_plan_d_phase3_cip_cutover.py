#!/usr/bin/env python3
"""Plan D phase 3 on cip: soft-supersede legacy dupes + integrity audit gate."""
from __future__ import annotations

import json
import sys

from sqlalchemy import text

from app.core.feature_flags import shipment_bitemporal_read_enabled
from app.db.session_sync import SessionLocal
from app.services.data_integrity_audit import format_summary_table, run_data_integrity_audit_sync
from app.services.imports.shipment_plan_d_cutover import (
    assert_database_is,
    soft_supersede_legacy_duplicate_evidence,
)


def main() -> int:
    from app.core.config import get_settings

    settings = get_settings()
    print(f"DATABASE_URL_SYNC resolves to DB: {settings.database_url_sync.split('/')[-1]}")

    with SessionLocal() as db:
        assert_database_is(db, "cip")
        print(f"read_enabled: {shipment_bitemporal_read_enabled()}")

        supersede = soft_supersede_legacy_duplicate_evidence(db, dry_run=False)
        print("soft_supersede:", json.dumps(supersede, indent=2))
        db.commit()

        report = run_data_integrity_audit_sync(db, sample_limit=15)
        print(format_summary_table(report))

        dupes = next(c for c in report.checks if c.check == "evidence_true_dupes")
        parity = next(c for c in report.checks if c.check == "evidence_fact_parity")

        if dupes.count != 0:
            print(f"GATE FAIL: evidence_true_dupes (5b) = {dupes.count}", file=sys.stderr)
            return 1

        view_ok = db.scalar(text("SELECT count(*) FROM shipment_evidence_current")) is not None
        if not view_ok:
            print("GATE FAIL: shipment_evidence_current not readable", file=sys.stderr)
            return 1

        print(f"Phase 3 gate: 5b=0, parity findings={parity.count} (254 fact-mismatch worklist expected)")
        print("Phase 3 cip cutover: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
