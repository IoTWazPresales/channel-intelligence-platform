"""READ-ONLY 2c step 3: indexes on alias tables, columns of dim tables and staging tables."""
import json
from ro import q, run_ro


async def work(db):
    out = {}
    for t in ("distributor_source_token_alias", "customer_source_token_alias", "import_entity_mapping_candidate"):
        out["idx_" + t] = [r["indexdef"] for r in await q(db, "select indexdef from pg_indexes where tablename=:t", t=t)]
    for t in ("dim_customer", "dim_distributor", "shipment_evidence_line", "import_distributor_si_staging_line",
              "import_customer_sellthrough_staging_line", "source_definition", "customer_article_alias",
              "customer_location", "entity_mapping_queue"):
        out["cols_" + t] = [r["column_name"] for r in await q(db, "select column_name from information_schema.columns where table_name=:t order by ordinal_position", t=t)]
    out["alias_tables"] = [r["table_name"] for r in await q(db, "select table_name from information_schema.tables where table_schema='public' and table_name like '%alias%'")]
    json.dump(out, open(".eif/audit/OVERNIGHT_20261102/queries/2c_meta.out.json", "w"), indent=1, default=str)


run_ro(work)
