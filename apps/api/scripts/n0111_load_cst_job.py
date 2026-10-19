"""N-0111: load a sell-through job's steward-resolved rows into the facts.

usage (API venv python, from anywhere):
  python apps/api/scripts/n0111_load_cst_job.py [job_id]           dry run: counts only, writes nothing
  python apps/api/scripts/n0111_load_cst_job.py [job_id] --apply   marks steward-mapped rows resolved and loads them

With no job id it takes the newest customer sell-through job. Prints current_database() first. Rows
already loaded are not touched again; ignored tokens stay out.
"""
from __future__ import annotations

import os
import sys

_API = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _API)
os.chdir(_API)

from sqlalchemy import text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402
from app.models.ingestion import ImportJob  # noqa: E402
from app.services.imports.cst_mapping_candidates import mark_steward_mapped_cst_lines_resolved  # noqa: E402
from app.services.imports.customer_sell_through_apply import apply_customer_sellthrough_staging  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
do_apply = "--apply" in sys.argv

COUNTS = """
select
  count(*) filter (where resolved_product_id is not null and resolution_status <> 'resolved') as mapped_not_marked,
  count(*) filter (where resolution_status = 'resolved' and apply_status is null) as resolved_not_loaded,
  count(*) filter (where apply_status is not null) as loaded_or_done,
  count(*) filter (where resolved_product_id is null) as no_product,
  count(*) as total
from import_customer_sellthrough_staging_line where import_job_id = :j
"""

with SessionLocal() as s:
    print("current_database() =", s.execute(text("select current_database()")).scalar())
    jid = int(args[0]) if args else s.execute(
        text("select max(id) from import_job where staged_metadata ? 'customer_id'")
    ).scalar()
    job = s.get(ImportJob, jid)
    print(f"job {jid}: {job.file_name!r} status={job.status} import_mode={job.import_mode}")
    before = dict(s.execute(text(COUNTS), {"j": jid}).mappings().one())
    print("before:", before)
    if not do_apply:
        print("dry run: nothing written. Add --apply to load.")
        sys.exit(0)
    marked = mark_steward_mapped_cst_lines_resolved(s, jid)
    summary = apply_customer_sellthrough_staging(s, jid)
    s.commit()
    print(f"marked resolved: {marked} | loaded: {summary.applied} | still unresolved: {summary.skipped_unresolved}")
    if summary.errors:
        print("errors:", summary.errors)
    print("after:", dict(s.execute(text(COUNTS), {"j": jid}).mappings().one()))
