"""READ-ONLY: cross-checks of the 151 distinct unmatched item codes (job 1697) against other tables/jobs.
Reads the identifiers from the earlier read-only dump (no write anywhere)."""
import json
import re

from ro import q, run_ro

BASE = ".eif/audit/OVERNIGHT_20261102/queries/"
rows = json.load(open(BASE + "2b_analyse_rows.out.json"))
ITEMS = sorted({r["item_code"].strip().lower() for r in rows})
EANS = sorted({(r["ean_code"] or "").strip() for r in rows if r["ean_code"]})
UPCS = sorted({(r["upc_code"] or "").strip() for r in rows if r["upc_code"]})
MODELS = sorted({r["sales_model_name"].strip().lower() for r in rows if r["sales_model_name"]})
J = 1697


async def work(db):
    out = {"n_items": len(ITEMS), "n_eans": len(EANS), "n_upcs": len(UPCS), "n_models": len(MODELS)}
    # 1. master: any row where any identifier column equals the line token, with loose normalisation done in SQL
    out["master_any_identifier_loose"] = await q(db, """
        select count(*) n from dim_product p
        where lower(regexp_replace(coalesce(p.sku,''),'[^a-zA-Z0-9]','','g')) = any(:items_n)
           or lower(regexp_replace(coalesce(p.part_number,''),'[^a-zA-Z0-9]','','g')) = any(:items_n)
           or lower(regexp_replace(coalesce(p.sales_model_name,''),'[^a-zA-Z0-9]','','g')) = any(:models_n)
           or lower(regexp_replace(coalesce(p.model_name,''),'[^a-zA-Z0-9]','','g')) = any(:models_n)
           or regexp_replace(coalesce(p.ean,''),'\\D','','g') = any(:eans)
           or regexp_replace(coalesce(p.upc,''),'\\D','','g') = any(:upcs)""",
        items_n=[re.sub(r"[^a-z0-9]", "", i) for i in ITEMS], models_n=[re.sub(r"[^a-z0-9]", "", m) for m in MODELS], eans=EANS, upcs=UPCS)
    # leading-zero variants of barcodes (EAN-13 vs UPC-12 padding)
    out["master_barcode_leading_zero_variant"] = await q(db, """
        select count(*) n from dim_product p
        where ltrim(regexp_replace(coalesce(p.ean,''),'\\D','','g'),'0') = any(:eans0) or ltrim(regexp_replace(coalesce(p.upc,''),'\\D','','g'),'0') = any(:eans0)
           or ltrim(regexp_replace(coalesce(p.ean,''),'\\D','','g'),'0') = any(:upcs0) or ltrim(regexp_replace(coalesce(p.upc,''),'\\D','','g'),'0') = any(:upcs0)""",
        eans0=[e.lstrip("0") for e in EANS], upcs0=[u.lstrip("0") for u in UPCS])
    # 2. other catalogue / alias tables
    out["catalog_product_by_sku"] = await q(db, "select count(*) n from catalog_product where lower(source_sku) = any(:items)", items=ITEMS)
    out["catalog_product_total"] = await q(db, "select count(*) n, count(canonical_product_id) linked from catalog_product")
    out["product_alias_by_value"] = await q(db, "select count(*) n from product_alias where lower(trim(alias_value)) = any(:v)", v=ITEMS + MODELS + [e.lower() for e in EANS])
    out["customer_article_alias_total"] = await q(db, "select status, count(*) n from customer_article_alias group by 1")
    # 3. same codes in other shipment evidence jobs: resolved or not
    out["same_item_other_jobs"] = await q(db, """
        select (product_id is not null) resolved, count(*) lines, count(distinct lower(trim(item_code))) distinct_items, count(distinct import_job_id) jobs
        from shipment_evidence_line where import_job_id <> :j and lower(trim(item_code)) = any(:items) group by 1""", j=J, items=ITEMS)
    out["first_job_seen_unmatched"] = await q(db, """
        select min_job, count(*) n_items from (select lower(trim(item_code)) ic, min(import_job_id) min_job from shipment_evidence_line
          where lower(trim(item_code)) = any(:items) and product_id is null group by 1) t group by 1 order by 1""", items=ITEMS)
    # 4. DSI mapping candidates / staging / pricing unknown SKU referencing these tokens
    out["dsi_mapping_candidates_product"] = await q(db, """
        select status, count(*) n, sum(total_units) units from import_entity_mapping_candidate
        where entity_type ilike 'product%' and (lower(normalized_key) = any(:items) or lower(normalized_key) = any(:models)) group by 1""", items=ITEMS, models=MODELS)
    out["mapping_candidate_entity_types"] = await q(db, "select entity_type, status, count(*) n from import_entity_mapping_candidate group by 1,2 order by 3 desc limit 40")
    # 5. master age: is the catalogue stale relative to the report?
    out["master_created_by_month"] = await q(db, "select to_char(date_trunc('month', created_at),'YYYY-MM') m, count(*) n from dim_product group by 1 order by 1 desc limit 8")
    out["master_max_dates"] = await q(db, "select max(created_at) max_created, max(updated_at) max_updated, max(launch_date) max_launch from dim_product")
    # 6. master families: how many masters per 8-char sku prefix for the unmatched items (prefix present?)
    out["sku_prefix_presence"] = await q(db, """
        with items as (select distinct split_part(i,'-',1) pre from unnest(cast(:items as text[])) i)
        select count(*) prefixes, count(*) filter (where exists (select 1 from dim_product p where lower(split_part(p.sku,'-',1)) = items.pre)) prefix_in_master from items""", items=ITEMS)
    out["model_base_presence"] = await q(db, """
        with m as (select distinct split_part(i,'-',1) base from unnest(cast(:models as text[])) i)
        select count(*) bases, count(*) filter (where exists (select 1 from dim_product p where lower(split_part(p.sales_model_name,'-',1)) = m.base or lower(p.model_name) = m.base)) base_in_master from m""", models=MODELS)
    # 7. resolved lines in the SAME job: how do their master rows look (sku tier = exact sku). count of masters touched
    out["resolved_same_job_distinct_products"] = await q(db, "select count(distinct product_id) n from shipment_evidence_line where import_job_id=:j and product_id is not null", j=J)
    # 8. inactive_only lines (12): what are they
    out["inactive_only_lines"] = await q(db, """select e.item_code, e.sales_model_name, e.quantity, e.line_state, p.sku, p.is_active, p.lifecycle_status, p.retired_date
        from shipment_evidence_line e left join dim_product p on lower(trim(p.sku)) = lower(trim(e.item_code))
        where e.import_job_id=:j and e.product_resolution_status='inactive_only' order by e.quantity desc""", j=J)
    print(json.dumps(out, indent=1, default=str))
    open(BASE + "2b_crosscheck.out.json", "w").write(json.dumps(out, indent=1, default=str))


run_ro(work)
