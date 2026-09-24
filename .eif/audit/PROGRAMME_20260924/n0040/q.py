"""N-0040 discovery: read-only queries against cip (session read_only; rollback)."""
import sys
import psycopg

QUERIES = {
    "fk_to_dim_product": """
        select c.conrelid::regclass::text as tbl, a.attname as col
        from pg_constraint c
        join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any(c.conkey)
        where c.contype = 'f' and c.confrelid = 'dim_product'::regclass
        order by 1""",
    "catalog_tables": """
        select table_name, string_agg(column_name, ',') from information_schema.columns
        where table_schema='public' and (table_name ilike '%catalog%' or table_name ilike '%product_master%')
        group by 1 order by 1""",
    "jsonb_product_line_in_catalog_attrs": """
        select count(*) from information_schema.columns
        where table_schema='public' and column_name ilike '%line%' and table_name ilike '%catalog%'""",
    "lineup_cases_by_period_bu": """
        select inferred_period_start, business_unit, count(*) filter (where commercial_status<>'superseded') active,
               count(*) filter (where commercial_status='superseded') superseded
        from commercial_lineup_case group by 1,2 order by 1,2""",
    "lineup_bu_source_tier": """
        select coalesce(j.staged_metadata->'lineup_bu_resolution'->>'source_tier','(none)') tier, c.business_unit, count(*)
        from commercial_lineup_case c left join import_job j on j.id=c.import_job_id
        group by 1,2 order by 1,2""",
    "lineup_lines_by_case_bu_vs_product_line": """
        select c.business_unit case_bu, coalesce(p.product_line,'(no product)') line_pl, count(*)
        from commercial_lineup_line l join commercial_lineup_case c on c.id=l.case_id
        left join dim_product p on p.id=l.product_id
        where c.commercial_status<>'superseded'
        group by 1,2 order by 1,3 desc""",
    "supersession_pairs": """
        select l.id loser, l.business_unit lbu, l.inferred_period_start lps, w.id winner, w.business_unit wbu,
               w.inferred_period_start wps, w.commercial_status wstatus
        from commercial_lineup_case l left join commercial_lineup_case w on w.id=l.superseded_by_case_id
        where l.commercial_status='superseded' or l.superseded_by_case_id is not null order by 1""",
    "cpor_lines_by_product_line": """
        select coalesce(p.product_line,'(null)'), count(*) from cpor_case_line x join dim_product p on p.id=x.product_id group by 1 order by 2 desc""",
    "null_pl_usage": """
        select 'shipment_evidence_line' t, count(*) from shipment_evidence_line where product_id in (select id from dim_product where product_line is null)
        union all select 'fact_customer_sellthrough', count(*) from fact_customer_sellthrough where product_id in (select id from dim_product where product_line is null)
        union all select 'fact_inventory_distributor', count(*) from fact_inventory_distributor where product_id in (select id from dim_product where product_line is null)
        union all select 'fact_inventory_customer', count(*) from fact_inventory_customer where product_id in (select id from dim_product where product_line is null)
        union all select 'cpor_case_line', count(*) from cpor_case_line where product_id in (select id from dim_product where product_line is null)
        union all select 'commercial_plan_line', count(*) from commercial_plan_line where product_id in (select id from dim_product where product_line is null)
        union all select 'fact_sales_sellin', count(*) from fact_sales_sellin where product_id in (select id from dim_product where product_line is null)
        union all select 'product_alias', count(*) from product_alias where product_id in (select id from dim_product where product_line is null)
        union all select 'catalog_product', count(*) from catalog_product where canonical_product_id in (select id from dim_product where product_line is null)""",
    "shipment_evidence_by_product_line": """
        select coalesce(p.product_line,'(null)'), count(*) from shipment_evidence_line s join dim_product p on p.id=s.product_id group by 1 order by 2 desc""",
    "catalog_meta_product_line": """
        select coalesce(source_metadata_json->>'product_line', source_metadata_json->>'Product Line', '(absent)') pl, count(*)
        from catalog_product group by 1 order by 2 desc limit 25""",
    "catalog_meta_keys": """
        select k, count(*) from catalog_product, jsonb_object_keys(source_metadata_json::jsonb) k group by 1 order by 2 desc limit 40""",
    "catalog_snapshot_product_line": """
        select '['||coalesce(source_metadata_json::jsonb->'row_staged_snapshot'->>'product_line','(absent)')||']' pl, count(*)
        from catalog_product group by 1 order by 2 desc""",
    "catalog_snapshot_keys": """
        select k, count(*) from catalog_product, jsonb_object_keys(source_metadata_json::jsonb->'row_staged_snapshot') k
        where jsonb_typeof(source_metadata_json::jsonb->'row_staged_snapshot')='object' group by 1 order by 2 desc limit 40""",
    "cpor_null_line": """
        select x.id, x.case_id, x.product_id, p.sku from cpor_case_line x join dim_product p on p.id=x.product_id where p.product_line is null""",
    "catalog_base_unit": """
        select '['||coalesce(source_metadata_json::jsonb->'row_staged_snapshot'->>'base_unit','(absent)')||']' bu, count(*)
        from catalog_product group by 1 order by 2 desc""",
    "catalog_bg": """
        select '['||coalesce(source_metadata_json::jsonb->'row_staged_snapshot'->>'bg','(absent)')||']' bg, count(*)
        from catalog_product group by 1 order by 2 desc""",
    "catalog_base_unit_vs_dim": """
        select coalesce(source_metadata_json::jsonb->'row_staged_snapshot'->>'base_unit','(absent)') bu, coalesce(p.product_line,'(null)') pl, count(*)
        from catalog_product c left join dim_product p on p.id=c.canonical_product_id
        where coalesce(source_metadata_json::jsonb->'row_staged_snapshot'->>'base_unit','(absent)') <> coalesce(p.product_line,'(null)')
        group by 1,2 order by 3 desc""",
    "lineup_line_base_unit_raw": """
        select '['||base_unit_raw||']', count(*) from commercial_lineup_line group by 1 order by 2 desc""",
    "catalog_base_unit_line": """
        select substr(source_metadata_json::jsonb->'row_staged_snapshot'->>'base_unit',3,2) line, count(*)
        from catalog_product group by 1 order by 2 desc""",
    "catalog_base_unit_line_vs_dim": """
        select substr(source_metadata_json::jsonb->'row_staged_snapshot'->>'base_unit',3,2) cat_line, coalesce(p.product_line,'(null)') dim_pl, count(*)
        from catalog_product c left join dim_product p on p.id=c.canonical_product_id
        group by 1,2 having substr(source_metadata_json::jsonb->'row_staged_snapshot'->>'base_unit',3,2) is distinct from coalesce(p.product_line,'(null)') order by 3 desc""",
    "catalog_odd_base_units": """
        select left(source_metadata_json::jsonb->'row_staged_snapshot'->>'base_unit',6) prefix6, coalesce(p.product_line,'(null)') dim_pl, count(*)
        from catalog_product c left join dim_product p on p.id=c.canonical_product_id
        where substr(source_metadata_json::jsonb->'row_staged_snapshot'->>'base_unit',3,2) in ('-9','-X') or source_metadata_json::jsonb->'row_staged_snapshot'->>'base_unit' is null
        group by 1,2 order by 3 desc limit 20""",
    "catalog_bg_goc": """
        select source_metadata_json::jsonb->'row_staged_snapshot'->>'bg' bg, count(distinct source_metadata_json::jsonb->'row_staged_snapshot'->>'goc') gocs, count(*)
        from catalog_product group by 1 order by 3 desc""",
    "lineup_base_unit_raw_distinct": """
        select count(distinct base_unit_raw), count(*) filter (where base_unit_raw is null) from commercial_lineup_line""",
    "dim_product_line_upper_distinct_with_null": """
        select count(distinct coalesce(upper(trim(product_line)),'<NULL>')) from dim_product""",
    "product_catalogs": "select id, code, name, is_active from product_catalog order by id",
}


def main() -> None:
    names = sys.argv[1:] or list(QUERIES)
    conn = psycopg.connect(host="localhost", port=5432, user="cip", password="cip", dbname="cip")
    conn.read_only = True
    cur = conn.cursor()
    cur.execute("select current_database()")
    print("db =", cur.fetchone()[0])
    for n in names:
        print("==", n)
        try:
            cur.execute(QUERIES[n])
            if cur.description:
                print(" | ".join(d[0] for d in cur.description))
                for r in cur.fetchall():
                    print(" | ".join("" if v is None else str(v) for v in r))
        except Exception as e:  # noqa: BLE001
            print("ERR", e)
            conn.rollback()
    conn.rollback()
    conn.close()


if __name__ == "__main__":
    main()
