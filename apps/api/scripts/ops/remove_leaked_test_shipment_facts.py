"""Remove the leaked test facts ``AUD-PARI-*`` from ``fact_inbound_shipment`` (GOV-008 review 2 Nov, minor).

``tests/test_data_integrity_audit.py`` once wrote shipped facts whose item code is ``AUD-PARI-<token>`` into the real table and
left them there: no import job, report type ``shipped``, 30 units in three facts (ids 99964, 99966, 99968 on ``cip`` on
2 November 2026). The one-off open-book close then turned them into open orders, so they count in open units.

DRY RUN IS THE DEFAULT. A dry run is one READ ONLY transaction and prints what would be removed.

    python apps/api/scripts/ops/remove_leaked_test_shipment_facts.py --expect-db cip_pari
    python apps/api/scripts/ops/remove_leaked_test_shipment_facts.py --expect-db cip_pari --apply --expect-count 3

``--apply`` needs ``--expect-db`` equal to ``current_database()`` and ``--expect-count`` equal to the number of facts matched
(default 3). It refuses when anything else points at one of the facts. It writes ONE platform audit event that holds each
removed row in full (so a row can be put back by hand), then deletes exactly those rows, in one transaction.

NOT RUN on ``cip`` by the batch-2 session. Plan: ``.eif/audit/REVIEW_20261102/batch2/AUD_PARI_CLEANUP_PLAN.md`` (clone first).
Selection (all must hold): ``item_code LIKE 'AUD-PARI-%'``, ``import_job_id IS NULL``, ``shipment_evidence_line_id IS NULL``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[2]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

_SELECT = """
SELECT * FROM fact_inbound_shipment
WHERE item_code LIKE 'AUD-PARI-%'
  AND import_job_id IS NULL
  AND shipment_evidence_line_id IS NULL
ORDER BY id
"""


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def find_leaked(db: Session) -> list[dict[str, Any]]:
    return [{k: _jsonable(v) for k, v in row.items()} for row in db.execute(text(_SELECT)).mappings().all()]


def execute(db: Session, *, expect_db: str, apply: bool, expect_count: int = 3) -> dict[str, Any]:
    """Dry run, or apply, inside the caller's session. The caller commits (the CLI does; a test rolls back)."""
    current = str(db.scalar(text("SELECT current_database()")))
    if current != expect_db:
        raise SystemExit(f"refusing: current_database() is {current!r}, expected {expect_db!r}")
    if apply and current in ("",):
        raise SystemExit("refusing: no database name")
    if not apply:
        db.execute(text("SET TRANSACTION READ ONLY"))
    rows = find_leaked(db)
    ids = [int(r["id"]) for r in rows]
    result: dict[str, Any] = {
        "database": current,
        "apply": apply,
        "matched": len(rows),
        "units": float(sum(float(r.get("quantity") or 0) for r in rows)),
        "ids": ids,
        "line_states": sorted({str(r.get("line_state")) for r in rows}),
        "rows": [
            {"id": r["id"], "item_code": r["item_code"], "line_state": r["line_state"], "quantity": r["quantity"], "report_type": r["report_type"]}
            for r in rows
        ],
    }
    if not apply:
        return result
    if len(rows) != expect_count:
        raise SystemExit(f"refusing: matched {len(rows)} fact(s), --expect-count says {expect_count}")
    pointed_at = db.scalar(
        text("SELECT count(*) FROM fact_inbound_shipment WHERE superseded_by_fact_id = ANY(:ids)"), {"ids": ids}
    )
    if pointed_at:
        raise SystemExit(f"refusing: {pointed_at} other fact(s) point at these facts (superseded_by_fact_id)")
    from app.models.platform_audit import PlatformAuditEvent

    db.add(
        PlatformAuditEvent(
            tenant_id=str(rows[0].get("tenant_id") or "default") if rows else "default",
            actor="scripts/ops/remove_leaked_test_shipment_facts.py",
            area="admin",
            action="leaked_test_shipment_facts_removed",
            target_type="fact_inbound_shipment",
            target_id=",".join(str(i) for i in ids),
            detail_json={"database": current, "count": len(rows), "units": result["units"], "removed_rows": rows},
        )
    )
    db.flush()
    deleted = db.execute(text("DELETE FROM fact_inbound_shipment WHERE id = ANY(:ids)"), {"ids": ids}).rowcount
    if deleted != len(rows):
        raise SystemExit(f"ROLLED BACK by the caller: deleted {deleted}, expected {len(rows)}")
    result["deleted"] = int(deleted)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--expect-db", required=True, help="Abort unless current_database() matches")
    parser.add_argument("--apply", action="store_true", help="Delete the matched facts. Default is a read-only dry run")
    parser.add_argument("--expect-count", type=int, default=3, help="With --apply: abort unless exactly this many facts match")
    args = parser.parse_args(argv)
    from app.db.session_sync import SessionLocal

    with SessionLocal() as db:
        try:
            result = execute(db, expect_db=args.expect_db.strip(), apply=bool(args.apply), expect_count=int(args.expect_count))
            if args.apply:
                db.commit()
            else:
                db.rollback()
        except BaseException:
            db.rollback()
            raise
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
