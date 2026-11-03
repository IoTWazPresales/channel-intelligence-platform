"""READ-ONLY (TASK 3): why do applied staging lines (e.g. 4320) map to few fact rows? Per job: lines, distinct
(product, site, period) keys, lines with units, lines with SOH, distinct fact ids, whether those facts exist."""
import json
from ro import q, run_ro

OUT = ".eif/audit/OVERNIGHT_20261102/queries/3_collapse.out.json"
JOBS = [900, 906, 907, 912, 913, 903, 911, 1659, 1665]


async def work(db):
    out = {}
    out["per_job"] = await q(db, """
      select s.import_job_id job_id, s.apply_status, s.resolution_status, count(*) lines,
        count(distinct (s.resolved_product_id, coalesce(nullif(trim(s.site_label),''), s.raw_location_token), s.period_start_date)) distinct_keys,
        count(*) filter (where s.units_sold is not null) with_units,
        count(*) filter (where s.units_sold > 0) with_units_gt0,
        count(*) filter (where s.reported_soh is not null) with_soh,
        count(*) filter (where s.reported_soh > 0) with_soh_gt0,
        count(*) filter (where s.units_sold is null and s.reported_soh is null and s.in_transit_units is null and s.on_order_units is null) no_figures,
        count(distinct s.fact_sellthrough_row_id) distinct_fact_ids,
        count(*) filter (where s.fact_sellthrough_row_id is not null and not exists (select 1 from fact_customer_sellthrough f where f.id=s.fact_sellthrough_row_id)) fact_id_dangling,
        coalesce(sum(s.units_sold),0) units, coalesce(sum(s.reported_soh),0) soh
      from import_customer_sellthrough_staging_line s where s.import_job_id = any(:ids) group by 1,2,3 order by 1,2,3""", ids=JOBS)
    out["fact_by_job"] = await q(db, """
      select f.import_job_id, f.customer_id, count(*) fact_rows, coalesce(sum(units_sold),0) units, coalesce(sum(reported_soh),0) soh,
        count(*) filter (where reported_soh is not null) with_soh, min(period_start_date) d_min, max(period_start_date) d_max
      from fact_customer_sellthrough f where f.customer_id in (11,12) group by 1,2 order by 1""")
    out["fact_columns_extra_tables"] = await q(db, """select table_name from information_schema.tables where table_schema='public' and (table_name ilike '%sellthrough%' or table_name ilike '%supersed%') order by 1""")
    print(json.dumps(out, indent=1, default=str))
    open(OUT, "w").write(json.dumps(out, indent=1, default=str))


run_ro(work)
