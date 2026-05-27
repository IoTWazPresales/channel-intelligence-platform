# Channel Intelligence Platform — Current Context

## Branch
`main`

## Head commit
`2dbb95b` — `dsi: Phase 1 weekly intelligence state, auto-resolution, and SOH reconciliation`

## Alembic Head
`20260518_0041` — `fact_inventory_reconciliation` + `source_key` upsert grain. Applied on **`cip`** and **`cip_alembic_smoke`**.

---

## Latest work (May 2026) — DSI Phase 1 + Phase 2 (weekly uploads)

### Phase 1A — import state awareness
- `dsi_import_state_awareness.py`: `check_dsi_import_state(db, job_id, distributor_id)` → `intelligence_state` on `import_job.staged_metadata` (read-only; never blocks validate).
- Layers: `token_auto_resolution`, `soh_reconciliation`, `velocity_learning`, `pricing_intelligence`, `forecasting` with `active` / `degraded` / `initialising` / `inactive`.
- Auto-resolution tier from prior applied DSI jobs on same source: `none` (0) · `supervised` (1) · `automatic` (2+).
- Optional tables: `fact_customer_velocity` — missing → 0 weeks; **CPOR:** `_has_cpor_data` always `False` until a real CPOR import module exists (no proxy).
- Wired at end of validate cache load in `process_distributor_sales_inventory`.
- Tests: `tests/test_dsi_import_state_awareness.py` (14 tests, mocked DB).

### Phase 1B — weekly token auto-resolution
- `dsi_weekly_auto_resolution.py`: validate-time auto-resolve for **automatic** tier; plan-time **supervised** ready rows (`auto_resolved_supervised`).
- `load_historical_customer_resolutions`: steward rows keyed `(distributor_id, normalized_key)` with `(None, key)` fallback.
- Historical workflow unchanged; weekly-only tier logic in `plan_dsi_candidate_sync` and validate row loop.
- Tests: `tests/test_dsi_weekly_auto_resolution.py` (10 tests).

### Phase 1C — frontend
- `DsiIntelligenceStatusPanel.tsx` on validate step (reads `staged_metadata.intelligence_state`).
- Supervised review callout in `DsiImportJobResolutionSection` (`dsi-supervised-auto-resolve-section`).

### Phase 2 — SOH reconciliation
- Migration `20260518_0041`: `fact_inventory_reconciliation` with unique `source_key` (`dsi-recon:{distributor}:{product}:{customer_id|0}:{period_end}`).
- `reconcile_distributor_soh` updates `fact_inventory_distributor` + upserts customer-allocated / open-channel reconciliation rows.
- Post-apply dispatch: `dsi_soh_reconciliation_enqueue.py` → Celery `imports.dsi_soh_reconciliation` (detached thread fallback).
- Activity bell: `dsi_soh_reconcile_task`, kind `dsi_soh_reconciliation`.

### Validation (May 2026)
- `cip_alembic_smoke`: `alembic upgrade head` → `20260518_0041` (clean).
- Pytest (`test_dsi_import_state_awareness`, `test_dsi_soh_reconciliation`): **17 passed** (mocked DB; no `cip` writes).
- Browser/API E2E (`scripts/e2e_dsi_phase1_phase2_validate.py`, job **740** / **741** on `cip`):
  - **S1 pass** — `intelligence_state` panel + API payload; automatic tier (97 prior jobs on source 50).
  - **S2 skipped** — no source with exactly one prior applied job.
  - **S3 pass** — `auto_resolution_tier: automatic`.
  - **S4 pass** — post-apply `dsi_soh_reconcile_task` + `calculated_soh` on `fact_inventory_distributor` (dist **84**).
- **Fixes (May 2026):** JSONB `flag_modified` + end-of-validate re-persist for `intelligence_state`; `POST /dsi-apply` now calls `complete_dsi_import_job_to_loaded` (promotes to `loaded`, dispatches SOH reconcile).

### Next
- Supervised-tier browser check after a controlled “first apply” on a fresh source (or isolated test source).
- Kill stale API on **:8001** if it points at a non-`cip` DB; dev stack used **:8002** + `CIP_API_INTERNAL_URL` for web proxy during validation.
- Phase 3: velocity / forecasting job consumers on `intelligence_state` layers.

---

## Prior work (May 2026) — DSI Phase 0 foundations (shipped on `main`)

### What was built and why

Phase 0 establishes the **fact-layer foundations** for weekly DSI intelligence. Before this work, sell-out upserts used a month-level natural key, negative quantities landed in `fact_sales_sellout`, and inventory had no `source_key`. Returns had no home. Historical imports could not safely auto-apply after validate because `asyncio.run` inside the pipeline Celery task hung on Windows.

