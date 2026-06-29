"""Preview-first merge of NULL-distributor PO rows into distributor-set siblings (Unit 2b).

Dry-run by default; ``--confirm`` executes the merge plan. Warren runs against ``cip``.
"""
from __future__ import annotations

import argparse
import json

from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.services.imports.cip_db_identity import is_cip_application_database
from app.services.imports.shipment_null_distributor_sibling_po_merge import (
    execute_null_distributor_sibling_po_merge,
    plan_null_distributor_sibling_po_merges,
    sibling_merge_plan_to_dict,
    sibling_merge_skip_to_dict,
    sibling_merge_summary_stats,
)


def run(*, dry_run: bool, limit: int | None, sample: int) -> dict:
    out: dict = {}
    with SessionLocal() as db:
        dbname = db.scalar(text("SELECT current_database()"))
        if not is_cip_application_database(str(dbname)):
            raise SystemExit(f"Refusing: current_database()={dbname!r}")

        out["before"] = sibling_merge_summary_stats(db)
        plans, skipped = plan_null_distributor_sibling_po_merges(db)
        if limit is not None:
            plans = plans[: int(limit)]
        out["groups_mergeable"] = len(plans)
        out["groups_skipped"] = len(skipped)
        out["losers_to_delete"] = sum(len(g.loser_ids) for g in plans)
        out["skipped_ambiguous"] = sum(1 for s in skipped if s.reason.startswith("ambiguous_"))
        out["skipped_unsafe"] = sum(1 for s in skipped if s.reason.startswith("unsafe_"))
        out["sample_plans"] = [sibling_merge_plan_to_dict(g) for g in plans[:sample]]
        out["sample_skipped"] = [sibling_merge_skip_to_dict(s) for s in skipped[:sample]]

        if dry_run:
            return out

        totals = {
            "losers_deleted": 0,
            "evidence_lines_updated": 0,
            "facts_updated": 0,
            "observations_updated": 0,
            "case_links_updated": 0,
            "case_links_deduped": 0,
            "dismiss_rows_updated": 0,
        }
        for group in plans:
            stats = execute_null_distributor_sibling_po_merge(db, group)
            for k, v in stats.items():
                totals[k] = totals.get(k, 0) + int(v)
        db.commit()
        out["execute"] = totals
        out["after"] = sibling_merge_summary_stats(db)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--confirm", action="store_true", help="Execute merge (default preview only)")
    p.add_argument("--limit", type=int, default=None, help="Cap number of norm groups merged")
    p.add_argument("--sample", type=int, default=10, help="Preview sample size in output")
    args = p.parse_args()
    result = run(dry_run=not args.confirm, limit=args.limit, sample=max(0, int(args.sample)))
    mode = "CONFIRM" if args.confirm else "DRY-RUN"
    print(f"[{mode}] merge_null_distributor_sibling_purchase_orders")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
