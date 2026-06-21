"""Profile DSI validate on a remote Supabase job (169k soak).

Usage (from apps/api with venv active):
  set CIP_DSI_VALIDATE_PROFILE=1
  python scripts/_dsi_validate_profile.py --job-id 43

Prints wall time and relies on processor log lines for chunk breakdown.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from sqlalchemy import func, select, text

# Ensure app package on path when run as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session_sync import SessionLocal
from app.ingestion.pipeline import process_import_job_sync
from app.models.import_distributor_si import ImportDistributorSiStagingLine
from app.models.ingestion import ImportJob


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile DSI validate for an import job")
    parser.add_argument("--job-id", type=int, required=True, help="ImportJob.id to re-validate")
    args = parser.parse_args()

    os.environ["CIP_DSI_VALIDATE_PROFILE"] = "1"

    with SessionLocal() as db:
        db_name = db.scalar(text("SELECT current_database()"))
        job = db.get(ImportJob, args.job_id)
        if not job:
            raise SystemExit(f"Job {args.job_id} not found")
        total = int((job.staged_metadata or {}).get("dsi_validate_total_rows") or 0)
        print(f"Database: {db_name}")
        print(f"Job #{job.id} file={job.file_name!r} stage={job.stage} rows~{total or 'unknown'}")

    t0 = time.monotonic()
    with SessionLocal() as db:
        result = process_import_job_sync(db, args.job_id)
    elapsed = time.monotonic() - t0

    with SessionLocal() as db:
        staging = db.scalar(
            select(func.count())
            .select_from(ImportDistributorSiStagingLine)
            .where(ImportDistributorSiStagingLine.import_job_id == args.job_id)
        )
        j = db.get(ImportJob, args.job_id)
        meta = j.staged_metadata or {}
        candidates = db.scalar(
            text(
                "SELECT COUNT(*) FROM import_entity_mapping_candidate WHERE import_job_id = :jid"
            ),
            {"jid": args.job_id},
        )

    rows = int(staging or 0)
    rps = rows / elapsed if elapsed > 0 else 0.0
    print(f"Result: stage={result.stage} status={result.status}")
    print(f"Staging lines: {rows}  candidates: {candidates}")
    print(f"Wall time: {elapsed:.1f}s  throughput: {rps:.1f} rows/s")
    print(f"Checkpoint rows_committed: {meta.get('dsi_validate_rows_committed')}")
    if rows and rps < 62:
        print("FAIL: throughput below 62 rows/s pre-Phase-1 baseline")
        raise SystemExit(1)
    if rows and elapsed > 3600:
        print("FAIL: validate exceeded 1 hour")
        raise SystemExit(1)
    print("PASS: throughput and duration within acceptance targets")


if __name__ == "__main__":
    main()
