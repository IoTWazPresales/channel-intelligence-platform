"""READ-ONLY: (a) which source columns exist in raw_source_row for the 479 lines and how often they hold a value;
(b) whether the unmatched identifiers appear anywhere else in the catalogue tables (name/specs/catalog_product text)."""
import json
import re

from ro import q, run_ro

BASE = ".eif/audit/OVERNIGHT_20261102/queries/"
rows = json.load(open(BASE + "2b_analyse_rows.out.json"))
ITEMS = sorted({r["item_code"].strip() for r in rows})
MODELS = sorted({r["sales_model_name"].strip() for r in rows if r["sales_model_name"]})
EANS = sorted({r["ean_code"].strip() for r in rows if r["ean_code"]})


async def work(db):
    out = {}
    out["raw_keys_unmatched"] = await q(db, """
        select k, count(*) filter (where nullif(trim(v),'') is not null) with_value, count(*) total
        from shipment_evidence_line e, jsonb_each_text(e.raw_source_row) as t(k, v)
        where e.import_job_id=1697 and e.product_resolution_status='no_match' group by k order by with_value desc, k""")
    out["raw_keys_resolved_sample_counts"] = await q(db, """
        select k, count(*) filter (where nullif(trim(v),'') is not null) with_value
        from (select raw_source_row from shipment_evidence_line where import_job_id=1697 and product_resolution_status='resolved_unique' limit 1500) e, jsonb_each_text(e.raw_source_row) as t(k, v)
        group by k order by with_value desc, k""")
    pats = ["%" + i + "%" for i in ITEMS + MODELS]
    out["master_name_or_specs_contains_token"] = await q(db, """select count(*) n from dim_product p where p.name ilike any(:pats) or p.specs_json::text ilike any(:pats)""", pats=pats)
    out["master_specs_contains_ean"] = await q(db, """select count(*) n from dim_product p where p.specs_json::text ilike any(:pats)""", pats=["%" + e + "%" for e in EANS])
    out["catalog_product_text_contains_token"] = await q(db, """select count(*) n from catalog_product c where c.display_name ilike any(:pats) or c.source_metadata_json::text ilike any(:pats)""", pats=pats)
    # identifier value forms on the unmatched lines (shape only)
    out["shape"] = await q(db, """select length(item_code) len_item, (item_code ~ '^90[A-Z0-9]{6}-[A-Z0-9]{6}$') asus_like_item_shape, (ean_code ~ '^[0-9]{13}$') ean13, (upc_code ~ '^[0-9]{12}$') upc12, count(*) lines
        from shipment_evidence_line where import_job_id=1697 and product_resolution_status='no_match' group by 1,2,3,4 order by 5 desc""")
    out["master_shape"] = await q(db, """select (sku ~ '^90[A-Z0-9]{6}-[A-Z0-9]{6}$') same_shape, count(*) n from dim_product group by 1""")
    print(json.dumps(out, indent=1, default=str))
    open(BASE + "2b_rawcols.out.json", "w").write(json.dumps(out, indent=1, default=str))


run_ro(work)
