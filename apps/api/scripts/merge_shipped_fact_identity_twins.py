"""Preview-first collapse of shipped fact twins from invoice_line source_key drift.

Dry-run by default; ``--confirm`` executes clean 1:1 merges only. Warren runs against ``cip``.
Run after migration ``20260630_0060`` (``fact_upsert_key`` backfill) and before ``0061`` (unique swap)
if duplicates remain.
"""
from __future__ import annotations

import argparse
import json

from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.services.imports.cip_db_identity import is_cip_application_database
from app.services.imports.shipment_shipped_fact_identity_twin_merge import (
    amazon_po_shipped_stats,
    execute_shipped_fact_identity_twin_merge,
    plan_shipped_fact_identity_twin_merges,
    shipped_fact_twin_plan_to_dict,
    shipped_fact_twin_skip_to_dict,
    shipped_fact_twin_summary_stats,
    twin_blast_radius,
)


def run(*, dry_run: bool, limit: int | None, sample: int) -> dict:
    out: dict = {}
    with SessionLocal() as db:
        dbname = db.scalar(text("SELECT current_database()"))
        if not is_cip_application_database(str(dbname)):
            raise SystemExit(f"Refusing: current_database()={dbname!r}")

        out["before"] = shipped_fact_twin_summary_stats(db)
        out["amazon_before"] = amazon_po_shipped_stats(db, "PURMIDR26009978", 26)
        plans, skipped = plan_shipped_fact_identity_twin_merges(db)
        if limit is not None:
            plans = plans[: int(limit)]

        out["blast_radius"] = twin_blast_radius(db, plans, skipped)
        out["bucket_counts"] = {
            "clean": len(plans),
            "split": sum(1 for s in skipped if s.bucket == "split"),
            "non_reconciling": sum(1 for s in skipped if s.bucket == "non_reconciling"),
        }
        out["losers_to_delete"] = sum(len(g.loser_ids) for g in plans)
        out["sample_clean"] = [shipped_fact_twin_plan_to_dict(g) for g in plans[:sample]]
        out["sample_split"] = [
            shipped_fact_twin_skip_to_dict(s) for s in skipped if s.bucket == "split"
        ][:sample]
        out["sample_non_reconciling"] = [
            shipped_fact_twin_skip_to_dict(s) for s in skipped if s.bucket == "non_reconciling"
        ][:sample]
        out["amazon_split"] = [
            shipped_fact_twin_skip_to_dict(s)
            for s in skipped
            if s.bucket == "split" and "15260158606" in (s.fact_upsert_key or "")
        ]

        if dry_run:
            out["amazon_after_estimated"] = {
                **out["amazon_before"],
                "shipped_units": out["amazon_before"]["shipped_units"]
                - sum(
                    g.legacy_qty
                    for g in plans
                    if g.purchase_order_id == out["amazon_before"].get("purchase_order_id")
                    and g.resolved_customer_id == 26
                ),
                "note": "estimate if all clean Amazon merges run; split rows remain",
            }
            return out

        totals = {"facts_deleted": 0}
        for group in plans:
            stats = execute_shipped_fact_identity_twin_merge(db, group)
            totals["facts_deleted"] += int(stats.get("facts_deleted", 0))
        db.commit()
        out["execute"] = totals
        out["after"] = shipped_fact_twin_summary_stats(db)
        out["amazon_after"] = amazon_po_shipped_stats(db, "PURMIDR26009978", 26)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--confirm", action="store_true", help="Execute clean merges (default preview only)")
    p.add_argument("--limit", type=int, default=None, help="Cap number of clean groups merged")
    p.add_argument("--sample", type=int, default=10, help="Preview sample size in output")
    args = p.parse_args()
    result = run(dry_run=not args.confirm, limit=args.limit, sample=max(0, int(args.sample)))
    mode = "CONFIRM" if args.confirm else "DRY-RUN"
    print(f"[{mode}] merge_shipped_fact_identity_twins")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
