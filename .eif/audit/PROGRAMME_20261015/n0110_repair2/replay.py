"""N-0110 repair 2: re-apply every CST load that owns fact rows and still has its stored file.

Runs inside dbrun.py (DATABASE_URL* point at one database).

usage (via dbrun):  python replay.py totals            per-customer rows, units, on-hand (JSON)
                    python replay.py run [--cip]        replay all loads with a stored file, oldest first
                    python replay.py recompute [--cip]  recompute every stock position

A replay is a new job over the same stored file, with staged_metadata.received_on set to the
day the original load was received, so a week without a year resolves as it would have then.
It applies under the fixed loader: per-site and per-day keys, differing repeats summed (D-0091),
older rows for the same customer, product and period superseded (D-0090). After a replay, any
row the original load still owns whose period starts after its receive day (a week stored under
a year that had not happened) moves to the superseded table as ``week_not_yet_happened``.
Writes to cip only with --cip. Never on cip_test.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))

from sqlalchemy import func, select, text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402
from app.ingestion.pipeline import process_import_job_sync  # noqa: E402
from app.models.fact_customer_sellthrough import FactCustomerSellthrough  # noqa: E402
from app.models.ingestion import ImportJob, RawFileMetadata  # noqa: E402
from app.services.imports.customer_sell_through import job_received_on  # noqa: E402
from app.services.imports.customer_sell_through_supersede import REASON_FUTURE_WEEK, move_to_superseded  # noqa: E402
from app.storage.local import get_storage_backend  # noqa: E402


def guard(s, allow_cip: bool) -> str:
    db = s.execute(text("select current_database()")).scalar()
    print(f"current_database()={db}", flush=True)
    if db == "cip_test" or (db == "cip" and not allow_cip):
        raise SystemExit(f"refusing to write on {db}")
    return db


def file_ok(s, job_id: int) -> bool:
    storage = get_storage_backend()
    keys = s.scalars(select(RawFileMetadata.storage_key).where(RawFileMetadata.job_id == job_id)).all()
    if not keys:
        return False
    try:
        for k in keys:
            storage.read(k)
    except Exception:  # noqa: BLE001
        return False
    return True


def owning_jobs(s) -> list[ImportJob]:
    ids = s.scalars(select(FactCustomerSellthrough.import_job_id).where(FactCustomerSellthrough.import_job_id.isnot(None)).distinct()).all()
    jobs = [s.get(ImportJob, int(i)) for i in ids]
    return sorted(jobs, key=lambda j: (job_received_on(j), j.created_at, j.id))


def replay(s, old: ImportJob) -> dict:
    meta = copy.deepcopy(old.staged_metadata) if isinstance(old.staged_metadata, dict) else {}
    received = job_received_on(old)
    meta["received_on"] = received.isoformat()
    meta["replay_of_job_id"] = meta.get("replay_of_job_id") or int(old.id)
    # A load from before the on-hand rule that stored no on-hand at all was sales-only in effect.
    with_soh = s.scalar(
        select(func.count(FactCustomerSellthrough.reported_soh)).where(FactCustomerSellthrough.import_job_id == old.id)
    )
    if not with_soh:
        meta["cst_sales_only"] = True
    job = ImportJob(
        tenant_id=old.tenant_id,
        source_id=old.source_id,
        template_slug=old.template_slug,
        import_mode="apply",
        status="pending",
        stage="uploaded",
        file_name=old.file_name,
        content_type=old.content_type,
        inferred_schema=copy.deepcopy(old.inferred_schema),
        field_mapping=copy.deepcopy(old.field_mapping),
        file_headers=copy.deepcopy(old.file_headers),
        mapping_decisions=copy.deepcopy(old.mapping_decisions),
        staged_metadata=meta,
    )
    s.add(job)
    s.flush()
    for r in s.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id == old.id).order_by(RawFileMetadata.id)):
        s.add(RawFileMetadata(job_id=job.id, storage_key=r.storage_key, byte_size=r.byte_size, checksum=r.checksum))
    s.commit()
    superseded_before = s.scalar(text("select count(*) from fact_customer_sellthrough_superseded"))
    process_import_job_sync(s, job.id)
    s.commit()
    s.refresh(job)
    superseded = s.scalar(text("select count(*) from fact_customer_sellthrough_superseded")) - superseded_before

    left = s.execute(
        select(FactCustomerSellthrough.id, FactCustomerSellthrough.period_start_date, FactCustomerSellthrough.units_sold).where(
            FactCustomerSellthrough.import_job_id == old.id
        )
    ).all()
    future = [int(r[0]) for r in left if r[1] > received]
    moved = move_to_superseded(s, future, by_job_id=int(job.id), reason=REASON_FUTURE_WEEK) if future else None
    s.commit()
    return {
        "old_job": int(old.id),
        "new_job": int(job.id),
        "file": old.file_name,
        "received_on": received.isoformat(),
        "status": job.status,
        "error": (job.error_summary or "")[:200] or None,
        "superseded_by_rule": int(superseded),
        "future_week_rows_moved": moved.rows if moved else 0,
        "future_week_units_moved": moved.units if moved else 0.0,
        "old_rows_left": len(left) - len(future),
        "old_units_left": float(sum(float(r[2] or 0) for r in left if r[1] <= received)),
    }


def cmd_totals() -> None:
    with SessionLocal() as s:
        print(f"current_database()={s.execute(text('select current_database()')).scalar()}", file=sys.stderr)
        rows = s.execute(
            select(
                FactCustomerSellthrough.customer_id,
                func.count(),
                func.sum(FactCustomerSellthrough.units_sold),
                func.sum(FactCustomerSellthrough.reported_soh),
            )
            .group_by(FactCustomerSellthrough.customer_id)
            .order_by(FactCustomerSellthrough.customer_id)
        ).all()
        print(json.dumps({str(c): [int(n), float(u or 0), float(h or 0)] for c, n, u, h in rows}))


def cmd_run(allow_cip: bool) -> None:
    with SessionLocal() as s:
        guard(s, allow_cip)
        jobs = owning_jobs(s)
        skipped = [int(j.id) for j in jobs if not file_ok(s, int(j.id))]
        print(json.dumps({"loads": len(jobs), "no_stored_file": skipped}), flush=True)
        for old in jobs:
            if int(old.id) in skipped:
                continue
            print(json.dumps(replay(s, old)), flush=True)


def cmd_recompute(allow_cip: bool) -> None:
    from app.services.channel_intelligence.customer_stock_gap import recompute_all_customer_stock_positions

    with SessionLocal() as s:
        guard(s, allow_cip)
        tenants = s.scalars(select(FactCustomerSellthrough.tenant_id).distinct()).all()
        for tid in tenants:
            print(json.dumps({"tenant": tid, **recompute_all_customer_stock_positions(s, tenant_id=tid)}), flush=True)
        s.commit()


if __name__ == "__main__":
    action, allow = sys.argv[1], "--cip" in sys.argv
    {"totals": cmd_totals, "run": lambda: cmd_run(allow), "recompute": lambda: cmd_recompute(allow)}[action]()
