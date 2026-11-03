"""READ-ONLY (TASK 3): per job, for each customer with store-level staging rows: status, stage, staged rows by
load-report reason (the exact SQL the Import Center uses), units, date range, loaded fact rows of the job."""
import json
from ro import q, run_ro
from app.services.imports.import_load_report import _CST_SQL

OUT = ".eif/audit/OVERNIGHT_20261102/queries/3_jobs.out.json"
STORE = "(nullif(trim(s.site_label),'') is not null or nullif(trim(s.raw_location_token),'') is not null or s.resolved_location_id is not null)"


async def work(db):
    out = {}
    jobs = await q(db, f"""
      select j.id job_id, j.file_name, j.template_slug, j.import_mode, j.status, j.stage, j.validation_passed, j.archived_at is not null archived,
        j.created_at, j.completed_at, j.error_summary,
        j.staged_metadata->>'customer_id' meta_customer,
        j.staged_metadata->>'year_confirmed' year_confirmed, j.staged_metadata->>'week_year' week_year,
        (select string_agg(distinct coalesce(s.resolved_customer_id::text,'null'),',') from import_customer_sellthrough_staging_line s where s.import_job_id=j.id) staged_cust_ids,
        (select count(*) from import_customer_sellthrough_staging_line s where s.import_job_id=j.id) staged_rows,
        (select count(*) from import_customer_sellthrough_staging_line s where s.import_job_id=j.id and {STORE}) store_rows,
        (select count(*) from import_customer_sellthrough_staging_line s where s.import_job_id=j.id and s.apply_status in ('applied','duplicate')) applied_rows,
        (select count(*) from fact_customer_sellthrough f where f.import_job_id=j.id) fact_rows_owned,
        (select count(*) from import_customer_sellthrough_staging_line s where s.import_job_id=j.id and s.fact_sellthrough_row_id is not null) lines_with_fact_id,
        (select coalesce(sum(s.units_sold),0) from import_customer_sellthrough_staging_line s where s.import_job_id=j.id) staged_units,
        (select coalesce(sum(s.units_sold),0) from import_customer_sellthrough_staging_line s where s.import_job_id=j.id and s.apply_status is null) unapplied_units,
        (select min(s.period_start_date) from import_customer_sellthrough_staging_line s where s.import_job_id=j.id) d_min,
        (select max(s.period_start_date) from import_customer_sellthrough_staging_line s where s.import_job_id=j.id) d_max,
        (select count(distinct s.period_start_date) from import_customer_sellthrough_staging_line s where s.import_job_id=j.id) n_dates,
        (select count(distinct coalesce(nullif(trim(s.site_label),''), nullif(trim(s.raw_location_token),''))) from import_customer_sellthrough_staging_line s where s.import_job_id=j.id) n_sites
      from import_job j
      where j.template_slug='customer_sell_through'
        and exists (select 1 from import_customer_sellthrough_staging_line s where s.import_job_id=j.id and {STORE})
      order by j.id""")
    out["jobs"] = jobs
    ids = [j["job_id"] for j in jobs]
    from sqlalchemy import text
    res = await db.execute(text(_CST_SQL), {"ids": ids})
    reasons = {}
    for jid, reason, n in res.all():
        reasons.setdefault(int(jid), {})[reason] = int(n)
    out["reasons_by_job"] = reasons
    print(json.dumps(out, indent=1, default=str))
    open(OUT, "w").write(json.dumps(out, indent=1, default=str))


run_ro(work)
