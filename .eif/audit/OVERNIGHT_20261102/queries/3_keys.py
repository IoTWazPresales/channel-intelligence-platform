"""READ-ONLY (TASK 3): store-grain facts written under a chain-level key (loc part 0 although a site label exists),
per customer and writing job, against the site-aware keys the applied staging lines of that job would give now.
Also: site-like payload keys on staging rows of every customer; overlap of site labels between files of one week."""
import json
from ro import q, run_ro

OUT = ".eif/audit/OVERNIGHT_20261102/queries/3_keys.out.json"


async def work(db):
    out = {}
    out["fact_key_shape"] = await q(db, """
      select f.customer_id, c.name, f.import_job_id,
        count(*) fact_rows,
        count(*) filter (where nullif(trim(f.site_label),'') is not null and f.source_key ~ '^ct:[0-9]+:0:') store_label_but_chain_key,
        count(*) filter (where f.source_key ~ '^ct:[0-9]+:sl:') site_keyed,
        count(*) filter (where f.source_key ~ '^ct:[0-9]+:[0-9]+:' and f.source_key !~ '^ct:[0-9]+:0:') location_keyed,
        count(distinct f.site_label) sites, min(f.period_start_date) d_min, max(f.period_start_date) d_max,
        coalesce(sum(f.units_sold),0) units
      from fact_customer_sellthrough f join dim_customer c on c.id=f.customer_id
      where f.customer_id in (11,12,15,57) group by 1,2,3 order by 1,3""")
    out["applied_lines_vs_site_keys"] = await q(db, """
      select s.import_job_id job_id, count(*) applied_lines,
        count(distinct (s.resolved_product_id, upper(trim(coalesce(nullif(s.site_label,''), s.raw_location_token))), s.period_start_date)) site_aware_keys,
        count(distinct (s.resolved_product_id, s.period_start_date)) chain_level_keys
      from import_customer_sellthrough_staging_line s
      where s.apply_status='applied' and s.import_job_id in (select distinct import_job_id from import_customer_sellthrough_staging_line where coalesce(nullif(trim(site_label),''), nullif(trim(raw_location_token),'')) is not null)
      group by 1 order by 1""")
    out["site_like_payload_keys_all_customers"] = await q(db, """
      select coalesce(s.resolved_customer_id, nullif(j.staged_metadata->>'customer_id','')::int) cid, k.key, count(*) rows
      from import_customer_sellthrough_staging_line s join import_job j on j.id=s.import_job_id,
        lateral jsonb_each_text(s.raw_row_payload) k
      where k.key !~ '^_' and k.key ~* '(store|site|outlet|shop|branch|location|depot|warehouse|dc\\b)' and nullif(trim(k.value),'') is not null
      group by 1,2 order by 1,3 desc""")
    out["job900_vs_files_sites"] = await q(db, """
      with a as (select distinct coalesce(nullif(trim(site_label),''), raw_location_token) s from import_customer_sellthrough_staging_line where import_job_id=900),
           b as (select distinct coalesce(nullif(trim(site_label),''), raw_location_token) s from import_customer_sellthrough_staging_line where import_job_id=906),
           c as (select distinct coalesce(nullif(trim(site_label),''), raw_location_token) s from import_customer_sellthrough_staging_line where import_job_id=907)
      select (select count(*) from a) job900_sites, (select count(*) from b) job906_sites, (select count(*) from c) job907_sites,
        (select count(*) from a where s in (select s from b)) in_906, (select count(*) from a where s in (select s from c)) in_907,
        (select count(*) from a where s not in (select s from b) and s not in (select s from c)) in_neither""")
    out["job900_meta"] = await q(db, """select id, file_name, staged_metadata - 'cst_load_parse' meta, staged_metadata->'cst_load_parse' parse, file_headers from import_job where id in (900,906,907)""")
    print(json.dumps(out, indent=1, default=str))
    open(OUT, "w").write(json.dumps(out, indent=1, default=str))


run_ro(work)
