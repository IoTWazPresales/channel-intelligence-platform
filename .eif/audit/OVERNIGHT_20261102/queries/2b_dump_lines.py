"""READ-ONLY: dump the 479 no_match lines (identifiers only) + sample of master formats, for offline analysis."""
import json
from ro import q, run_ro
J = 1697
async def work(db):
    out = {}
    out["lines"] = await q(db, """select e.id, e.line_state, e.source_sheet, e.item_code, e.sales_model_name, e.customer_item, e.ean_code, e.upc_code, e.mpor_item_no, e.quantity,
        e.product_resolution_token tok, coalesce(e.resolved_distributor_id,e.distributor_id) did, d.name distributor, coalesce(e.resolved_customer_id,e.customer_id) cid, c.name customer,
        e.customer_dealer_token, e.bill_to_raw, e.ship_to_raw
        from shipment_evidence_line e left join dim_distributor d on d.id=coalesce(e.resolved_distributor_id,e.distributor_id)
        left join dim_customer c on c.id=coalesce(e.resolved_customer_id,e.customer_id)
        where e.import_job_id=:j and e.product_resolution_status='no_match' order by e.id""", j=J)
    out["master"] = await q(db, "select id, sku, part_number, sales_model_name, model_name, marketing_name, series_name, product_line, category, business_unit, ean, upc, is_active, lifecycle_status from dim_product")
    out["alias"] = await q(db, "select product_id, alias_value, alias_kind, confidence from product_alias")
    json.dump(out, open(".eif/audit/OVERNIGHT_20261102/queries/2b_dump_lines.out.json","w"), default=str)
    print({k: len(v) for k, v in out.items()})
run_ro(work)
