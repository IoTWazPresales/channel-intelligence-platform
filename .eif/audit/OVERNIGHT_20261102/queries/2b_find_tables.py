"""READ-ONLY: find import job for the 27 Oct report and alias/identifier tables."""
import json
from ro import q, run_ro

async def work(db):
    out = {}
    out["jobs"] = await q(db, """select id, template_slug, import_mode, status, stage, file_name, created_at, completed_at, archived_at,
        (select count(*) from shipment_evidence_line e where e.import_job_id=j.id) ev,
        (select count(*) from fact_inbound_shipment f where f.import_job_id=j.id) facts
        from import_job j where file_name ilike '%Shipped%Unshipped%' or template_slug ilike '%shipment%' order by id""")
    out["alias_tables"] = await q(db, """select table_name from information_schema.tables where table_schema='public' and (table_name ilike '%alias%' or table_name ilike '%product%' or table_name ilike '%identifier%') order by 1""")
    print(json.dumps(out, indent=1, default=str))
    open(".eif/audit/OVERNIGHT_20261102/queries/2b_find_tables.out.json","w").write(json.dumps(out, indent=1, default=str))
run_ro(work)
