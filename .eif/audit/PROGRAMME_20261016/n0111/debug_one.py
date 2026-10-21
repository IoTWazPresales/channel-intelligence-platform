"""N-0111 debug on the kept clone cip_n0111: load one day-dated file, print what the job recorded."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import func, select, text  # noqa: E402

import n0111_load as L  # noqa: E402
from app.db.session_sync import SessionLocal  # noqa: E402
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine as S  # noqa: E402
from app.models.ingestion import ImportJob  # noqa: E402

with SessionLocal() as db:
    cdb = db.execute(text("select current_database()")).scalar()
    print("current_database()", cdb)
    assert str(cdb).startswith("cip_n0111")
    skus = ["90NR0381-M08090", "90XB06MN-MPW000", "90NX0AD1-M00260"]
    files = L.customer_files(skus)
    which = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    name, data, flags = files[which]
    jid = L.new_cst_job(db, 299, 21, name, data, flags)
    job = db.get(ImportJob, jid)
    print("job", jid, job.status, job.stage, job.error_summary)
    meta = job.staged_metadata or {}
    print(json.dumps({k: meta[k] for k in meta if k.startswith(("customer_sellthrough", "cst_"))}, default=str)[:3000])
    print("staging", db.execute(select(S.resolution_status, S.apply_status, S.period_grain, func.count()).where(S.import_job_id == jid).group_by(S.resolution_status, S.apply_status, S.period_grain)).all())
