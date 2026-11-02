#!/usr/bin/env python3
"""Re-read one applied inbound shipment job from its stored workbook with the current loader, then rewrite its facts.

Used after the source-key change (a line not invoiced yet keeps its order in the key) so a job that lost rows to the old
key gets them back. It runs the two data steps the worker runs, without the notification side of an import:

1. ``process_shipment_evidence_import``: evidence lines (one per source key), observations, the invoice graduation;
   lines of this job the file no longer produces under any key are purged (the old collapsed key goes).
2. ``write_shipment_facts_and_close_book``: this job's facts (a PO-less twin is retired at load) and the open-book close.

Dry run (default) only reads the stored workbook and reports what it would produce. ``--apply`` needs ``--expect-db`` equal
to ``current_database()``, runs both steps in one transaction and writes one ``platform_audit_event``.

  python scripts/ops/reprocess_shipment_job.py --job 1697 --apply --expect-db cip_retire
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--job", type=int, required=True)
    p.add_argument("--apply", action="store_true", help="write (needs --expect-db)")
    p.add_argument("--expect-db", default=None)
    p.add_argument("--fail-before-commit", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args(argv)

    import pandas as pd
    from sqlalchemy import func, select, text

    from app.db.session_sync import SessionLocal
    from app.models.ingestion import ImportJob
    from app.models.shipment_evidence import ShipmentEvidenceLine
    from app.services.imports.shipment_evidence_import import process_shipment_evidence_import
    from app.services.imports.shipment_open_book import write_shipment_facts_and_close_book

    with SessionLocal() as db:
        dbname = str(db.scalar(text("SELECT current_database()")))
        print(f"current_database() = {dbname}; job {args.job}; {'APPLY' if args.apply else 'DRY RUN (nothing is written)'}")
        if args.apply and args.expect_db != dbname:
            print(f"refused: --apply needs --expect-db {dbname!r} (got {args.expect_db!r})")
            return 2
        job = db.get(ImportJob, args.job)
        if job is None or job.template_slug != "inbound_shipments" or job.status != "completed" or job.stage != "loaded":
            print("refused: the job is not an applied inbound_shipments job")
            return 2
        before = db.scalar(select(func.count()).select_from(ShipmentEvidenceLine).where(ShipmentEvidenceLine.import_job_id == args.job))
        if not args.apply:
            db.execute(text("SET TRANSACTION READ ONLY"))
            from app.services.imports.shipment_evidence_import import _load_frames_for_job
            from app.services.imports.shipment_evidence_source_keys import stable_source_key_for_row  # noqa: F401
            from app.models.ingestion import RawFileMetadata
            from app.storage.local import get_storage_backend

            raw = db.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id == args.job)).first()
            frames = _load_frames_for_job(job, pd.DataFrame(), get_storage_backend().read(raw.storage_key))
            rows = sum(len(f) for _sn, f, rt, _ls in frames if f is not None)
            print(f"evidence lines now: {before:,}; the stored workbook has {rows:,} data rows on {len(frames)} sheets (the real run reports the lines it writes)")
            db.rollback()
            return 0
        # A job applied before the voyage fields existed has a saved mapping without them, so a plain re-read would leave
        # on-board, ETA, ATA and the voyage text empty. Add the fields the file's own headers match (the one-time confirm).
        from app.models.shipment_water import WATER_FIELDS
        from app.services.imports.shipment_field_mapping import build_initial_shipment_field_mapping

        mapping = dict(job.field_mapping or {})
        have = set(mapping.values())
        added = {h: t for h, t in build_initial_shipment_field_mapping([str(h) for h in (job.file_headers or [])], None).items() if t in WATER_FIELDS and t not in have}
        if added:
            mapping.update(added)
            job.field_mapping = mapping
            print(f"saved mapping gains {len(added)} voyage field(s): {sorted(added.values())}")
        blocking = process_shipment_evidence_import(db, job, pd.DataFrame(), mapping)
        if blocking:
            db.rollback()
            print(f"ROLLED BACK: the evidence import reported {blocking} blocking problem(s)")
            return 3
        db.flush()
        written = write_shipment_facts_and_close_book(db, job)
        after = db.scalar(select(func.count()).select_from(ShipmentEvidenceLine).where(ShipmentEvidenceLine.import_job_id == args.job))
        from app.services.platform_audit import record_platform_audit_sync

        record_platform_audit_sync(
            db, None, area="admin", action="shipment_job_reprocess", target_type="import_job", target_id=str(args.job),
            actor_label="scripts/ops/reprocess_shipment_job.py",
            detail={"evidence_lines_before": before, "evidence_lines_after": after, **{k: v for k, v in written.items() if k != "skipped_reason"}},
        )
        if args.fail_before_commit:
            db.rollback()
            print("ROLLED BACK (forced failure before commit)")
            return 3
        db.commit()
        print(f"committed: evidence lines {before:,} -> {after:,}; facts written {written['fact_rows']:,}; open-book closed {written['closed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
