# Current state

**Last updated:** 2026-06-27 (DSI apply proven fresh on job #199; staged_metadata deadlock fixed; DSI loaded callout; dev-worker duplicate preflight)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/dsi-async-topology` |
| **HEAD (snapshot)** | `468c239` — gate-key revisit fix committed + pushed |
| **PR** | None open — open when soak complete |
| **Alembic (code)** | `20260623_0050` |
| **Alembic (DB)** | **`20260623_0050`** on local `cip` (migration run 2026-06-24) |

---

## Database and environment

| Field | Value |
|-------|--------|
| **Active DB** | Local Postgres `cip` @ `127.0.0.1:5432` (topology B) |
| **Bitemporal flags** | `CIP_SHIPMENT_BITEMPORAL_DUAL_WRITE` / `_READ` — **off** by default |

---

## Dev topology

Local desktop (no Docker): `pnpm dev:api` :8001, `pnpm dev:web` :3000, worker or `CIP_DEV_CELERY_DISPATCH=in_process_thread`.

---

## What is working

### DSI apply proven fresh end-to-end on job #199 (2026-06-27)
- **Final state:** `import_job 199 = (status=completed, stage=loaded, import_mode=apply)` on `cip`.
- **Facts upserted (source_import_job_id=199):** `fact_sales_sellout`=2 (Sep 15: 4u/39,996; Sep 16: 2u/6,666) · `fact_inventory_distributor`=2 (Sep 15: 40 SOH; Sep 16: 36 SOH). Small clean E2E sample, not job #96 volume.
- **Post-apply derivations all succeeded in the worker:** `dsi_soh_reconciliation` (1 product, 42 allocation rows) · `dsi_velocity_compute` (3,369 rows) · `dsi_forecasting` (0 rows). Confirms the full apply → facts → derive chain.
- **UI loaded state:** the DSI Apply step (`activeStep===7`) now renders `ImportJobLoadedSuccessCallout` when the job is `loaded` (parity with shipment), instead of always showing the apply form. Verified in-browser for job #199.

### staged_metadata deadlock FIXED (was the "latent bug" below) — single-writer (2026-06-27)
- **Root cause:** post-apply derivation dispatch used a dual-writer pattern — `set_task_slot_on_job` on the caller's session (uncommitted row lock on `import_job`) **plus** `set_task_slot_by_job_id` in `enqueue_*` (own committed session). On one worker thread the two connections self-deadlocked on the same `import_job.staged_metadata` row → `idle in transaction` / `HeadersTimeoutError` on apply.
- **Fix:** `dispatch_dsi_soh_reconciliation_after_apply` / `dispatch_dsi_velocity_after_apply` no longer write/flush the slot on the caller session — `enqueue_*` is the **sole writer** (its own committed session); the completion path refreshes the job afterwards. Derivation dispatch in `complete_dsi_import_job_to_loaded` is wrapped in try/except so a derivation hiccup leaves the job `loaded` (facts applied), never reverts to `failed`. Test `test_dsi_soh_reconciliation.py` asserts `session.flush` is NOT called (single-writer contract).
- **Idempotent re-apply:** `run_dsi_apply_sync` now sets `status=completed`/`completed_at` when a re-applied job is already `STAGE_LOADED` (was stuck `status=running`).

### dev-worker duplicate-consumer preflight (2026-06-27)
- `scripts/dev-worker.js` now scans for existing `app.worker.celery_app` processes before spawning and stops them (Windows `taskkill /T`, Unix `SIGTERM`) so two workers can't double-consume the same Redis queues. Mirrors `dev-api.js` killing a stale process on its port. Skip with `CIP_SKIP_WORKER_PREFLIGHT=1`. Verified fresh start logs `mingle: all alone` (single consumer).
- **Known follow-up (not a duplicate):** billiard spawns one worker child under the **base/system** Python (`sys._base_executable`) not the venv — single logical consumer, but interpreter mismatch is a latent quirk to revisit.

### Job #96 APPLIED to `loaded` — facts in DSI DB (2026-06-27)
- **Final state:** `import_job 96 = (status=completed, stage=loaded, import_mode=apply)` on `cip`.
- **Facts upserted (source_import_job_id=96):** `fact_sales_sellout`=35,582 · `fact_inventory_distributor` (SOH)=47,411 · `fact_returns`=3,175. Counts < staging-line counts because facts aggregate by `source_key` (distributor+customer+product+period) — correct, not loss.
- **What actually happened:** the sync `dsi-apply-complete` (Finalize) endpoint upserted facts (committed) but the Next.js proxy `UND_ERR_HEADERS_TIMEOUT` fired at ~303s and the dev-server `--reload` killed the in-request thread before it flipped `stage→loaded`. Recovery: a one-off **surgical finalize** verified 0 human-fixable blocked rows + facts complete, flipped `stage=loaded`, dispatched derivations. SOH reconciliation + velocity then ran inline as fast no-ops (nothing to reconcile for a single snapshot).
- **Latent bug — now FIXED:** the derivation dispatch wrapper deadlock on `import_job.staged_metadata` is resolved by the single-writer change above.

### Finalize-to-loaded no longer times out the proxy (2026-06-27)
- **Root cause:** `POST /mappings/import-jobs/{id}/dsi-apply-complete` runs `complete_dsi_import_job_to_loaded` **synchronously in-request** (`asyncio.to_thread`); the 178k re-resolve + fact upsert exceeds the proxy's ~300s headers timeout → spurious 500 even though facts committed.
- **Fix (`apps/web/.../admin/imports/page.tsx`):** the "Finalize to loaded" button (`dsiApplyComplete`) now POSTs the **async** `dsi-apply` endpoint (worker + poll), identical to the "Apply" button, and drives `dsiApplyAsync`. Both apply buttons are disabled while `dsiApplyAsync` and show an in-progress callout. No synchronous long-running write left in the request path (import-parity rule).

### DSI apply no longer re-validates the whole file (2026-06-27, commit `e4c30bc`)
- **Root cause:** `run_dsi_apply_sync` ran TWO full passes — Step 1 `process_import_job_sync`
  (apply mode) re-parsed the file + re-resolved all 178k rows (wiping & rebuilding staging),
  then Step 2 `complete_dsi_import_job_to_loaded` re-resolved every staging line again + upserted
  facts. Step 1's full re-pipeline was the "why does apply revalidate again" problem AND it is
  destructive: if interrupted it leaves partial staging + `stage=failed`.
- **Fix:** Step 1 is skipped when the job is already `validated` with staging present
  (`already_validated`). Step 2 alone re-resolves staging against current master data and upserts
  facts. Step 1 retained only as fallback for an apply on a never-validated job.
- **Dispatch is `broker`** (apps/api/.env) → DSI apply runs in the **Celery worker process**;
  the worker must be **restarted** to load this fix (uvicorn hot-reload does not cover the worker).

### DSI import wizard gate-key revisit fix (2026-06-27, commit `468c239`)
- mapping-draft sync effect changed from `activeStep !== 5` → `activeStep < 5`. On revisit
  (deep-link to validated job at step 6), `dsiMapDraft` was never synced → `dsiMappingDraftDirty`
  stuck true → "Continue to apply" never showed. Fixed.

### DSI customer alias resolution-key fix (2026-06-27)
- Root cause: DSI staging resolves customers on Dealer Name Group token; aliases were keyed on
  customer-name column → phantom-resolved loop ("40 rows" forever unresolved in staging).
- Fix: `dsi_customer_alias_normalized_token(cand)` = `normalized_key` (dealer-group primary).
  All alias write paths routed through it. Job #96 remediated + revalidated → 0 blocking rows.
- Safety net: regenerated customer candidates re-open as `needs_review` (not phantom-resolved).

### Shipment import wizard (DSI-aligned — wired + unit-tested)
- **7 steps:** upload → column mapping → validate & resolve → apply.
- **Apply step:** `ImportJobLoadedSuccessCallout` when job stage `loaded`.
- **`shipmentWizardActiveStepFromServer`** — revisit jobs land on correct step.
- **Validate progress** — re-validate on `validated` jobs shows progress.
- **Steward grid** — `filterShipmentStewardCandidates` / `ShipmentImportJobResolutionSection` DSI parity (tabs, plan toolbar, bulk steward, server re-validate).

### Plan C / D / BACKLOG-007 (prior)
- Resolution plan API, paginated candidates, bitemporal D1–D3 (schema + dual-write wired; flags off), post-validate re-map + orphan purge.

### Docs / backlog (2026-06-24)
- **BACKLOG-046** — ACZA BOM Not Ready sheet handling (operator workaround: upload Shipped + Unship only).
- **BACKLOG-047** — stale column-mapping UI after Back + re-upload.
- **BACKLOG-048** — Celery + background-task parity audit.
- **BACKLOG-045** — steward UI parity audit (side drawer + workspace layout).

---

## In progress / not proven live

- **Job #96 is DONE** — `stage=loaded`, facts in DSI DB (see "What is working").
- **DSI apply de-timeout + deadlock fix PROVEN on fresh job #199** (worker path, full derive chain). Job #96-scale (178k) apply through the **Apply** button still not re-soaked since these fixes, but the mechanism is the same and is now deadlock-free.
- Apply fast-path (skip Step 1, `e4c30bc`) proven on the small job #199; large-volume re-soak still pending.
- Warren **actively working through** ACZA shipment upload / steward workflow (20260623 file; BOM tab deferred per BACKLOG-046).
- Browser soak on shipment wizard end-to-end not yet confirmed this session.
- Rectron / distributor-vs-customer mapping and 0.85 auto-apply threshold — reported in lost session; **not re-verified** after `a04e4d5`.
- Import Centre home URL reset on navigate — reported; fix in `a04e4d5` **not re-verified** live.
- Plan D D4–D5 deferred; bitemporal read path not exercised with flags on.

---

## Next (recommended)

1. **Re-soak** the apply path on a large (job #96-scale, 178k) DSI job through the **Apply** button to confirm no proxy 500 and deadlock-free derive at volume.
2. Resolve pre-existing `rules-of-hooks` lint errors in `dsi-mapping-steward-panel.tsx` (7 errors, not from this work — blocks a clean `pnpm lint`).
3. Revisit the billiard base-Python worker-child quirk (single consumer, wrong interpreter).
4. Finish ACZA upload workflow (trim workbook to **Shipped + Unship** until BACKLOG-046).
5. Open PR on `feat/dsi-async-topology` when soak passes.

---

## Blockers requiring Warren

- Business sign-off: should **BOM Not Ready** ever enter shipment facts? (BACKLOG-046)
- Main promotion — explicit instruction only

---

## Key references

| Topic | Doc |
|-------|-----|
| Import contract (shipment) | `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` |
| Operator | `docs/SHIPMENT_EVIDENCE_OPERATOR.md` |
| Plan D | `docs/SHIPMENT_BITEMPORAL_PLAN_D.md` |
| Backlog 046–048 | `docs/BACKLOG.md` |
