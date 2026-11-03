"""READ-ONLY: reproduce '479 lines / 40,695 units no product match' for job 1697."""
import json
from ro import q, run_ro

async def work(db):
    out = {}
    J = 1697
    out["ev_status_by_linestate"] = await q(db, """select line_state, coalesce(product_resolution_status,'<null>') st, (product_id is null) pid_null, count(*) lines, sum(quantity) units
       from shipment_evidence_line where import_job_id=:j group by 1,2,3 order by 1,2,3""", j=J)
    out["ev_status_totals"] = await q(db, """select coalesce(product_resolution_status,'<null>') st, (product_id is null) pid_null, count(*) lines, sum(quantity) units
       from shipment_evidence_line where import_job_id=:j group by 1,2 order by 1,2""", j=J)
    out["fact_status_by_linestate"] = await q(db, """select line_state, coalesce(product_resolution_status,'<null>') st, (product_id is null) pid_null, count(*) lines, sum(quantity) units
       from fact_inbound_shipment where import_job_id=:j group by 1,2,3 order by 1,2,3""", j=J)
    out["fact_all_jobs_unmatched"] = await q(db, """select import_job_id, line_state, count(*) lines, sum(quantity) units from fact_inbound_shipment where product_id is null group by 1,2 order by 1,2""")
    out["ev_all_jobs_unmatched"] = await q(db, """select import_job_id, count(*) lines, sum(quantity) units from shipment_evidence_line where product_id is null group by 1 order by 1""")
    out["ev_corpus_superseded"] = await q(db, """select (corpus_superseded_at is not null) superseded, (product_id is null) pid_null, count(*) lines, sum(quantity) units from shipment_evidence_line where import_job_id=:j group by 1,2 order by 1,2""", j=J)
    # distinct-line variants: unmatched by distinct source keys
    out["ev_unmatched_distinct"] = await q(db, """select count(*) lines, count(distinct source_key) keys, sum(quantity) units, count(distinct (source_sheet, source_row_number)) rows_ from shipment_evidence_line where import_job_id=:j and product_id is null""", j=J)
    print(json.dumps(out, indent=1, default=str))
    open(".eif/audit/OVERNIGHT_20261102/queries/2b_repro.out.json","w").write(json.dumps(out, indent=1, default=str))
run_ro(work)
