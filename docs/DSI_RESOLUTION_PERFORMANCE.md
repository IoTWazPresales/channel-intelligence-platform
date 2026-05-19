# DSI resolution performance notes

## Root cause (plan slowness at ~5k candidates)

`POST /mappings/import-jobs/{id}/dsi-resolution-plan` called `build_dsi_resolution_plan_sync` with **`candidate_ids` omitted**, so the service loaded **every** `import_entity_mapping_candidate` for the job and ran `plan_dsi_candidate_sync` once per row.

Per candidate, the uncached path performed multiple SQL round-trips:

- `_resolve_distributor` — full `DimDistributor` scan + alias query
- `_resolve_customer` — alias + code/name lookups
- `derive_effective_provisional_customer_geo_sync` — region/channel catalog + alias queries via `session.get`
- Product historical disambiguation — optional `db=session` shipment corroboration queries

With **5,337 candidates**, that is tens of thousands of queries (27–37s observed).

## Root cause (UI freeze on load)

`GET /mappings/import-jobs/{id}/distributor-si-candidates` returned **all** rows; the web app rendered the full list and keyed the resolution-plan query on every id.

## Fixes implemented (no migration applied)

### Candidates API

- Paginated `GET` with `skip`, `limit` (default 100, max 1000), `total` in response.
- Server-side filters: `entity`, `party`, `verify_name_only`, `special_category_only`, `possible_duplicates_only`, `status`.

### Plan API

- `DSIPlanBuildContext`: one-time preload of product index, `DSIResolutionCache`, regions/channels, geo aliases.
- Plan path uses in-memory distributor/customer/geo resolution (no per-row table scans).
- Ambiguous product with a single `eligible_products` entry resolves from **context** (no corroboration DB).
- Frontend sends **`candidate_ids` for the current page only** (max 1000).
- If `candidate_ids` is omitted, server plans at most **100** rows and returns `plan_scope_note`.

### Frontend

- TanStack Query page state, pagination controls, rows-per-page 100/250/500/1000.
- Queue filter chips remain **client-side on the current page** (depend on plan rows).

## Recommended index (migration not run — flag for approval)

Existing: `import_job_id` index, unique `(import_job_id, entity_type, normalized_key)`.

Suggested for large jobs (list + filter by job + entity + status):

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_iemc_job_entity_status
  ON import_entity_mapping_candidate (import_job_id, entity_type, status);
```

Optional JSONB party filter (if used heavily):

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_iemc_context_party
  ON import_entity_mapping_candidate ((context->>'party'))
  WHERE entity_type = 'distributor_token';
```

Do **not** run against `cip` without explicit approval.

## Further optimizations (after this change)

1. **Materialized plan snapshot** — store plan rows on validate completion; GET plan becomes read-only.
2. **Background plan job** — Celery task for “plan all open candidates” with progress UI (like DSI validate).
3. **Server-side queue filter** — persist `suggested_action` on candidate at validate time to filter without full replan.
4. **Geo token endpoint** — paginate `dsi-unresolved-geo-tokens` if slow on large jobs.
5. **Virtualized table** — `@tanstack/react-virtual` if row height grows with many columns.
