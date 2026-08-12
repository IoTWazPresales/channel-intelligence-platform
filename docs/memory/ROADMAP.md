# Platform roadmap

**Purpose:** Single phased schedule for strategic audit, modular audit, DSI topology,
and backlog items. **`docs/BACKLOG.md`** holds full entry detail + TRIGGERs; this file
holds **priority order** and **done vs open** (verified against `main` @ PR #5 merge).

**Last verified:** 2026-07-20 · **Active branch:** `feat/cpor-listing-status-audit`  
**How to use:** Pick the lowest open phase item whose TRIGGER is met (or waived by Warren).
Update status here + `CURRENT.md` when items complete; add deferrals to `BACKLOG.md`.

**2026-07-20 prune:** Removed shipped / ignore-Supabase / ignore-deploy / fixed-069 entries from
`docs/BACKLOG.md` (see prune note there + `.tmp/BACKLOG_DISPOSITION_OVERVIEW_2026-07-20.md`).
Opus CONSULT READY. ROADMAP rows below refreshed for Done items that were stale as Open.

---

## Status legend

| Status | Meaning |
|--------|---------|
| **Done** | Shipped on `main`; verified in repo this session |
| **Partial** | Core path shipped; follow-up row still open |
| **Open** | Not started; TRIGGER met or active-branch work |
| **Parked** | TRIGGER not met or explicit deferral |
| **Ops** | Warren / infra approval required |

---

## Phase A — DSI async topology (active: `feat/dsi-async-topology`)

Job #96 class: solo Windows worker + remote Supabase → false **queue timeout** on plan
compute (task often succeeds after UI gives up). Structural fixes, not poll-only patches.

| ID | Item | Status | Evidence / notes |
|----|------|--------|------------------|
| **BACKLOG-038** | Env flag: disable Celery beat + `reap_stale_running_jobs` on Windows solo dev | **Done** | `celery_queues.dev_beat_disabled()`; `dev-worker.js` skips beat by default on Windows solo; reaper task no-op when disabled. |
| **BACKLOG-039** | Celery **queue split**: interactive steward vs batch validate/apply | **Done** | `celery_queues.py` routes; worker `-Q interactive,batch,celery` in dev-worker + docker-compose. |
| **BACKLOG-040** | Defer historical **post-validate auto-apply** until steward idle | **Done** | `dsi_post_validate_auto_apply.py`; Windows default defer; flush task + steward completion hooks. |
| **BACKLOG-041** | Raise compute **poll queue grace** + queue-aware UI messaging | **Done** | Scaled compute grace in `stewardAsyncPoll.ts`; clearer queue-timeout copy. |
| **BACKLOG-042** | Dedupe duplicate resolution-plan error banners | **Done** | Error only in `DsiResolutionPlanToolbar.tsx`. |
| **BACKLOG-043** | Triage **CI `test` failure** on `main` post PR #5 | **Done** | Fixed `test_product_usage_delete_semantics.py` import after `_SPECS` refactor. Removed from BACKLOG 2026-07-21 re-audit. |

**Done (related, do not re-implement):**

| Item | Status | Evidence |
|------|--------|----------|
| Compute task dedupe (reuse active task) | **Done** | `reusable_dsi_bulk_task_id` + `compute-async` in `mappings.py` |
| Apply poll queue grace (row-scaled) | **Done** | `stewardAsyncPollApplyOptions` — min 450 attempts |
| `waitForDsiStewardBulkIdle` before apply POST | **Done** | `useDsiResolutionPlan.ts` |
| Post-validate historical auto-apply (exists) | **Done** | `dsi_validate_post_sync.py` — **defer timing** is BACKLOG-040, not removal |

---

## Phase B — Dev / deploy strategy

| ID | Item | Status | Evidence / notes |
|----|------|--------|------------------|
| — | Daily dev on **local `cip`**; Supabase for **scheduled soaks** | **Partial** | Warren on **local `cip`** since 2026-06-22 (Supabase clone + `.env` repoint). Supabase remains rollback backup; periodic remote soaks still optional. |
| **BACKLOG-002** | Async connection pooling (`:5432` session pooler + modest pool) | **Removed** | Ignored — Supabase stopped; NullPool/`6543` locked. |
| **BACKLOG-003** | EU **co-location** API + worker with Supabase | **Removed** | Ignored — not redeploying. |
| **BACKLOG-028** | Sync Celery engine off pooler replica routing | **Done** | `sync_url.py`, `resolve_sync_engine_url()`; `commit_session_with_transient_retry`. |
| **BACKLOG-030** | DSI validate batched staging + chunked commits | **Done** | 2k chunks, 50k commit boundary; job #43 soak accepted. |
| — | Sync `idle_in_transaction_session_timeout` backstop | **Done** | `session_sync.py` `build_sync_connect_args()` |
| **BACKLOG-032** | Post bulk-delete VACUUM runbook | **Parked** | TRIGGER: large delete + disk pressure + maintenance window. |
| — | Supabase disk / read-only | **Done** (ops) | MCP 2026-06-21: **740 MB**, `read_only=off`, `ACTIVE_HEALTHY` |

---

## Phase C — Import modularization & parity

| ID | Item | Status | Evidence / notes |
|----|------|--------|------------------|
| **BACKLOG-004** | Import Flow **Phase 3**: capability-driven wizard; split `admin/imports/page.tsx` | **Parked** | Page still **~4,015 lines**; no `ImportFlowCapability` in `packages/types/`. TRIGGER: PM core-loop re-run + approval. |
| **BACKLOG-001** | Shipment steward → shared `ImportStewardCandidateWorkspace` | **Done** | Mounted in `ShipmentImportJobResolutionSection` (2026-07). Full intelligence parity remains **044/045**. |
| **BACKLOG-044** | Shipment steward UX + resolution intelligence parity (plan/ready/bulk vs DSI) | **Done** | Workspace + plan + drawer duplicate Same/Different (045). |
| **BACKLOG-005** | DSI → `CanonicalColumnMappingPanel` | **Done** | |
| **BACKLOG-006** | Slim shipment `mapping-candidates` API (paginate / omit `line_ids`) | **Parked** | Paginated list; `line_ids` still in context payload. |
| **BACKLOG-007** | Shipment post-validation re-map + `source_key` stability | **Done** | UI + orphan purge shipped; soak is ops watch only. |
| **BACKLOG-022** | Unified `import_dispatch.enqueue_import_worker_task` | **Done** | `import_dispatch.py` exists; imports + shipment delegate. |
| **BACKLOG-025** | Generic pipeline apply → async | **Partial** | `/process` async (2026-06-05). **Remaining:** frontend progress for CST/masters (`BACKLOG-029` part b). |
| **BACKLOG-026** | PM: consolidate dual apply pipelines | **Parked** | `product_master_workflow.py` vs `pipeline.py::_process_product_master`. |
| **BACKLOG-027** | PM + historical → `CanonicalColumnMappingPanel` | **Parked** | Pairs with BACKLOG-026. |
| **BACKLOG-029** | CST surface + upload zone | **Partial** | (a) dsiApplyAsync poll **Done**; (c) `ImportFileUploadZone` **Done**; (b) CST web surface **Parked**. |
| **BACKLOG-020** | PM full job revisit in wizard | **Parked** | `page.tsx` still says full PM revisit not supported. |
| — | Import Flow contract Phase 1 (design) | **Done** | `IMPORT_FLOW_CAPABILITY_CONTRACT.md` |
| — | Import Flow Phase 2 (tracking registry) | **Partial** | Slot registry + cancel revoke **Done** (BACKLOG-015); not all importers on unified helper. |
| — | Shipment steward async bulk-map | **Done** | `shipment_bulk_steward_enqueue.py` + 202 endpoint |

---

## Phase D — DSI resolution & data substrate

| ID | Item | Status | Evidence / notes |
|----|------|--------|------------------|
| **BACKLOG-037** | Validate/refresh post-resolution orchestrator unification | **Parked** | TRIGGER: Tier B+C validate soak or refresh bug. |
| **BACKLOG-036** | Weekly SKU-strict product resolution | **Done** | `dsi_weekly_product_resolution.py` |
| **BACKLOG-035** | Migration 0048 alias partial-uniques | **Done** | Applied Supabase 2026-06-16; code head `20260609_0049` adds `task_run`. |
| **BACKLOG-016** | DSI steward finalize (deferred plan items) | **Parked** | Per-row approval in `DSI_STEWARD_FINALIZE_PLAN.md`. |
| **BACKLOG-017** | Embedding duplicate detection | **Parked** | Still `difflib`; doc says not implemented. |
| **BACKLOG-018** | DSI geo token indexes | **Parked** | TRIGGER: EXPLAIN still slow. |
| **BACKLOG-008** | DSI region hints from shipment evidence | **Parked** | TRIGGER: region Phases A–B stable. |
| **BACKLOG-033** | Bitemporal shipment evidence (observations + current-state view) | **Done** | Core Plan D shipped; follow-ons **057-D4** / **058-D5** remain open. |
| **BACKLOG-034** | PM launch/retire date integrity | **Parked** | TRIGGER: commercial outputs depend on lifecycle windows. |
| — | `task_run` ledger at dispatch | **Done** | `task_run.py`, migration `20260609_0049`; read path not fully unified with activity feed. |
| — | `db_transient_retry` on all sync writers | **Partial** | Used in DSI bulk paths + validate; **not** all commit paths — verify before assuming coverage. |

---

## Phase E — Ops visibility, PM/PIM, commercial planner

| ID | Item | Status | Evidence / notes |
|----|------|--------|------------------|
| **BACKLOG-031** | Admin **data health** dashboard | **Parked** | No `/admin/data-health` route in API/web grep. TRIGGER: operator visibility need or pre-soak. |
| **BACKLOG-010** | Drop legacy PAV ~2M rows | **Done (local cip)** | Count was 0; truncate script shipped; remote/other env: re-run script after backup. |
| **BACKLOG-011** | `catalog_product` bulk upsert on PM commit | **Parked** | TRIGGER: profiling shows catalog flush dominant. |
| **BACKLOG-009** | PIM typed attributes from `specs_json` | **Parked** | Design brief only. |
| **BACKLOG-021** | Commercial Planner RBAC + durable recommendations | **Parked** | `COMMERCIAL_PLANNER_GAP_ANALYSIS.md`. |
| **BACKLOG-013** | CST own import surface (D1) | **Parked** | Backend exists; web surface = BACKLOG-029(b). |
| **BACKLOG-014** | Customer classification import | **Parked** | Template deferred in `template_definitions.py`. |
| **BACKLOG-019** | Historical lineup deferred bundle | **Parked** | Pick one slice when module prioritized. |

---

## Completed — PR #5 / close-out (do not re-audit)

Verified on `main` after merge `0540435` (2026-06-21).

| Area | Status | Notes |
|------|--------|-------|
| DSI steward bulk orchestrators (map/ignore/provisional) | **Done** | Set-based sync modules + async enqueue |
| DSI resolution plan compute + apply async | **Done** | Poll helpers + Celery tasks |
| Shipment apply async + bulk steward enqueue | **Done** | `shipment_apply_sync`, `shipment_bulk_steward_enqueue` |
| Shipment steward perf Phase 1–2 (debounce, batch SQL) | **Done** | Merged in PR #5 branch history |
| DSI validate via Celery `imports.process_job` | **Done** | Not synchronous in request path |
| Import pipeline dispatch claim (duplicate enqueue guard) | **Done** | `import_pipeline_dispatch_claim.py` |
| Memory palace (`CURRENT.md`, `MEMORY_PALACE.md`, topology docs) | **Done** | This roadmap completes the index |
| Branch/PR lifecycle + context handover rules | **Done** | `.cursor/rules/*.mdc` |
| **BACKLOG-012** AG Grid test mock | **Done** | |
| **BACKLOG-015** Cancel revokes all slot tasks | **Done** | |
| **BACKLOG-023** DSI progress terminal label | **Done** | |
| **BACKLOG-024** AI resolver on distributor_master + historical_lineup | **Done** | |
| **BACKLOG-072** Catalogue-gap confirm-resolve (scan/preview/apply) | **Done** | `product_master_gap_resolve.py` + `/product-master-gaps/*` + Confirm resolve UI; removed from BACKLOG 2026-07-21. DSI *facts* stay FLAG-only (`source_key` includes product_id) by design. |

---

## Suggested execution order (next)

1. **CPOR historical** VERIFY steward parity → H3 (active branch).
2. **BACKLOG-044/045** shipment steward intelligence parity when TRIGGER fires.
3. **BACKLOG-047** / **060** import UX friction when prioritized.
4. **BACKLOG-004** only after explicit PM core-loop re-run + approval.

---

## Maintenance

- New deferral → `BACKLOG.md` entry + one row in the phase table here.
- Item completes → set **Done** here, update `CURRENT.md`, changelog line in `CONTEXT.md`.
- Do not duplicate long TRIGGER text — link `BACKLOG-0xx`.

---

## Related docs

| Doc | Role |
|-----|------|
| `docs/memory/CURRENT.md` | Now: branch, env, blockers |
| `docs/BACKLOG.md` | Full backlog entries |
| `docs/DEV_TOPOLOGY.md` | Topology matrix |
| `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` | Importer capability matrix |
| `docs/memory/derived/platform_async_and_background_truth.md` | Celery task inventory |
