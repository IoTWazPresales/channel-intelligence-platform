"""READ-ONLY on cip: the steward queue (import_entity_mapping_candidate) after the job 1697 re-process of 2 Nov 2026.
The pre-run copies (clones) are gone, so this reads cip alone: the queue now, what the re-process did to job 1697's rows, and the summary it logged."""
from datetime import datetime, timezone

from sqlalchemy import create_engine, text

eng = create_engine("postgresql+psycopg://cip:cip@localhost:5432/cip")
with eng.connect() as con:
    con.execute(text("SET TRANSACTION READ ONLY"))
    print(con.execute(text("select current_database(), current_setting('transaction_read_only')")).one())
    cols = [r[0] for r in con.execute(text("select column_name from information_schema.columns where table_name='import_entity_mapping_candidate' order by ordinal_position"))]
    print("columns:", cols)
    print("total rows:", con.execute(text("select count(*) from import_entity_mapping_candidate")).scalar())
    print("by (entity_type, status):")
    for r in con.execute(text("select entity_type, status, count(*) from import_entity_mapping_candidate group by 1,2 order by 1,2")):
        print("  ", tuple(r))
    print("job 1697 by (entity_type, status):")
    for r in con.execute(text("select entity_type, status, count(*) from import_entity_mapping_candidate where import_job_id=1697 group by 1,2 order by 1,2")):
        print("  ", tuple(r))
    ts = "updated_at" if "updated_at" in cols else ("created_at" if "created_at" in cols else None)
    if ts:
        print(f"job 1697 rows by {ts} day:", [tuple(r) for r in con.execute(text(f"select {ts}::date, status, count(*) from import_entity_mapping_candidate where import_job_id=1697 group by 1,2 order by 1,2"))])
    print("summary rows logged for job 1697 (latest 3):")
    for r in con.execute(text("select created_at, message from import_row_result where job_id=1697 and code='shipment_evidence_summary' order by id desc limit 3")):
        print("  ", r[0], r[1])
    nr = con.execute(text("select id, entity_type, status, raw_token, suggested_display_name, row_count, import_job_id from import_entity_mapping_candidate where import_job_id=1697 and status='needs_review' order by row_count desc nulls last limit 25" if "row_count" in cols else
                          "select id, entity_type, status, raw_token, import_job_id from import_entity_mapping_candidate where import_job_id=1697 and status='needs_review' limit 25")).all()
    print("job 1697 needs_review (top 25 by rows):")
    for r in nr:
        print("  ", tuple(r))
    con.rollback()
