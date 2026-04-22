# Platform Data Model And Lineage

## Data layers
- **Raw**: uploaded bytes in storage backend, referenced by `raw_file_metadata`.
- **Ingestion control**: `import_template`, `source_definition`, `import_job`, `import_row_result`.
- **Canonical dimensions**: `dim_product`, `dim_customer`, `dim_channel`, `dim_distributor`, `dim_region`, others.
- **Operational facts**: `fact_inventory_customer`, `fact_forecast`, `fact_pricing`, `fact_promotion_plan`, etc.
- **Derived/recommendation entities**: stock, buy, pricing, promotion readiness, budget health, exception inbox.
- **Catalog overlay**: `product_catalog`, `catalog_product`, `attribute_definition`, `product_attribute_value`.

## Key entity relationships
- `source_definition` -> `import_template` (many-to-one), optional `product_catalog_id`.
- `import_job` -> `source_definition` and -> `raw_file_metadata` / `import_row_result`.
- `catalog_product` links a catalog row to canonical `dim_product` via `canonical_product_id`.
- `product_attribute_value` links catalog product + attribute definition (EAV typed-as-JSON pattern).
- Fact tables mostly link back to dimension keys (`dim_product`, `dim_customer`, etc.).

## Product Master lineage (current truth)
1. Upload creates `import_job` + `raw_file_metadata`.
2. Header inference and mapping decisions stored on `import_job`.
3. Validation writes staged metadata (`staged_metadata`) and row outcomes in `import_row_result`.
4. Commit phase writes canonical updates (`dim_product`) and catalog/EAV updates (`catalog_product`, `product_attribute_value`) when source has `product_catalog_id`.
5. Async commit metadata and state transitions persist in `import_job.status`, `import_job.stage`, and `pm_commit_meta`.

## Canonical vs staged vs derived distinction
- Canonical product identity lives in `dim_product`.
- Staged import evidence and validation messages are retained under `import_job`/`import_row_result`.
- Catalog-specific product expressions live in `catalog_product` + EAV namespace pattern (`catalog:{id}:{kind}:{header_slug}`).
- Derived planning/recommendation outputs are separate from ingestion and generally modeled in `derived.py`.

## Lineage observability currently available
- Import-level: job status/stage/error summary + row-level result records.
- Commit-level (Product Master): queued/running/failed timestamps and error fields in `pm_commit_meta`.
- API/UI expose these fields for user-visible progress and post-failure diagnosis.
