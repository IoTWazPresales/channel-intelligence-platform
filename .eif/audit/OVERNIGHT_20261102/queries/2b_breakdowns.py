"""READ-ONLY: breakdowns of the 479 no_match evidence lines of job 1697."""
import json
from ro import q, run_ro

J = 1697
BASE = "from shipment_evidence_line e where e.import_job_id=:j and e.product_resolution_status='no_match'"

async def work(db):
    out = {}
    out["total"] = await q(db, f"select count(*) lines, sum(quantity) units, count(*) filter (where quantity is null) null_qty {BASE}", j=J)
    out["by_line_state"] = await q(db, f"select line_state, count(*) lines, sum(quantity) units {BASE} group by 1", j=J)
    out["by_sheet"] = await q(db, f"select source_sheet, report_type, count(*) lines, sum(quantity) units {BASE} group by 1,2", j=J)
    out["by_distributor"] = await q(db, f"""select coalesce(d.name,'<unresolved>') distributor, e.distributor_resolution_status dstat, count(*) lines, sum(e.quantity) units
        from shipment_evidence_line e left join dim_distributor d on d.id=coalesce(e.resolved_distributor_id,e.distributor_id)
        where e.import_job_id=:j and e.product_resolution_status='no_match' group by 1,2 order by 4 desc""", j=J)
    out["by_customer"] = await q(db, f"""select coalesce(c.name,'<unresolved>') customer, count(*) lines, sum(e.quantity) units
        from shipment_evidence_line e left join dim_customer c on c.id=coalesce(e.resolved_customer_id,e.customer_id)
        where e.import_job_id=:j and e.product_resolution_status='no_match' group by 1 order by 3 desc""", j=J)
    out["identifier_presence"] = await q(db, f"""select (nullif(trim(item_code),'') is not null) has_item_code, (nullif(trim(sales_model_name),'') is not null) has_sales_model,
        (nullif(trim(customer_item),'') is not null) has_customer_item, (nullif(trim(ean_code),'') is not null) has_ean, (nullif(trim(upc_code),'') is not null) has_upc,
        (nullif(trim(mpor_item_no),'') is not null) has_mpor, count(*) lines, sum(quantity) units {BASE} group by 1,2,3,4,5,6 order by 8 desc""", j=J)
    out["identifier_presence_resolved_baseline"] = await q(db, """select (nullif(trim(item_code),'') is not null) has_item_code, (nullif(trim(sales_model_name),'') is not null) has_sales_model,
        (nullif(trim(customer_item),'') is not null) has_customer_item, (nullif(trim(ean_code),'') is not null) has_ean, (nullif(trim(upc_code),'') is not null) has_upc,
        count(*) lines from shipment_evidence_line where import_job_id=:j and product_resolution_status='resolved_unique' group by 1,2,3,4,5 order by 6 desc""", j=J)
    out["token_used_vs_detail"] = await q(db, f"select product_resolution_detail, count(*) lines, sum(quantity) units {BASE} group by 1 order by 2 desc", j=J)
    out["resolved_tier_baseline"] = await q(db, "select product_resolution_detail, count(*) lines from shipment_evidence_line where import_job_id=:j and product_resolution_status='resolved_unique' group by 1 order by 2 desc", j=J)
    out["distinct_values"] = await q(db, f"select count(distinct item_code) item_codes, count(distinct sales_model_name) sales_models, count(distinct customer_item) customer_items, count(distinct ean_code) eans, count(distinct upc_code) upcs, count(distinct mpor_item_no) mpors {BASE}", j=J)
    out["dim_product"] = await q(db, "select count(*) n, count(*) filter (where is_active) active, count(sku) sku, count(part_number) pn, count(sales_model_name) sm, count(ean) ean, count(upc) upc, count(model_name) mn, count(marketing_name) mk from dim_product")
    out["product_alias"] = await q(db, "select alias_kind, confidence, count(*) n from product_alias group by 1,2 order by 3 desc")
    print(json.dumps(out, indent=1, default=str))
    open(".eif/audit/OVERNIGHT_20261102/queries/2b_breakdowns.out.json","w").write(json.dumps(out, indent=1, default=str))
run_ro(work)
