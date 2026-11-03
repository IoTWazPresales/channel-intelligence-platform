"""READ-ONLY: why 12 lines of job 1697 are 'inactive_only' (not part of the 479), and their master rows."""
import json

from ro import q, run_ro


async def work(db):
    out = {}
    out["lines"] = await q(db, """select e.item_code, e.sales_model_name, e.ean_code, e.quantity, e.line_state, e.product_resolution_token tok
        from shipment_evidence_line e where e.import_job_id=1697 and e.product_resolution_status='inactive_only' order by e.quantity desc""")
    out["masters_by_sales_model"] = await q(db, """select p.id, p.sku, p.sales_model_name, p.is_active, p.lifecycle_status, p.retired_date, p.launch_date
        from dim_product p where lower(trim(p.sales_model_name)) in (select lower(trim(sales_model_name)) from shipment_evidence_line where import_job_id=1697 and product_resolution_status='inactive_only')
        or lower(trim(p.sku)) in (select lower(trim(item_code)) from shipment_evidence_line where import_job_id=1697 and product_resolution_status='inactive_only')""")
    out["lifecycle_values"] = await q(db, "select lifecycle_status, is_active, count(*) n from dim_product group by 1,2 order by 3 desc")
    # distributor row-name resolution sanity: which distributor id column is populated on the 479
    out["dist_cols"] = await q(db, """select (distributor_id is not null) has_distributor_id, (resolved_distributor_id is not null) has_resolved_distributor_id,
        (customer_id is not null) has_customer_id, (resolved_customer_id is not null) has_resolved_customer_id, count(*) lines
        from shipment_evidence_line where import_job_id=1697 and product_resolution_status='no_match' group by 1,2,3,4""")
    # dim_distributor / customer hardcode-related: distributor-owned site columns (none expected here)
    out["customer_status_of_unmatched"] = await q(db, """select c.customer_status, count(*) lines from shipment_evidence_line e left join dim_customer c on c.id=coalesce(e.resolved_customer_id,e.customer_id)
        where e.import_job_id=1697 and e.product_resolution_status='no_match' group by 1""")
    out["fact_vs_evidence_gap"] = await q(db, """select 'evidence_shipped_no_match_without_fact' what, count(*) lines, sum(e.quantity) units from shipment_evidence_line e
        where e.import_job_id=1697 and e.product_resolution_status='no_match' and e.line_state='shipped'
          and not exists (select 1 from fact_inbound_shipment f where f.shipment_evidence_line_id=e.id)
        union all select 'evidence_open_no_match_without_fact', count(*), sum(e.quantity) from shipment_evidence_line e
        where e.import_job_id=1697 and e.product_resolution_status='no_match' and e.line_state='open_order'
          and not exists (select 1 from fact_inbound_shipment f where f.shipment_evidence_line_id=e.id)
        union all select 'fact_no_match_total_job', count(*), sum(quantity) from fact_inbound_shipment where import_job_id=1697 and product_resolution_status='no_match'
        union all select 'fact_no_match_open_or_shipped_job', count(*), sum(quantity) from fact_inbound_shipment where import_job_id=1697 and product_resolution_status='no_match' and line_state in ('open_order','shipped')""")
    print(json.dumps(out, indent=1, default=str))
    open(".eif/audit/OVERNIGHT_20261102/queries/2b_inactive.out.json", "w").write(json.dumps(out, indent=1, default=str))


run_ro(work)
