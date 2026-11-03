"""READ-ONLY 2c step 1: where do the 'needs_review' items live, per table / entity_type / job status."""
import json
from ro import q, run_ro


async def work(db):
    out = {}
    out["cols_import_job"] = [r["column_name"] for r in await q(db, "select column_name from information_schema.columns where table_name='import_job' order by ordinal_position")]
    out["cand_by_entity_status"] = await q(db, "select entity_type, status, count(*) n, count(distinct import_job_id) jobs from import_entity_mapping_candidate group by 1,2 order by 1,2")
    out["cand_needs_review_by_entity_jobstatus"] = await q(db, """
        select c.entity_type, j.status as job_status, j.stage as job_stage, (j.archived_at is not null) as archived, count(*) n, count(distinct c.import_job_id) jobs
        from import_entity_mapping_candidate c join import_job j on j.id=c.import_job_id
        where c.status='needs_review' group by 1,2,3,4 order by 1,2,3,4""")
    # other tables with a status column that may hold needs_review
    out["tables_with_status_needs_review_candidates"] = await q(db, """
        select table_name, column_name from information_schema.columns
        where table_schema='public' and column_name in ('status','review_status','resolution_status','steward_status')
        order by 1""")
    print(json.dumps(out, indent=1, default=str))
    json.dump(out, open(".eif/audit/OVERNIGHT_20261102/queries/2c_count.out.json", "w"), indent=1, default=str)

run_ro(work)
