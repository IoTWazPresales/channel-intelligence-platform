"""READ-ONLY 2c step 2: profile the shipment_* needs_review candidates as stored (match_reason, suggested_action, jobs)."""
import json
from ro import q, run_ro


async def work(db):
    out = {}
    out["by_entity_matchreason_action"] = await q(db, """
        select entity_type, coalesce(match_reason,'(null)') match_reason, coalesce(context->>'suggested_action','(null)') suggested_action,
               (suggested_entity_id is not null) has_suggested, count(*) n
        from import_entity_mapping_candidate where status='needs_review' and entity_type like 'shipment_%'
        group by 1,2,3,4 order by 1,5 desc""")
    out["by_job"] = await q(db, """
        select c.entity_type, c.import_job_id, j.source_id, j.file_name, j.status, j.stage, j.import_mode,
               to_char(j.created_at,'YYYY-MM') created_month, count(*) n,
               sum(row_count) rows_sum
        from import_entity_mapping_candidate c join import_job j on j.id=c.import_job_id
        where c.status='needs_review' and c.entity_type like 'shipment_%' group by 1,2,3,4,5,6,7,8 order by 1,2""")
    out["job_candidate_status_all"] = await q(db, """
        select c.import_job_id, c.entity_type, c.status, count(*) n from import_entity_mapping_candidate c
        where c.entity_type like 'shipment_%' and c.import_job_id in (select import_job_id from import_entity_mapping_candidate where status='needs_review' and entity_type like 'shipment_%')
        group by 1,2,3 order by 1,2,3""")
    print(json.dumps(out, indent=1, default=str))
    json.dump(out, open(".eif/audit/OVERNIGHT_20261102/queries/2c_ship_explore.out.json", "w"), indent=1, default=str)

run_ro(work)
