# Current state

**Last updated:** 2026-06-27 (memory palace refresh — `b2b81ea` pushed)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/dsi-async-topology` |
| **HEAD** | `b2b81ea` — DSI staged_metadata deadlock fix + loaded callout + dev-worker preflight (**pushed**, synced with `origin`) |
| **PR** | None open — branch ready for PR after large-volume apply soak |
| **Alembic (code)** | `20260623_0050` |
| **Alembic (DB)** | **`20260623_0050`** on local `cip` |

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

### Job #96 — APPLIED to `loaded` (facts in DSI DB)
- `fact_sales_sellout`=35,582 · `fact_inventory_distributor`=47,411 · `fact_returns`=3,175 (aggregated by `source_key` — correct).
- Achieved via surgical out-of-band finalize after sync Finalize endpoint timed proxy (~303s); facts had already committed.

### DSI apply pipeline (prior commits on branch)
- **No re-validate on apply** (`e4c30bc`): skip Step 1 when job already `validated` with staging.
- **Finalize → async** (`page.tsx`): Finalize button POSTs async `dsi-apply` (worker + poll), not sync in-request.
- **Gate-key revisit** (`468c239`): mapping-draft sync at `activeStep < 5`.
- **Customer alias resolution-key:** dealer-group token alignment; job #96 remediated → 0 blocking rows.

### Shipment import wizard (DSI-aligned — wired + unit-tested)
- 7-step wizard; `ImportJobLoadedSuccessCallout` on loaded; steward workspace parity.

---

## In progress / not proven live

- **Large-volume apply re-soak** — job #96-scale (178k) through **Apply** button not re-run since `b2b81ea`; mechanism proven on small job #199 only.
- **Pre-existing lint** — 7 `rules-of-hooks` errors in `dsi-mapping-steward-panel.tsx` block clean `pnpm lint` (not introduced by DSI apply work).
- **Billiard quirk** — solo worker spawns one child under system Python (single logical consumer; interpreter mismatch latent).
- Warren **actively working through** ACZA shipment upload (BOM tab deferred per BACKLOG-046).
- Shipment wizard browser soak, Rectron mapping, Import Centre URL reset — **not re-verified** this session.

---

## Next (recommended)

1. **Re-soak** large DSI apply (178k) through Apply button — confirm no proxy timeout + deadlock-free derive at volume.
2. **Open PR** on `feat/dsi-async-topology` when soak passes (or waive soak for merge with follow-up).
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
