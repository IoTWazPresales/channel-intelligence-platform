"""N-0110 repair 2, read-only: every CST load that owns fact rows, and whether its stored file can be read.

usage (via dbrun): python probe_jobs.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))

from sqlalchemy import text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402
from app.storage.local import get_storage_backend  # noqa: E402

with SessionLocal() as s:
    print("current_database()", s.execute(text("select current_database()")).scalar())
    s.execute(text("set transaction read only"))
    storage = get_storage_backend()
    jobs = s.execute(
        text(
            """
            select j.id, j.created_at, j.file_name, j.tenant_id, j.import_mode, j.status,
                   (select count(*) from fact_customer_sellthrough f where f.import_job_id = j.id) facts,
                   (select coalesce(sum(units_sold), 0) from fact_customer_sellthrough f where f.import_job_id = j.id) units,
                   (select array_agg(distinct customer_id) from fact_customer_sellthrough f where f.import_job_id = j.id) customers,
                   (select min(period_start_date) from fact_customer_sellthrough f where f.import_job_id = j.id) pmin,
                   (select max(period_start_date) from fact_customer_sellthrough f where f.import_job_id = j.id) pmax
            from import_job j
            where exists (select 1 from fact_customer_sellthrough f where f.import_job_id = j.id)
            order by j.created_at, j.id
            """
        )
    ).all()
    out = []
    for j in jobs:
        keys = s.execute(text("select storage_key from raw_file_metadata where job_id = :j"), {"j": j.id}).scalars().all()
        ok, digests = bool(keys), []
        for k in keys:
            try:
                digests.append(hashlib.sha256(storage.read(k)).hexdigest()[:12])
            except Exception:  # noqa: BLE001
                ok = False
        out.append(
            {
                "job": j.id,
                "loaded": j.created_at.isoformat(timespec="minutes"),
                "file": j.file_name,
                "customers": j.customers,
                "facts": j.facts,
                "units": float(j.units),
                "periods": [j.pmin.isoformat(), j.pmax.isoformat()],
                "files": len(keys),
                "file_ok": ok,
                "sha": digests,
            }
        )
    for o in out:
        print(json.dumps(o))
    print("jobs", len(out), "with file", sum(o["file_ok"] for o in out), "without", [o["job"] for o in out if not o["file_ok"]])
