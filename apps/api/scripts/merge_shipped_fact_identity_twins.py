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


def _twin_dict(t) -> dict:
    return {
        "old_fact": t.old_id, "evidence_qty": t.evidence_qty, "old_key": t.old_key, "old_job": t.old_job, "delivery_no": t.delivery_no,
        "item_code": t.item_code, "old_qty": t.old_qty, "twins": t.twins, "twin_qty": t.twin_qty,
        "keeper_fact": t.keeper_id, "keeper_key": t.keeper_key, "keeper_job": t.keeper_job,
    }


def _units(db, where: str) -> float:
    return float(db.scalar(text(f"SELECT coalesce(sum(quantity), 0) FROM fact_inbound_shipment WHERE {where}")) or 0)


def run_retire_po_less(*, apply: bool, expect_db: str | None, accept_evidence_sum: bool = False) -> dict:
    """Soft-retire shipped facts with no purchase_order_id whose delivery + item a newer job wrote under a PO key.

    Dry run (default) is a read-only transaction. ``--apply`` needs ``--expect-db`` equal to ``current_database()``,
    runs in one transaction, checks the retired count against the plan and writes one ``platform_audit_event``.
    Rows whose quantity differs from their twins' are listed and left alone.
    """
    from app.services.imports.shipment_shipped_fact_identity_twin_merge import (
        plan_po_less_shipped_twins,
        refresh_superseded_pointers,
        retire_po_less_shipped_twins,
    )

    out: dict = {}
    with SessionLocal() as db:
        dbname = str(db.scalar(text("SELECT current_database()")))
        out["database"] = dbname
        if apply and expect_db != dbname:
            raise SystemExit(f"refused: --apply needs --expect-db {dbname!r} (got {expect_db!r})")
        if not apply:
            db.execute(text("SET TRANSACTION READ ONLY"))
        plan = plan_po_less_shipped_twins(db)
        match = [t for t in plan if t.eligible(accept_evidence_sum)]
        differ = [t for t in plan if not t.eligible(accept_evidence_sum)]
        out["twins_found"] = len(plan)
        out["to_retire"] = len(match)
        out["to_retire_units"] = sum(t.old_qty for t in match)
        out["quantity_differs"] = [_twin_dict(t) for t in differ]
        out["shipped_units_before"] = _units(db, "line_state = 'shipped'")
        if not apply:
            db.rollback()
            return out
        changed = retire_po_less_shipped_twins(db, plan, accept_evidence_sum=accept_evidence_sum)
        refresh_superseded_pointers(db)
        if changed != len(match):
            db.rollback()
            raise SystemExit(f"ROLLED BACK: retired {changed}, plan said {len(match)}")
        from app.services.platform_audit import record_platform_audit_sync

        record_platform_audit_sync(
            db, None, area="admin", action="shipped_fact_po_less_retire", target_type="fact_inbound_shipment",
            target_id="20261101_0050", actor_label="scripts/merge_shipped_fact_identity_twins.py --retire-po-less",
            detail={"retired": changed, "fact_ids": [t.old_id for t in match], "quantity_differs": [t.old_id for t in differ]},
        )
        db.commit()
        out["retired"] = changed
        out["shipped_units_after"] = _units(db, "line_state = 'shipped'")
    return out


