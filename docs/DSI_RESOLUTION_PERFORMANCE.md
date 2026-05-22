# DSI resolution steward — performance and intelligence notes

## Embedding-based duplicate detection (not implemented)

**Flagged — stopped before implementation.**

True embedding similarity would require a new dependency (e.g. `sentence-transformers`, OpenAI embeddings API) and likely a persistence layer (vector column or side table + migration) to avoid recomputing vectors on every validate.

**Current approach:** text similarity after legal-suffix normalisation (`dsi_customer_name_normalization.py`) and pairwise `difflib.SequenceMatcher` within the import job (`annotate_dsi_customer_candidate_duplicates` in `dsi_customer_intelligence.py`). Scores are stored on candidate context as:

```json
"possible_duplicate_of": [{ "normalized_key": "…", "similarity_score": 0.87 }]
```

Threshold default: `0.82` (aligned with shipment evidence steward heuristics).

---

# DSI resolution steward — performance notes

## `GET/POST …/dsi-unresolved-geo-tokens` (~31s observed)

### Root cause

`collect_dsi_job_unresolved_geo_tokens_sync` loaded every `customer_dealer_token` candidate for the job, then for **each** candidate called `_resolve_source_geo_from_ctx`, which issued multiple SQL lookups:

- `DimChannel` / `DimRegion` by code or normalized name (per evidence token)
- `ChannelSourceTokenAlias` / `RegionSourceTokenAlias` by `normalized_token` (per token)

For jobs with thousands of customer candidates (e.g. ~4,600+), this became **O(candidates × queries)** with no catalog or alias batching.

### Fix (code)

`app/services/imports/dsi_geo_resolution_cache.py`:

- Preload all `DimChannel` and `DimRegion` rows into in-memory maps once per request.
- Collect normalized evidence tokens from all candidates, then **one** `IN (...)` query per alias table.
- `collect_dsi_job_unresolved_geo_tokens_sync` uses `DSIGeoResolutionCache` instead of per-row DB resolution.

The same cache is used for bulk provisional customer geo derivation (`derive_effective_provisional_customer_geo_sync` with `geo_cache=`).

### Recommended indexes (not applied in this change — review before migration)

| Table | Suggested index | Rationale |
|-------|-----------------|-----------|
| `import_entity_mapping_candidate` | `(import_job_id, entity_type)` | Geo collection filters on both; today often only `import_job_id` is indexed. |
| `channel_source_token_alias` | `(normalized_token)` WHERE `status = 'approved'` (or composite `(normalized_token, status)`) | Batch alias preload uses `normalized_token IN (...)` + `status`. |
| `region_source_token_alias` | Same as channel | Same pattern. |

Verify existing indexes with `EXPLAIN (ANALYZE, BUFFERS)` on a representative job before adding migrations.

---

## Bulk provisional customer creation

### Root cause

`dsi-steward-bulk-apply` with `create_provisional_customer` looped `execute_create_provisional_dsi_customer`, which **`await db.commit()` per candidate**. Each commit was expensive; the UI then invalidated steward queries (including resolution plan), which could refetch heavy plan payloads repeatedly during long applies.

### Fix (code)

- `run_dsi_bulk_provisional_customers_sync`: one transaction, **single commit** after all creates.
- Celery task `imports.dsi_bulk_provisional_customers` with progress meta.
- `POST …/dsi-steward-bulk-provisional-customers/apply-async` + `GET …/dsi-steward-bulk-task/{task_id}`.
- Sync `dsi-steward-bulk-apply` rejects `create_provisional_customer` (use async path).
- Frontend: one enqueue + poll, **one** `invalidateDsiImportJobStewardQueries` on success (no optimistic cache update during provisional bulk).