| Deliverable | Why |
|-------------|-----|
| **Migrations 0038–0040** | Day-level sell-out grain with `invoice_no` (`''` sentinel, not NULL — stable hash input); new `fact_returns`; inventory `source_key` + reconciliation placeholder columns |
| **Hashed `source_key` builders** (`dsi_fact_source_keys.py`) | Deterministic idempotent upsert: `dsi-sellout:` / `dsi-return:` / `dsi-soh:` prefixes |
| **Quantity routing on apply** | Positive → sell-out; negative → returns (abs qty); zero → skip both — matches commercial semantics |
| **Post-validate historical auto-apply** | Enqueues `dsi_resolution_plan_apply` via Celery or detached daemon thread — never inline `asyncio.run` on the validate thread |
| **Shared enqueue module** (`dsi_resolution_plan_enqueue.py`) | Steward apply-async and post-validate use the same dispatch path |

`period_start` and `transaction_date` are both populated from the staging transaction date on write (sell-out API still reads `period_start`; Phase 1 can unify).

### E2E results (local stack, May 2026)

- Services: `scripts/restart-dev.ps1` — Redis PONG, worker, API `/health`, web `:3000`
- **Scenario 1:** negative qty → `fact_returns` (by `invoice_no`); not in `fact_sales_sellout` — PASS
- **Scenario 2:** re-upload idempotent; qty update on same `source_key` only — PASS
- **Scenario 3:** historical validate enqueues `dsi_post_validate_auto_apply`; weekly does not; activity bell shows `dsi_pipeline` during validate — PASS
- Focused pytest (7 Phase 0 tests): PASS with `ALLOW_TESTS_ON_DEV_DB=1`
- Fixtures: `tests/e2e/fixtures/dsi_e2e_*.csv`

### Architectural decisions locked in Phase 0

1. **Invoice grain:** `distributor_id + product_id + customer_id + transaction_date + invoice_no` (empty string `''` when absent — never NULL in keys).
2. **Returns conflict:** update `return_quantity` and `unit_price` only; `import_job_id` owned by first job (audit record).
3. **Sell-out conflict:** update measures and `source_import_job_id` only — not identity columns.
4. **Inventory:** upsert on `source_key`; drop `uq_fact_inventory_distributor_dsi_v1`; reconciliation columns null until reconciliation jobs run.
5. **Post-validate:** historical workflow only; ready candidates only; excludes `hold_for_manual_review` and `needs_review`.
6. **DSI resolution order / steward governance / corroboration tier order:** unchanged.

---

## Prior work (May 2026) — DSI steward scale + product shipment tie-break

### Shipped on feature branch (`ca4ca57`)
| Area | What changed |
|------|----------------|
| **P0 async apply** | `POST .../dsi-resolution-plan/apply-async` → Celery `imports.dsi_resolution_plan_apply`; poll `.../dsi-steward-bulk-task/{task_id}`; activity bell kind `dsi_resolution_plan_apply` |
| **Apply perf** | Product resolution index loaded **once** per task; chunks of 25 candidates; sync `/apply` capped at 50 ids |
| **409 lock** | `dsi_steward_task_dispatch.py` blocks apply when pipeline or `dsi_bulk_task` active |
| **P1 product tie-break** | `dsi_product_shipment_tiebreak.py` — uses `shipment_distinct_product_ids` + `dominant_evidence_month` on candidate context (set on **next revalidate**) |
| **P1 plan labels** | `suggested_target_label` on plan rows (customer/distributor/product names) |
| **P1/P2 UX** | Single **Review…** row action; plan column shows target label; corroboration chip → **Shipment lines found** vs tie-break; resolution panel **one scroll parent** |

### Not changed
- Shipment evidence import module (read-only corroboration only)
- DSI eligibility / corroboration tier order
- Duplicate detection logic

### Job 733 note
- Existing candidates lack new context fields until **revalidate**. Tie-break at plan time uses stored ids when present; else live `_shipment_disambiguate_product_id`.
- Async apply needs **Redis + worker** (or `CIP_DEV_CELERY_DISPATCH=in_process_thread` when Celery enqueue fails). Stale `dsi_bulk_task` in metadata blocks sync apply until cleared or task completes.

### Validation run
- API: 57 tests (`test_dsi_resolution_plan`, bulk steward, tiebreak)
- Web: 39 tests (`import-steward` features)
- API smoke: `apply-async` 202 + 409 lock; sync apply 1 customer ~5s
- Browser E2E job 733: blocked by Next.js dev overlay on imports grid (manual open job still OK)

### Next
- Merge feature branch after review
- Revalidate job 733 to populate `shipment_distinct_product_ids` / `dominant_evidence_month` on product candidates
- Optional: clear stale `dsi_bulk_task` when Celery task orphaned (PENDING + no worker)

---

## Prior work (on `main`)
- Root-identity duplicate scorer (`0503aaf`)
- Steward same-entity UX, cluster map (`c774616`)
