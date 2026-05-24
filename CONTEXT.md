# Channel Intelligence Platform — Current Context

## Branch
`main`

## Alembic Head
`20260517_0037`

## What Is Working (latest)

### DSI steward finalize (duplicate + async validate)
- **Duplicate detection Phase 1 (extended)** — validate-time hints via `annotate_dsi_customer_candidate_duplicates`:
  - Existing cascade: `dealer_group_exact` / `dealer_group_similar`, `source_customer_exact`; BCS/RBS/TB short-stem guards unchanged.
  - **New active bases:** `dealer_group_prefix_stem` (e.g. Adriane + t/a tail), `dealer_group_shared_label_different_counterparty` (same dealer-group label, different source-customer strings), `source_customer_similar` (similar counterparty norms).
  - **Revalidate required** after deploying hint logic to refresh `possible_duplicate_of` on open jobs (e.g. job 733).
- **Steward UX Phase 1–3** (commit `afb682f`): sticky steward column + scrollable grid; drawer closes after steward action; `acknowledged_unique` blocks mapping buttons; duplicate **cluster** + **suffix-family** informational alerts; pipeline timestamps; blocking refetch on validate complete.
- **Same-entity Phase A + B:** unified same-entity dialog (search, suggestions, provisional display name); API `display_name` + `plan_suggested_target_id`; bulk map uses customer search; **Region (file)** / **Channel (file)** grid columns.
- **Plan sibling hints:** `sibling_mapping_hint` on customer plan rows when another token on the same job (same dealer-group norm) already maps to a `dim_customer` — `needs_review`, not auto-ready.
- **Cluster steward Phase 3:** `POST .../import-jobs/{job_id}/duplicate-review/cluster-same-entity` maps N tokens in one transaction; UI **Map cluster to one customer…** on cluster alert in steward drawer.
- **Duplicate hint contract:** `dsi_duplicate_hint_contract.py` + `dsiDuplicateHintContract.ts` — active + reserved bases; optional JSONB evidence keys without migration.
- **Duplicate steward review:** `context.duplicate_review`; plan gate `duplicate_review_required`; Same/Different; local plan refresh (not full revalidate) after pairwise actions.
- **Inter-disti hint**, **async validate UX** — unchanged.

### DSI steward workspace
- Entity tabs: Distributors → Customers → Products → **Region & channel**; paginated candidates; steward drawer per row.
- **Region evidence + ISO fallback**; global background tasks; import jobs list projection.

### Performance (DSI validate)
- `ShipmentCorroborationCache` + `DSIResolutionCache`; Celery `PROGRESS` meta → `GET .../dsi-progress`.

## Steward policies (documented behaviour)

| Topic | Policy |
|--------|--------|
| **Duplicates** | Hints are review-required only; steward confirms Same/Different before plan apply when unresolved. Shared dealer-group label + different counterparty → hint (not auto-suppress). |
| **Region** | One `dim_customer`, multiple regions via evidence — do not auto-split by region in duplicate logic. |
| **Revalidate** | After hint-logic deploy: re-run server validation on affected jobs. Pairwise/cluster steward actions use local plan refresh only. |

## Scoped for later (do not implement without explicit approval)

| Feature | Notes |
|---------|--------|
| **Duplicate validate-time cluster_id** | Optional `duplicate_cluster_id` on context from server union-find (UI union-find remains). |
| **Customer master merge** | Phase E — merge provisional duplicates in master, not import steward. |
| **Duplicate Phase 1.5+** | Registry/VAT; cross-job learning; phonetic keys. |
| **Distributor hub / branch SOH**, **inter-disti stock reconciliation**, **open peer cross-page**, **shipment_evidence_line index**, **DSI upload Celery infer** — unchanged deferred items. |

## Runtime (local dev, no Docker)
- Web: http://localhost:3000 (`pnpm dev:web`)
- API: http://localhost:8001 (`pnpm dev:api`)
- Worker: `pnpm dev:worker` (Redis :6379)
- DB: localhost:5432 / `cip` — **never run pytest against `cip` without explicit opt-in**

## Key paths (DSI steward finalize)
| Area | Path |
|------|------|
| Duplicate cascade + stem | `apps/api/app/services/imports/dsi_customer_name_normalization.py` |
| Duplicate hint contract | `apps/api/app/services/imports/dsi_duplicate_hint_contract.py`, `apps/web/src/features/import-steward/dsiDuplicateHintContract.ts` |
| Duplicate annotate + sibling index | `apps/api/app/services/imports/dsi_customer_intelligence.py` |
| Plan build + sibling hint | `apps/api/app/services/imports/dsi_plan_build_context.py`, `dsi_resolution_plan.py` |
| Steward duplicate + cluster ops | `apps/api/app/services/imports/dsi_steward_candidate_ops.py`, `mappings.py` |
| Cluster UI | `apps/web/src/features/import-steward/DsiDuplicateClusterSameEntityDialog.tsx`, `dsiDuplicateCluster.ts` |

## Tests (safe — no DB)
- `apps/api/tests/test_dsi_duplicate_detection_cascade.py`
- `apps/api/tests/test_dsi_duplicate_hint_contract.py`
- `apps/api/tests/test_dsi_duplicate_phase_a.py`
- `apps/api/tests/test_dsi_duplicate_review.py`
- `apps/web/src/features/import-steward/dsiDuplicateSameEntityDialogLogic.test.ts`
- `apps/web/src/features/import-steward/dsiDuplicateCluster.test.ts`

Run API unit tests from `apps/api`:  
`.\.venv\Scripts\python.exe -m pytest tests/test_dsi_duplicate_*.py -q`

## What is next
- **Revalidate job 733** (user-triggered) after pulling hint-logic changes to refresh `possible_duplicate_of`.
- Optional: customer master merge (Phase E); server-side `duplicate_cluster_id` on validate.
