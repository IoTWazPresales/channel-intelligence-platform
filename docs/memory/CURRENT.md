# Current state

**Last updated:** 2026-06-27 (DSI gate-key revisit fix; job #96 unblocked end-to-end)
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

- **Job #96 is currently BROKEN** — `stage=failed status=interrupted import_mode=apply`, staging
  partial (~144k of 178k). The old apply re-pipeline wiped validated staging and was interrupted
  mid-rebuild. **Recovery:** (1) restart Celery worker (load apply fix); (2) re-validate job #96
  to rebuild full staging → `validated`; (3) Continue to apply (now skips Step 1, just upserts
  facts + loads SOH).
- Apply fast-path (skip Step 1) committed but **not yet proven end-to-end** — needs worker restart
  + a real validated→apply run.
- Warren **actively working through** ACZA shipment upload / steward workflow (20260623 file; BOM tab deferred per BACKLOG-046).
- Browser soak on shipment wizard end-to-end not yet confirmed this session.
- Rectron / distributor-vs-customer mapping and 0.85 auto-apply threshold — reported in lost session; **not re-verified** after `a04e4d5`.
- Import Centre home URL reset on navigate — reported; fix in `a04e4d5` **not re-verified** live.
- Plan D D4–D5 deferred; bitemporal read path not exercised with flags on.

---

## Next (recommended)

1. **Confirm** "Continue to apply" appears on job #96 (hard-refresh page if needed).
2. **Apply** job #96 → SOH load → verify fact tables populated.
3. Finish ACZA upload workflow (trim workbook to **Shipped + Unship** until BACKLOG-046).
4. Open PR on `feat/dsi-async-topology` when soak passes.

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
