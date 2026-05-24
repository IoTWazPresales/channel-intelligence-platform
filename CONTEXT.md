# Channel Intelligence Platform — Current Context

## Branch
`main`

## Alembic Head
`20260517_0037`

## What Is Working (latest)

### DSI steward finalize (duplicate + async validate)
- **Duplicate detection Phase A** (post-`dfc0f2e`): dealer-group cascade; **`match_basis`** + source-customer secondary path; short-stem guards (TB/PC/BCS acronym cases). **BCS/RBS/SBC fix:** `computers`/`computer` generic; leading tokens ≤3 must match exactly; spaced acronyms collapsed (`B C S` → `bcs`). Revalidate after deploy to refresh hints.
- **Duplicate hint contract Phase A.5** (types/parsing only): `dsi_duplicate_hint_contract.py` + `dsiDuplicateHintContract.ts` — reserved parse-safe bases (`temporal_same_disti`, `cross_disti`, `source_customer_similar`); optional JSONB evidence keys (`matched_value`, `matched_field`, `dealer_group_norm`, `source_customer_norm`, `distributor_scope`, `evidence_reason`) without migration; annotate still emits Phase A bases only.
- **Duplicate detection Phase 1 + 1.5**: distinctive stem gate (≥ 0.90) then full-string (≥ 0.88 / relaxed 0.72); generic-only suffix matches suppressed; **short-token single-edit suppress** (e.g. NRC vs NGR); distributor-scoped overlap for hints.
- **Duplicate steward review**: `context.duplicate_review`; `acknowledged_unique`; plan gate `duplicate_review_required`; **Same entity** / **Different entity**; local plan refresh only (not full revalidate). **Same entity greenfield**: optional `customer_id` on POST — both peers null → provisional `dim_customer` from primary evidence + map both in one transaction; conflicting `suggested_entity_id` → 409. **Same entity guard**: self `peer_normalized_key` → 400; UI filters self from duplicate hints; `paired_normalized_key` stored from DB canonical keys.
- **Inline duplicate compare**: **Compare** / **Hide compare** under each peer in steward drawer (no scroll-to-top); optional **Open full steward for peer**; peer-not-on-page message when off current grid page.
- **Inter-disti hint**: validate-time `distributor_master_collision` on customer tokens matching `dim_distributor` name/code → steward info alert (sell-out counterparty; map as customer OK; buyer SOH from buyer’s own inventory import).
- **DSI validate/revalidate async UX**: `status=running` on dispatch; `dsi-progress` + `background-tasks` respect in-flight Celery; `notifyDsiAsyncPipelineStarted`; nav bell + `DsiValidateProgressPanel`; 409 on double dispatch; no blocking `pollDsiImportPipelineUntilDone` on HTTP.

### DSI steward workspace
- Entity tabs: Distributors → Customers → Products → **Region & channel**; paginated candidates; steward drawer per row.
- **Region evidence + ISO fallback**: `region_evidence` on plan rows; channel = geographic hints only; country fallback default off; geo tab + bulk apply suggested region.
- **Global background tasks**: nav bell, cancel/retry, Celery timeout on reads.
- **Import jobs list**: paginated projection (no heavy JSONB on list).

### Performance (DSI validate)
- `ShipmentCorroborationCache` + `DSIResolutionCache` — near-zero per-row DB in validate loop.
- Celery `PROGRESS` meta → `GET .../dsi-progress`.

## Steward policies (documented behaviour)

| Topic | Policy |
|--------|--------|
| **Duplicates** | Hints are review-required only (dealer group and/or source customer basis); steward must confirm Same/Different before plan apply when unresolved. |
| **Region** | Prefer **one `dim_customer`**, multiple regions via **`customer_location`** / region evidence — do **not** auto-split customers by region in duplicate logic. |
| **Inter-disti in customer column** | Map as **sell-out counterparty** on seller’s file; link to distributor master when useful; **does not** write buyer’s `fact_inventory_distributor`. |
| **Revalidate** | After steward bulk/plan/single-row map: optional **Re-run import validation (server)**; duplicate Same/Different uses **local plan refresh** only. |

## Scoped for later (do not implement without explicit approval)

| Feature | Notes |
|---------|--------|
| **Duplicate Phase 2** | Cluster connected components; one provisional leader + map siblings in-job; richer plan copy. |
| **Distributor hub / branch SOH** | `distributor_location` exists in master; **`fact_inventory_distributor` is per-distributor only** (no `location_id`). Later: per-location SOH, hub vs branch, transfer lines from files. |
| **Inter-disti stock reconciliation** | Derived receipt at buyer from seller sell-out vs buyer inventory snapshot — separate from steward map. |
| **Duplicate Phase 1.5+** | Registry/VAT columns; cross-job learning; phonetic keys — only if steward load still high. |
| **Web / external enrichment** | Deferred — low trust, ops cost. |
| **Open peer cross-page** | Optional API lookup by `normalized_key` when peer not on current candidates page. |
| **shipment_evidence_line.distributor_id index** | `CREATE INDEX CONCURRENTLY` when approved. |
| **DSI upload Celery infer** | Still inline (`infer_dsi_job_sync`). |

## Runtime (local dev, no Docker)
- Web: http://localhost:3000 (`pnpm dev:web`)
- API: http://localhost:8001 (`pnpm dev:api`)
- Worker: `pnpm dev:worker` (Redis :6379)
- DB: localhost:5432 / `cip` — **never run pytest against `cip` without explicit opt-in**

## Key paths (DSI steward finalize)
| Area | Path |
|------|------|
| Duplicate cascade | `apps/api/app/services/imports/dsi_customer_name_normalization.py` |
| Duplicate hint contract | `apps/api/app/services/imports/dsi_duplicate_hint_contract.py`, `apps/web/src/features/import-steward/dsiDuplicateHintContract.ts` |
| Duplicate + inter-disti annotate | `apps/api/app/services/imports/dsi_customer_intelligence.py` |
| Steward duplicate ops | `apps/api/app/services/imports/dsi_steward_candidate_ops.py` |
| Async dispatch / progress | `apps/api/app/api/v1/endpoints/imports.py`, `import_job_background_metadata.py` |
| Inline peer UI | `apps/web/src/features/import-steward/dsiDuplicatePeerCompare.tsx`, `dsi-mapping-steward-panel.tsx` |
| Async validate UX | `apps/web/src/features/import-steward/dsiAsyncPipelineRun.ts`, `imports/page.tsx` |

## Tests (safe — no DB)
- `apps/api/tests/test_dsi_duplicate_detection_cascade.py`
- `apps/api/tests/test_dsi_duplicate_hint_contract.py`
- `apps/api/tests/test_dsi_duplicate_phase_a.py`
- `apps/api/tests/test_dsi_distributor_name_collision.py`
- `apps/api/tests/test_dsi_duplicate_review.py` (if pure unit — verify before run)
- `apps/api/tests/test_dsi_job_progress.py`, `test_background_tasks.py`
- `apps/web/src/features/import-steward/dsiStewardCandidateFilterLogic.test.ts`

Run API unit tests from `apps/api`:  
`python -m pytest tests/test_dsi_duplicate_detection_cascade.py tests/test_dsi_distributor_name_collision.py tests/test_dsi_customer_name_normalization.py tests/test_dsi_job_progress.py tests/test_background_tasks.py -q`  
(Do **not** set `ALLOW_TESTS_ON_DEV_DB=1` unless intentionally testing against `cip`.)

## What Is Next (product)
- Move to next feature branch after commit of finalize slice.
- Hub/branch inventory epic when scheduled — see **Scoped for later**.
