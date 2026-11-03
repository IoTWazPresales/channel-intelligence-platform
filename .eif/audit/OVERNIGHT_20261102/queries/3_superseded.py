"""READ-ONLY (TASK 3): where did the facts of the applied store-level staging lines go? Superseded copies by customer,
job, reason; and, for the IC/Hifi-type week files, the facts held now vs staged-with-figures."""
import json
from ro import q, run_ro

OUT = ".eif/audit/OVERNIGHT_20261102/queries/3_superseded.out.json"


async def work(db):
    out = {}
    out["superseded_by_customer_job"] = await q(db, """
      select s.customer_id, c.name, s.import_job_id, s.superseded_by_import_job_id, s.reason, count(*) n,
        coalesce(sum(s.units_sold),0) units, coalesce(sum(s.reported_soh),0) soh, min(s.period_start_date) d_min, max(s.period_start_date) d_max
      from fact_customer_sellthrough_superseded s join dim_customer c on c.id=s.customer_id
      where s.customer_id in (11,12,15,57) group by 1,2,3,4,5 order by 1,3,4""")
    # How many applied lines carry a non-zero figure, vs facts. Fact rows hold a figure only when carried.
    out["applied_lines_nonzero"] = await q(db, """
      select s.import_job_id job_id, count(*) applied_lines,
        count(*) filter (where coalesce(s.units_sold,0)<>0 or coalesce(s.reported_soh,0)<>0 or coalesce(s.in_transit_units,0)<>0 or coalesce(s.on_order_units,0)<>0) nonzero_lines,
        count(distinct s.fact_sellthrough_row_id) distinct_facts
      from import_customer_sellthrough_staging_line s where s.import_job_id in (912,913) and s.apply_status='applied' group by 1""")
    # facts of those customers: what is the key shape and figure state
    out["fact_sample_ic"] = await q(db, """
      select f.id, f.source_key, f.site_label, f.units_sold, f.reported_soh, f.period_start_date, f.import_job_id, f.figure_import_jobs
      from fact_customer_sellthrough f where f.customer_id=12 order by f.id limit 8""")
    out["fact_ic_stats"] = await q(db, """
      select count(*) n, count(distinct site_label) sites, count(distinct product_id) products,
        count(*) filter (where units_sold<>0) units_nonzero, count(*) filter (where reported_soh<>0) soh_nonzero,
        count(*) filter (where units_sold=0 and coalesce(reported_soh,0)=0) all_zero
      from fact_customer_sellthrough where customer_id in (12)""")
    out["fact_hifi_stats"] = await q(db, """
      select count(*) n, count(distinct site_label) sites, count(distinct product_id) products,
        count(*) filter (where units_sold<>0) units_nonzero, count(*) filter (where reported_soh<>0) soh_nonzero,
        count(*) filter (where units_sold=0 and coalesce(reported_soh,0)=0) all_zero
      from fact_customer_sellthrough where customer_id in (11)""")
    print(json.dumps(out, indent=1, default=str))
    open(OUT, "w").write(json.dumps(out, indent=1, default=str))


run_ro(work)
