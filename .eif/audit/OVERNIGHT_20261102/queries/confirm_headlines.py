"""READ-ONLY: re-check the headline counts this continuation cites. No writes."""
import json
from ro import q, run_ro

OUT = ".eif/audit/OVERNIGHT_20261102/queries/confirm_headlines.out.json"


async def work(db):
    out = {}
    out["needs_review"] = await q(
        db,
        "select entity_type, count(*) n from import_entity_mapping_candidate where status='needs_review' group by 1 order by 1",
    )
    out["job_1697_no_match"] = await q(
        db,
        """select count(*) lines, sum(quantity) units
           from shipment_evidence_line
           where import_job_id=1697 and product_resolution_status='no_match'""",
    )
    out["store_level_customers"] = await q(
        db,
        """select count(*) filter (where store_level_rows > 0) customers_with_store_rows,
                  count(*) customers_with_staging
           from (
             select coalesce(s.resolved_customer_id, nullif(j.staged_metadata->>'customer_id','')::int) cid,
                    count(*) filter (where nullif(trim(s.site_label),'') is not null
                                       or nullif(trim(s.raw_location_token),'') is not null
                                       or s.resolved_location_id is not null) store_level_rows
             from import_customer_sellthrough_staging_line s
             join import_job j on j.id = s.import_job_id
             group by 1
           ) x""",
    )
    print(json.dumps(out, indent=1, default=str))
    open(OUT, "w").write(json.dumps(out, indent=1, default=str))


run_ro(work)