def run_retire_orphans(*, job: int, apply: bool, expect_db: str | None) -> dict:
    """Open facts of one job that lost their evidence line when the job was read again under new source keys.

    Dry run (default) is a read-only transaction and lists them. ``--apply`` needs ``--expect-db`` equal to ``current_database()``;
    each becomes ``closed_superseded`` (pointing at the fact that now carries the same order line) or ``closed_disappeared``.
    """
    from app.services.imports.shipment_shipped_fact_identity_twin_merge import plan_orphaned_open_rows, retire_orphaned_open_rows

    out: dict = {}
    with SessionLocal() as db:
        dbname = str(db.scalar(text("SELECT current_database()")))
        out["database"] = dbname
        if apply and expect_db != dbname:
            raise SystemExit(f"refused: --apply needs --expect-db {dbname!r} (got {expect_db!r})")
        if not apply:
            db.execute(text("SET TRANSACTION READ ONLY"))
        plan = plan_orphaned_open_rows(db, job)
        out["job"] = job
        out["orphaned_open_rows"] = len(plan)
        out["units"] = float(sum(float(r["quantity"] or 0) for r in plan))
        out["with_replacement"] = sum(1 for r in plan if r["replaced_by"] is not None)
        out["rows"] = [
            {"fact": r["id"], "order_no": r["order_no"], "order_line": r["order_line"], "item": r["item_code"], "quantity": float(r["quantity"] or 0),
             "replaced_by": r["replaced_by"]} for r in plan
        ]
        if not apply:
            db.rollback()
            return out
        done = retire_orphaned_open_rows(db, job, plan)
        # Rows the plan flags (quantity_differs, ambiguous) are left open on purpose; every other row must have been retired.
        actionable = sum(1 for r in plan if r.get("action") in (None, "supersede", "disappear"))
        out["flagged_left_open"] = [{"fact": r["id"], "reason": r["action"]} for r in plan if r.get("action") in ("quantity_differs", "ambiguous")]
        if done["superseded"] + done["disappeared"] != actionable:
            db.rollback()
            raise SystemExit(f"ROLLED BACK: retired {done}, the plan said {actionable}")
        from app.services.platform_audit import record_platform_audit_sync

        record_platform_audit_sync(
            db, None, area="admin", action="shipped_fact_orphan_open_retire", target_type="import_job", target_id=str(job),
            actor_label="scripts/merge_shipped_fact_identity_twins.py --retire-orphan-open-rows",
            detail={**done, "fact_ids": [r["id"] for r in plan]},
        )
        db.commit()
        out["retired"] = done
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--confirm", action="store_true", help="Execute key regen + collapses")
    p.add_argument("--limit", type=int, default=None, help="Cap collapse groups on confirm")
    p.add_argument("--sample", type=int, default=10, help="Preview sample size in output")
    p.add_argument("--retire-po-less", action="store_true", help="Retire PO-less shipped facts a PO-key fact replaced (dry run)")
    p.add_argument("--apply", action="store_true", help="with --retire-po-less: write it (needs --expect-db)")
    p.add_argument("--expect-db", default=None, help="with --apply: must equal current_database()")
    p.add_argument("--accept-evidence-sum", action="store_true",
                   help="with --retire-po-less: also retire a twin whose single PO-key fact equals the sum of its job's evidence lines")
    p.add_argument("--retire-orphan-open-rows", action="store_true", help="retire open facts of --job that lost their evidence line (dry run; --apply --expect-db)")
    p.add_argument("--job", type=int, default=None, help="with --retire-orphan-open-rows: the import job")
    args = p.parse_args()
    if args.retire_orphan_open_rows:
        if args.job is None:
            raise SystemExit("--retire-orphan-open-rows needs --job")
        print(f"[{'APPLY' if args.apply else 'DRY-RUN'}] merge_shipped_fact_identity_twins --retire-orphan-open-rows")
        print(json.dumps(run_retire_orphans(job=args.job, apply=args.apply, expect_db=args.expect_db), indent=2, default=str))
        return 0
    if args.retire_po_less:
        print(f"[{'APPLY' if args.apply else 'DRY-RUN'}] merge_shipped_fact_identity_twins --retire-po-less")
        print(json.dumps(run_retire_po_less(apply=args.apply, expect_db=args.expect_db, accept_evidence_sum=args.accept_evidence_sum), indent=2, default=str))
        return 0
    result = run(dry_run=not args.confirm, limit=args.limit, sample=max(0, int(args.sample)))
    mode = "CONFIRM" if args.confirm else "DRY-RUN"
    print(f"[{mode}] merge_shipped_fact_identity_twins")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
