# Channel Intelligence Platform — Context

> **Memory palace router.** Authoritative current state:
> **[`docs/memory/CURRENT.md`](docs/memory/CURRENT.md)**
>
> Read order: **[`docs/memory/MEMORY_PALACE.md`](docs/memory/MEMORY_PALACE.md)**

---

## How agents update state

1. Edit **`docs/memory/CURRENT.md`** after significant work (keep it short).
2. Append **one changelog line** below (newest first).
3. Do **not** add `## CURRENT STATE — supersedes every block below` sections here anymore.

For deferrals use **`docs/BACKLOG.md`**. For conflicts between docs, **ask Warren** before proceeding (see MEMORY_PALACE.md).

---

## Changelog

| Date | Summary |
|------|---------|
| 2026-06-28 | **Session B Units 5/7/8 — unified lineup importer + iterations + per-customer export (`693efb9`, `4d195e0`):** First-class `unified_lineup` importer (own template + `unified_lineup_system` source, seed migration `20260628_0056` applied to `cip`). Generalized the lineup seed over (template_slug, source_code) and threaded it through parser/dispatch/worker/Celery task so unified jobs are audited `template_slug='unified_lineup'` (rejected the cheap "reuse current_lineup" route per Warren's directive). New `dispatch_unified_lineup_import` fans out one `CommercialLineupCase` + one always-async parse job per uploaded file (per-file activity-feed progress, per-file failure isolation), reusing the canonical parse worker (pricing chain + period/product-line inference). Endpoint `POST /commercial-planner/lineup/unified-import` (multipart, N files + shared period/country/currency/plan). Unit 7: `iteration_number` advances on `pending_review→validated` (customer bounce-back = new round; first send = round 1); `customer_feedback`/`internal_notes` editable through the review loop while pricing/qty edits stay draft-only; case payload exposes iteration/product_line/inferred_period_start. Unit 8: `GET /commercial-planner/lineup-cases/{id}/export?customer_id=` streams a customer's slice with the full persisted pricing chain (recomputes nothing; DAP=calculated cost-ccy, not PM bottom). Real `cip` e2e proved: unified job tagging + DAP 39.6622 + period inference + missing_pm_bottom (Unit 5), iteration loop 1→1→2 + annotation 409-gate (Unit 7), XLSX slice output (Unit 8). 113 unit/API tests pass. Alembic head `20260628_0056`. **Remaining: Unit 6 (frontend) — Import-Centre multi-file uploader + make CurrentLineupSection upload read-only.** |
| 2026-06-28 | **Large-volume apply proven live (job #96):** Warren confirmed 178k RAW workbook applied and visible in channel operations. Updated `CURRENT.md` — removed stale "re-soak not proven" item; job #96 marked proven at volume. RAW vs DB gap audit in progress. |
| 2026-06-27 | **DSI apply proven fresh (job #199) + staged_metadata deadlock FIXED + DSI loaded callout + dev-worker preflight (`b2b81ea`):** Resolved BACKLOG-050 — the post-apply derivation dispatch deadlock on `import_job.staged_metadata` (dual-writer: caller-session `set_task_slot_on_job` holding an uncommitted row lock vs `enqueue_*`'s own committed session). Made `enqueue_*` the **sole writer** (removed caller-side slot write/flush in `dsi_soh_reconciliation_enqueue.py` + `dsi_velocity_enqueue.py`); wrapped derivation dispatch in `complete_dsi_import_job_to_loaded` in try/except so a loaded job never reverts to failed; `run_dsi_apply_sync` now marks an already-`loaded` re-apply `completed` (was stuck `running`). Added DSI `ImportJobLoadedSuccessCallout` in the Apply step (`page.tsx`) so a loaded DSI job shows a success state, not the apply form. Added `scripts/dev-worker.js` duplicate-consumer preflight (kills stray `app.worker.celery_app` processes before spawn; `CIP_SKIP_WORKER_PREFLIGHT=1` to skip). Proven E2E on fresh job #199: facts in `fact_sales_sellout`(2)+`fact_inventory_distributor`(2), full SOH+velocity(3,369)+forecast derive chain, UI loaded callout, `mingle: all alone`. Tests: `test_dsi_soh_reconciliation.py` 4/4, web routing+callout 13/13. Pre-existing `dsi-mapping-steward-panel.tsx` rules-of-hooks lint errors untouched (not this work). |
| 2026-06-27 | **Job #96 APPLIED → `loaded`; Finalize button de-timeouted (uncommitted):** Root cause of the `dsi-apply-complete` 500 = `UND_ERR_HEADERS_TIMEOUT` — the endpoint runs `complete_dsi_import_job_to_loaded` **synchronously in-request** (`asyncio.to_thread`); 178k re-resolve + upsert exceeds the proxy's ~300s headers timeout AND the dev `--reload` killed the thread before it flipped `stage→loaded`. Facts had already committed. Verified facts present (`fact_sales_sellout`=35,582, `fact_inventory_distributor`/SOH=47,411, `fact_returns`=3,175) then did a **surgical out-of-band finalize** (0 human-fixable blocked → `stage=loaded` → derivations). SOH reconciliation + velocity ran inline as fast no-ops. Cleaned phantom task_run entries. **Permanent fix:** "Finalize to loaded" button now POSTs the async `dsi-apply` (worker+poll) like "Apply" — no sync long-running write in the request path. Latent backlog: dispatch wrapper's concurrent helper sessions deadlock on `import_job.staged_metadata`. |
| 2026-06-27 | **DSI apply no longer re-validates whole file (`e4c30bc`):** `run_dsi_apply_sync` ran two full passes — Step 1 re-parsed + re-resolved all 178k rows (wiping/rebuilding staging), Step 2 re-resolved staging + upserted facts. Step 1 was the "apply revalidates again" problem and is destructive if interrupted (job #96 left `stage=failed`/partial staging). Fix: skip Step 1 when job already `validated` with staging; Step 2 self-resolves + upserts. Dispatch=`broker` → Celery worker must restart to load fix. Job #96 needs re-validate → apply to recover. |
| 2026-06-27 | **DSI gate-key revisit fix:** mapping-draft sync effect only ran at `activeStep===5`; on revisit (deep-link to validated job, step 6) `dsiMapDraft` stayed `{}` while server had real field_mapping → `dsiMappingDraftDirty=true` permanently → gate-key `useEffect` nulled itself → "Continue to apply" never showed despite 0-blocking DB. Fix: `activeStep < 5` so draft syncs on steps 5/6/7. Commit `468c239`. |
| 2026-06-27 | **DSI customer alias resolution-key fix (root cause):** steward map/provisional/open-channel wrote approved aliases keyed on the customer-name column while staging resolves on the Dealer Name Group → permanent `customer_unresolved` + phantom `resolved` candidates hidden from Customers tab. Routed all alias writes through `dsi_customer_alias_normalized_token` (= candidate resolution identity); preserve logic no longer carries stale `resolved` onto regenerated customer candidates. Job #96 remediated + full revalidate → **0 blocking rows**. Pre-existing dev-DB-pollution test failures unrelated. Uncommitted on `feat/dsi-async-topology`. |
| 2026-06-24 | **Context refresh:** cloud→local chat loss recovered via `git pull`; HEAD `1e51c76` pushed (BACKLOG-046–048); alembic `20260623_0050` applied on local `cip`; Warren mid ACZA workflow — soak + steward mapping issues not re-verified this session. |
| 2026-06-24 | **Shipment apply loaded UX:** shared `ImportJobLoadedSuccessCallout` on imports wizard step 6 when job stage `loaded`; BACKLOG-045 steward UI parity audit parked. |
| 2026-06-24 | **Shipment wizard + steward DSI parity (Phases 1–3):** 7-step wizard; validate progress fix; entity filter fix; `ShipmentImportJobResolutionSection` rework (tabs in workspace, plan toolbar, bulk steward, server re-validate); contract D4 updated. |
| 2026-06-24 | **Local merge:** fast-forward `feat/dsi-async-topology` to `0e61744` from `cursor/cloud-agent-1782231728131-em82n` (Plan C + D + BACKLOG-007). Local `cip` still at alembic `20260609_0049`. |
| 2026-06-24 | **Shipment steward UX + BACKLOG-007:** inline row actions + drawer (DSI parity); auto resolution plan compute on scope change; post-validate re-map UI on imports page; orphan `source_key` purge on re-validate (`test_shipment_evidence_orphan_purge.py`). |
| 2026-06-24 | **Plan D bitemporal shipment evidence (D1–D3):** migration `20260623_0050` (`shipment_evidence_observation` + `shipment_evidence_current` view + backfill); dual-write on validate (`CIP_SHIPMENT_BITEMPORAL_DUAL_WRITE`); corroboration read switch (`CIP_SHIPMENT_BITEMPORAL_READ`). Flags default off. D4–D5 deferred. |
| 2026-06-23 | **Plan C shipment steward parity:** workspace section, resolution plan API, paginated candidates + tab-counts, alias-scope port, operator docs; Plan D bitemporal design doc (no migration). Legacy panel retained in dialog. |
| 2026-06-23 | DSI customer alias-scope module (`dsi_customer_alias_scope.py`) wired to bulk map + provisional + async steward; steward tab-count/cache fixes; read-only customer duplicate groups API + admin page; BACKLOG-044 shipment parity parked. |
| 2026-06-22 | DSI customer sim-name plan tier (`575276f`); provisional create-path similarity reuse (`38b2c9e`); ambiguous product plan crash fix (`9f3206f`); HEAD `9f3206f`, **2 commits unpushed**. |
| 2026-06-22 | Warren local dev on **topology B**: Supabase `public` cloned read-only into local `cip` (pg_dump/pg_restore); `.env` repointed to `127.0.0.1`; anchors verified (`dim_product` 18158, alembic `20260609_0049`); rollback dumps in repo root (untracked). |
| 2026-06-21 | Phase A DSI async topology (BACKLOG-038–043): beat off Windows solo, interactive/batch queues, defer post-validate auto-apply, scaled compute poll grace, dedupe error banners, CI test fix. |
| 2026-06-21 | Added `docs/memory/ROADMAP.md` (phased schedule + done verification); BACKLOG-038–043 for Phase A DSI topology; BACKLOG-001 trigger updated post PR #5. |
| 2026-06-21 | PR **#5** merged to `main` (`0540435`); new branch `feat/dsi-async-topology` for DSI queue/scheduling work; branch/PR lifecycle + context handover rules added. |
| 2026-06-21 | Project rules Memory Palace section aligned to `CURRENT.md` / `MEMORY_PALACE.md`. |
| 2026-06-21 | Memory palace consolidation: `CURRENT.md`, `MEMORY_PALACE.md`, `DEV_TOPOLOGY.md`; full prior CONTEXT → [`docs/memory/CONTEXT-archive-through-2026-06-21.md`](docs/memory/CONTEXT-archive-through-2026-06-21.md); async docs aligned. |

---

## Archive

All append-only history through **2026-06-21** (including duplicate CURRENT STATE blocks):

**[`docs/memory/CONTEXT-archive-through-2026-06-21.md`](docs/memory/CONTEXT-archive-through-2026-06-21.md)**

Use archive for forensic history only — not for current branch, Alembic head, or "what works now".
