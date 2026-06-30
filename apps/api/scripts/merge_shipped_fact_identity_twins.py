"""Preview-first collapse of shipped fact rows sharing ``fact_upsert_key``.

Dry-run by default; ``--confirm`` regenerates PO-inclusive keys, collapses duplicates,
then commits. Run after ``20260630_0062`` and before ``0061`` (unique on ``fact_upsert_key``).
"""
from __future__ import annotations

import argparse
import json

from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.services.imports.cip_db_identity import is_cip_application_database
from app.services.imports.shipment_shipped_fact_identity_twin_merge import (
    amazon_po_shipped_stats,
    execute_all_shipped_fact_collapses,
    plan_shipped_fact_identity_twin_merges,
    regenerate_shipped_fact_upsert_keys,
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

        keys_regenerated = regenerate_shipped_fact_upsert_keys(db)
        out["keys_regenerated"] = int(keys_regenerated)
        if not dry_run:
            db.flush()

        plans, skipped = plan_shipped_fact_identity_twin_merges(db)
        if limit is not None:
            plans = plans[: int(limit)]

        out["blast_radius"] = twin_blast_radius(db, plans, skipped)
        out["bucket_counts"] = {
            "clean": sum(1 for g in plans if g.bucket == "clean"),
            "multi_invoice": sum(1 for g in plans if g.bucket == "multi_invoice"),
            "multi_import": sum(1 for g in plans if g.bucket == "multi_import"),
            "skipped": len(skipped),
        }
        out["losers_to_delete"] = sum(len(g.loser_ids) for g in plans)
        out["sample_clean"] = [
            shipped_fact_twin_plan_to_dict(g) for g in plans if g.bucket == "clean"
        ][:sample]
        out["sample_multi_invoice"] = [
            shipped_fact_twin_plan_to_dict(g) for g in plans if g.bucket == "multi_invoice"
        ][:sample]
        out["sample_multi_import"] = [
            shipped_fact_twin_plan_to_dict(g) for g in plans if g.bucket == "multi_import"
        ][:sample]
        out["sample_skipped"] = [shipped_fact_twin_skip_to_dict(s) for s in skipped][:sample]

        if dry_run:
            db.rollback()
            amazon_po_id = out["amazon_before"].get("purchase_order_id")
            stale = sum(
                g.units_before - g.survivor_qty
                for g in plans
                if g.purchase_order_id == amazon_po_id
            )
            out["amazon_after_estimated"] = {
                **out["amazon_before"],
                "shipped_units": out["amazon_before"]["shipped_units"] - stale,
                "note": "estimate after key regen + collapse (transaction rolled back)",
            }
            return out

        totals = execute_all_shipped_fact_collapses(db, plans)
        db.commit()
        out["execute"] = totals
        out["after"] = shipped_fact_twin_summary_stats(db)
        out["amazon_after"] = amazon_po_shipped_stats(db, "PURMIDR26009978", 26)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--confirm", action="store_true", help="Execute key regen + collapses")
    p.add_argument("--limit", type=int, default=None, help="Cap collapse groups on confirm")
    p.add_argument("--sample", type=int, default=10, help="Preview sample size in output")
    args = p.parse_args()
    result = run(dry_run=not args.confirm, limit=args.limit, sample=max(0, int(args.sample)))
    mode = "CONFIRM" if args.confirm else "DRY-RUN"
    print(f"[{mode}] merge_shipped_fact_identity_twins")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
