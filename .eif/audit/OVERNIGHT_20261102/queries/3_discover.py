"""READ-ONLY (TASK 3): discover customers with store/site-level sell-through staging rows, staged vs loaded.
Store-level staging row = non-blank site_label OR non-blank raw_location_token OR resolved_location_id set.
Loaded = apply_status in ('applied','duplicate')."""
import json
from ro import q, run_ro

OUT = ".eif/audit/OVERNIGHT_20261102/queries/3_discover.out.json"

STORE = "(nullif(trim(s.site_label),'') is not null or nullif(trim(s.raw_location_token),'') is not null or s.resolved_location_id is not null)"


async def work(db):
    out = {}
    out["all_customers_staging"] = await q(db, f"""
      select coalesce(s.resolved_customer_id, nullif(j.staged_metadata->>'customer_id','')::int) cid, c.name,
        count(*) staged_rows,
        count(*) filter (where {STORE}) store_level_rows,
        count(*) filter (where s.apply_status in ('applied','duplicate')) loaded_rows,
        count(*) filter (where {STORE} and s.apply_status in ('applied','duplicate')) store_loaded,
        count(*) filter (where {STORE} and s.apply_status is null) store_not_applied,
        count(distinct s.import_job_id) jobs
      from import_customer_sellthrough_staging_line s join import_job j on j.id=s.import_job_id
      left join dim_customer c on c.id=coalesce(s.resolved_customer_id, nullif(j.staged_metadata->>'customer_id','')::int)
      group by 1,2 order by store_level_rows desc, staged_rows desc""")
    out["fact_store_level_by_customer"] = await q(db, """
      select f.customer_id, c.name, count(*) fact_rows,
        count(*) filter (where nullif(trim(f.site_label),'') is not null or f.customer_location_id is not null) store_fact_rows,
        coalesce(sum(f.units_sold) filter (where nullif(trim(f.site_label),'') is not null or f.customer_location_id is not null),0) store_units
      from fact_customer_sellthrough f join dim_customer c on c.id=f.customer_id group by 1,2 order by store_fact_rows desc""")
    out["staging_status_values"] = await q(db, """select resolution_status, apply_status, count(*) n from import_customer_sellthrough_staging_line group by 1,2 order by n desc""")
    print(json.dumps(out, indent=1, default=str))
    open(OUT, "w").write(json.dumps(out, indent=1, default=str))


run_ro(work)
