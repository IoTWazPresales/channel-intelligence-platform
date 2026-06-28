# Current state

**Last updated:** 2026-06-28 (Session C Unit 2d shipped — Confirm-with-PO + commercial_lineup_case_po; migration NOT yet applied to cip)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/unit-6-unified-lineup-import-centre` (now also carries Session C; cut from `feat/dsi-async-topology` + BACKLOG-051 docs) |
| **HEAD** | Session C Unit 2d (confirm-with-PO) on top of `d208e1a` (Unit 6 frontend) / Session B Units 1-8 |
| **PR** | None open |
| **Alembic (code)** | `20260628_0057` (commercial_lineup_case_po) |
| **Alembic (DB)** | **`20260628_0056`** on local `cip` — **`0057` pending: Warren must run `alembic upgrade head`** before confirm-with-PO works at runtime |

---

## Database and environment

| Field | Value |
|-------|--------|
| **Active DB** | Local Postgres `cip` @ `127.0.0.1:5432` (topology B) |
| **Bitemporal flags** | `CIP_SHIPMENT_BITEMPORAL_DUAL_WRITE` / `_READ` — **off** by default |
| **Celery dispatch** | `broker` (apps/api/.env) — DSI apply runs in worker, not API process |

---

## Dev topology

Local desktop (no Docker): `pnpm dev:api` :8001 · `pnpm dev:web` :3000 · `pnpm dev:worker` (Redis :6379) or `CIP_DEV_CELERY_DISPATCH=in_process_thread`.

| Preflight | Script | Skip env |
|-----------|--------|----------|
| API port / stale uvicorn | `scripts/dev-api.js` | `CIP_SKIP_API_PORT_PREFLIGHT=1` |
| Redis TCP | `scripts/dev-worker.js` | `CIP_SKIP_REDIS_PREFLIGHT=1` |
| Duplicate Celery consumers | `scripts/dev-worker.js` | `CIP_SKIP_WORKER_PREFLIGHT=1` |

**Ops note:** On Windows, the **node wrappers** for API and worker can exit after ~30 min or host sleep/resume (exit code -1). Restart `pnpm dev:api` / `pnpm dev:worker`. Worker preflight auto-kills orphan `app.worker.celery_app` processes on restart (proven: killed PIDs 23376+5032 after wrapper death). Uvicorn `--reload` does **not** reload the Celery worker — restart worker after API-side apply fixes.

---

## What is working

### Session B — Unified lineup import path (Units 1-5, 7-8) — backend done, e2e-proven on `cip`
Goal: one unified, multi-file lineup importer that supersedes the embedded Commercial-Planner
upload and the admin `historical_lineup` workbook, with full pricing chain + negotiation tracking.

- **Unit 1 — backwards pricing calc** (`lineup_pricing.py`): SRP→DAP chain (SRP/(1+VAT) → dealer →
  net(rebate) → disti_cost → /(1+import_tax) → /ROE = DAP cost-ccy; profit = DAP − controlled_cost).
- **Unit 2 — model + migration `20260628_0055`**: case `product_line` / `inferred_period_start` /
  `iteration_number`; line `customer_feedback` / `internal_notes` / `pricing_chain_json` /
  `calc_dap_cost_currency` / `calc_profit_total`.
- **Unit 3 — pricing alias map + resolution** (`lineup_pricing_resolution.py`): file evidence over
  trade-term defaults (customer/distributor terms + `commercial_sku_assumption`); stores calc_* +
  `pricing_chain_json` (inputs/sources/outputs/flags); `missing_pm_bottom` flag when no PM bottom.
- **Unit 4 — period/product-line inference** (`lineup_period_inference.py`): `26Q1`/month-column →
  `inferred_period_start`; product line from majority column. User-supplied values win.
- **Unit 5 — first-class `unified_lineup` importer** (`693efb9`): own template + `unified_lineup_system`
  source (seed migration `20260628_0056`, applied to `cip`). Lineup seed generalized over
  (template_slug, source_code); threaded through parser/dispatch/worker/Celery task so jobs are
  audited `template_slug='unified_lineup'`. `unified_lineup_import.dispatch_unified_lineup_import`
  fans out **one CommercialLineupCase + one always-async parse job per file** (per-file activity-feed
  progress, per-file failure isolation). Endpoint `POST /commercial-planner/lineup/unified-import`
  (multipart, N files + shared period/country/currency/plan). **Real e2e on cip:** job tagged
  unified_lineup, DAP 39.6622, period 2026-01-01, `missing_pm_bottom`, chain persisted.
- **Unit 7 — negotiation iterations + annotations** (`4d195e0`): `iteration_number` advances on
  `pending_review→validated` (customer bounce-back = new round; first send = round 1).
  `customer_feedback`/`internal_notes` editable through review loop (draft/validated/pending_review);
  pricing/qty edits stay draft-only. Case payload exposes iteration/product_line/inferred_period_start.
- **Unit 8 — per-customer XLSX export** (`4d195e0`): `GET /commercial-planner/lineup-cases/{id}/export?customer_id=`
  streams one customer's slice with the full persisted pricing chain (recomputes nothing; DAP =
  calculated cost-ccy, **not** PM bottom). `lineup_customer_export.py`.
- **Tests:** 113 unit/API pass; Units 5/7/8 also proven by real `cip` e2e (scripts cleaned up).

### Unit 6 (frontend) — DONE (wired + unit-tested; not yet browser-soaked)
Import-Centre multi-file uploader for the unified lineup importer + embedded upload made read-only.
- **New `UnifiedLineupImportDialog`** (`apps/web/src/app/(app)/admin/imports/UnifiedLineupImportDialog.tsx`):
  multi-file dropzone + plan/period/country/currency fields → `POST /api/v1/commercial-planner/lineup/unified-import`
  via `apiPostFormData` (repeated `files` field + form fields). On 202 it registers each returned
  `task_id` with the nav-bell activity feed (kind `commercial_planner_lineup_parse`) so progress is
  visible per file, and renders a per-file dispatch outcome table. Plan dropdown reads
  `GET /commercial-planner/plans`; selecting a plan prefills country/currency.
- **Import-Centre page** (`admin/imports/page.tsx`): added explicit primary card
  (`unified-lineup-import-card`) opening the dialog; `ImportTemplate` type gained `hidden?`; the
  `visibleTemplates` filter now excludes `hidden` templates so `unified_lineup` stays out of the
  generic wizard (it has its own surface).
- **`CurrentLineupSection`** read-only: new `allowUpload` prop (default **false**). When read-only the
  "Upload current lineup" button is replaced by an "Import lineups in Import Centre" link (→
  `/admin/imports`), the per-case "Upload file to this case" retry is hidden, and the
  `UploadLineupDialog`/`RetryParseDialog` are not mounted. Legacy upload retained behind `allowUpload`.
- **Tests:** new `UnifiedLineupImportDialog.test.tsx` (3) proves multipart `files` wiring +
  task registration + disabled-until-valid-file; existing `CurrentLineupSection.test.tsx` (7) and
  `commercial-planner/page.test.tsx` (83) still green. Lint clean for touched files.
- **NOT verified:** browser soak of the dialog against a running API (per-file progress in the bell,
  cases landing under the plan's Current lineups).

### DSI apply — proven fresh E2E on job #199 (`b2b81ea`, 2026-06-27)
- `import_job 199` → `completed` / `loaded` / `apply`.
- Facts (`source_import_job_id=199`): `fact_sales_sellout`=2 · `fact_inventory_distributor`=2.
- Full derive chain in worker: SOH reconciliation · velocity (3,369 rows) · forecasting.
- UI: DSI Apply step shows `ImportJobLoadedSuccessCallout` when loaded (parity with shipment).

### staged_metadata deadlock — FIXED (BACKLOG-050 resolved, `b2b81ea`)
- **Root cause:** dual-writer on `import_job.staged_metadata` — caller-session `set_task_slot_on_job` (uncommitted row lock) + `enqueue_*` own committed session → self-deadlock on one worker thread.
- **Fix:** `enqueue_*` is sole writer; derivation dispatch wrapped in try/except (loaded job never reverts to `failed`); idempotent re-apply sets `completed` when already `loaded`. Test asserts `session.flush` not called on dispatch.

### dev-worker duplicate-consumer preflight (`b2b81ea`)
- Kills stray `app.worker.celery_app` before spawn; fresh start logs `mingle: all alone`.

### Job #96 — large-volume apply PROVEN LIVE (`loaded`, channel operations)
- Full **178k-row** RAW workbook applied; facts visible in channel operations (Warren confirmed 2026-06-28).
- `fact_sales_sellout`=35,582 · `fact_inventory_distributor`=47,411 · `fact_returns`=3,175 (unique `source_key` grain — multiple Excel rows collapse per key).
- Apply path: async worker + poll; `staged_metadata` deadlock fix (`b2b81ea`) holds at volume.

### DSI apply pipeline (prior commits on branch)
- **No re-validate on apply** (`e4c30bc`): skip Step 1 when job already `validated` with staging.
- **Finalize → async** (`page.tsx`): Finalize button POSTs async `dsi-apply` (worker + poll), not sync in-request.
- **Gate-key revisit** (`468c239`): mapping-draft sync at `activeStep < 5`.
- **Customer alias resolution-key:** dealer-group token alignment; job #96 remediated → 0 blocking rows.

### Shipment import wizard (DSI-aligned — wired + unit-tested)
- 7-step wizard; `ImportJobLoadedSuccessCallout` on loaded; steward workspace parity.

---

## In progress / not proven live
- **Pre-existing lint** — 7 `rules-of-hooks` errors in `dsi-mapping-steward-panel.tsx` block clean `pnpm lint` (not introduced by DSI apply work).
- **Billiard quirk** — solo worker spawns one child under system Python (single logical consumer; interpreter mismatch latent).
- Warren **actively working through** ACZA shipment upload (BOM tab deferred per BACKLOG-046).
- Shipment wizard browser soak, Rectron mapping, Import Centre URL reset — **not re-verified** this session.

---

## Next (recommended)

1. **Browser-soak Unit 6** — open `/admin/imports`, use the "Lineup (unified import)" card to upload
   2+ files against a running API; confirm per-file progress in the nav bell and cases appearing under
   the plan's Current lineups. (Wired + unit-tested; not yet soaked.)
2. **Open PR** for `feat/unit-6-unified-lineup-import-centre` → merges DSI large-volume work + full
   Session B unified importer (Units 1-8). Branch cut from `feat/dsi-async-topology`.
3. Fix `dsi-mapping-steward-panel.tsx` rules-of-hooks lint (unblocks `pnpm lint`).
4. Finish ACZA upload (trim to **Shipped + Unship** until BACKLOG-046).

---

## Blockers requiring Warren

- Business sign-off: should **BOM Not Ready** enter shipment facts? (BACKLOG-046)
- Main promotion — explicit instruction only

---

## Key references

| Topic | Doc |
|-------|-----|
| Memory index | `docs/memory/MEMORY_PALACE.md` |
| Import contract | `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` |
| Dev topology | `docs/DEV_TOPOLOGY.md` |
| Backlog 045–050 | `docs/BACKLOG.md` |
