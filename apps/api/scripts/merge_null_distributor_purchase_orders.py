"""Preview-first merge of duplicate NULL-distributor purchase_order rows (Unit 2).

Dry-run by default; ``--confirm`` executes the merge plan. Warren runs against ``cip``.
"""
from __future__ import annotations

import argparse
import json

from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.services.imports.cip_db_identity import is_cip_application_database
from app.services.imports.shipment_null_distributor_po_merge import (
    execute_null_distributor_po_merge,
    merge_plan_to_dict,
    merge_summary_stats,
    plan_null_distributor_po_merges,
)


def run(*, dry_run: bool, limit: int | None, sample: int) -> dict:
    out: dict = {}
    with SessionLocal() as db:
        dbname = db.scalar(text("SELECT current_database()"))
        if not is_cip_application_database(str(dbname)):
            raise SystemExit(f"Refusing: current_database()={dbname!r}")

        out["before"] = merge_summary_stats(db)
        plans = plan_null_distributor_po_merges(db)
        if limit is not None:
            plans = plans[: int(limit)]
        out["groups_planned"] = len(plans)
        out["losers_to_delete"] = sum(len(g.loser_ids) for g in plans)
        out["sample_plans"] = [merge_plan_to_dict(g) for g in plans[:sample]]

        if dry_run:
            return out

        totals = {
            "losers_deleted": 0,
            "evidence_lines_updated": 0,
            "facts_updated": 0,
            "observations_updated": 0,
            "case_links_updated": 0,
            "case_links_deduped": 0,
        }
        for group in plans:
            stats = execute_null_distributor_po_merge(db, group)
            for k, v in stats.items():
                totals[k] = totals.get(k, 0) + int(v)
        db.commit()
        out["execute"] = totals
        out["after"] = merge_summary_stats(db)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--confirm", action="store_true", help="Execute merge (default preview only)")
    p.add_argument("--limit", type=int, default=None, help="Cap number of norm groups merged")
    p.add_argument("--sample", type=int, default=10, help="Preview sample size in output")
    args = p.parse_args()
    result = run(dry_run=not args.confirm, limit=args.limit, sample=max(0, int(args.sample)))
    mode = "CONFIRM" if args.confirm else "DRY-RUN"
    print(f"[{mode}] merge_null_distributor_purchase_orders")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
