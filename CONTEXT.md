# Channel Intelligence Platform — Current Context

## CURRENT STATE — Jun 11, 2026 (DSI validate hang fix — keepalives + single cache build) — supersedes every block below

- **Branch:** `fix/shipment-steward-performance` @ **`27d4058`** pushed (includes `0af613a` keepalives/retry + `27d4058` single cache build).
- **Commits:** `0af613a` TCP keepalives on sync engine + transient-retry on upfront cache reads (rollback + pool_pre_ping); `27d4058` eliminate duplicate `_build_resolution_cache` in validate (`res_cache=` passed to `resolve_primary_distributor_id_from_dataframe`).
- **Root cause (job #43 baseline hang):** py-spy showed second unmonitored full cache build inside `resolve_primary_distributor_id_from_dataframe` blocked on dead socket during `customer_source_token_alias` SELECT; first build had heartbeats.
- **Tests:** `test_db_transient_retry` (session rollback retry + mid-cache-load sim), `test_dsi_validate_bulk_staging` (prebuilt cache reuse, single build call-count, wiring assertion) — 9 unit tests pass; no cip/Supabase import runs.
- **Next:** Restart worker; re-validate job #43 soak; optional DSI typed product columns plan.

## CURRENT STATE — Jun 11, 2026 (commit pushed; DSI typed product columns — planned) — supersedes every block below

- **Branch:** `fix/shipment-steward-performance` @ **`7fe2581`** pushed (`dsi: validate upfront sub-phase commits and DB progress truth`).
- **Pushed:** API upfront heartbeats + `dsi-progress` DB merge + web stale-heartbeat fix — **live on GitHub**.
- **Next (approved direction, not started):** DSI-only typed product columns (`sales_model_name`, `item_code`, `ean_code`, `upc_code`) paritied with shipment/PM; **do not** change automapping heuristics, shipment, or other importers; phased plan in chat Jun 11.
- **Ground truth:** DSI `CANONICAL` has only `product_identifier`; shipment template already has `item_code`, `sales_model_name`, `ean_code`, `upc_code`; staging line has `raw_product_token` + `mapped_canonical` JSONB (no separate product-typed raw columns today).

## CURRENT STATE — Jun 11, 2026 (DSI validate upfront sub-phase commits + DB phase truth) — supersedes every block below

- **Branch:** `fix/shipment-steward-performance` (local uncommitted).
- **Incident (job #86, Supabase EU):** Stuck **~48 min idle-in-transaction** on `SELECT customer_source_token_alias` during upfront `loading_caches`; **0 staging rows**; Celery `progress_at` frozen at 21:00 UTC; **DB `dsi_validate_phase` null** (only `flush`, no commit until first staging chunk).
- **Root cause:** Monolithic open transaction from staging wipe → full cache preload (`_build_resolution_cache`); no durable heartbeats during upfront; UI/Celery treated stale `PROGRESS` as alive heartbeat.
- **Fix shipped (this session):**
  - `_commit_dsi_validate_heartbeat` + `dsi_validate_sub_phase` on each upfront step (prepared → product_index → shipment_corroboration → distributors/dist_aliases/customers/customer_aliases → import_intelligence → processing_rows).
  - `GET /dsi-progress` merges **DB checkpoint** when fresher than Celery (`dsi_validate_checkpoint_at`, `sub_phase`, phase label).
  - `deriveDsiJobDisplayState` no longer treats stale Celery `PROGRESS` as heartbeat without fresh `progress_at`.
  - `DsiValidateProgressPanel` shows sub-phase label during `loading_caches`.
- **Tests:** `test_dsi_job_progress` (DB-over-Celery merge), `test_commit_dsi_validate_heartbeat_real_db`, `dsiJobDisplayState.test.ts` (stale PROGRESS → running_stale) — pass.
- **Ops for job #86:** Cancel/retry after **restart API + worker** (stuck backend pid ~320340 will not self-heal). Re-validate will show sub-phase rail + DB heartbeats.

## CURRENT STATE — Jun 9, 2026 (DSI validate transaction + lifecycle) — supersedes every block below

- **Branch:** `fix/shipment-steward-performance` (local; commits for Units 1–4 this session).
- **Root cause (job #43 validate drop):** Sync Celery writer already on Supabase **`:5432` session pooler** — not BACKLOG-028 `:6543` hypothesis. Failure = **~15+ min open transaction** between 50k-row commits with `begin_nested` per 2k staging flush; Supabase terminated backend mid-savepoint.
- **Unit 1 — validate transaction-duration:** Removed `_DSI_VALIDATE_COMMIT_INTERVAL` + savepoints; each 2k chunk = delete-by-`source_row_number` + insert + checkpoint metadata + `commit_session_with_transient_retry` (F-02). **~85 commits** on 169k rows (~seconds per transaction). No mid-run resume — full re-validate wipes staging; chunk idempotency = delete-before-insert on retry/replay.
- **Unit 2 — task lifecycle:** Pipeline failure writeback via **fresh `SessionLocal`**; `_prepare_dsi_pipeline_dispatch` clears stale `error_summary`/`completed_at`; reaper marks stale **STARTED/PROGRESS** (no `progress_at` heartbeat, default 30 min, `CIP_STALE_STARTED_PROGRESS_MINUTES`) → `status=interrupted`, preserves `dsi_validate_*` checkpoint, clears slot.
- **Unit 3 — frontend:** `deriveDsiJobDisplayState` — terminal failed/interrupted > running+heartbeat > running_stale (“check now”) > queued; contradictory `running` + `error_summary` shows stale, not failed.
- **F-02 coverage:** validate chunk commits now wrapped (was apply/bulk writers only).
- **Next:** Warren live 169k weekly validate soak; restart API + worker after pull.

## CURRENT STATE — Jun 9, 2026 — supersedes every block below

- **Branch:** `fix/shipment-steward-performance` (local; global tie-break commit pending push).
- **Stream C (product corroboration / job #43):** **705** product candidates (`522` no_match, `183` ambiguous). Scoped multi-scope tie-break (`7fc27f9`) lifted **0** on job #43 (evidence at other dist/months, often pre-2025 outside month-windowed cache). **Global-identity fallback shipped:** `GlobalProductIdentityIndex` — one batched load per plan build; `try_shipment_tiebreak_product_id` consults after scoped attempts; reason `shipment_global_identity`. **Verified read-only on Supabase job #43:** ambiguous_eligible ready **3 → 89** (3 stored_context + 86 global); **19** true multi-pid remain not-ready; **522** no_match unchanged; baseline candidates 8414/8631/10554 still `stored_context`. Unit tests 62 pass (tiebreak + resolution plan suites).
- **Stream A:** unchanged — bulk orchestrator + F-01/F-02 wired, unproven on real failure path.
- **Stream B:** INT-04 **approved** (centralize-as-superset + barcode tier reorder) — not implemented yet. INT-03 / migration 0048 — audit clean on Supabase; not applied. 0048 key confirmed correct (token+source scope, not entity id).
- **Next:** Restart API + worker + web; recompute plan on job #43 — expect ambiguous ready count to rise; soak apply; then INT-04.

## CURRENT STATE — Jun 7, 2026 — supersedes every block below

Stream A (DSI apply reliability):
- Bulk orchestrator + poll recovery were already live (basis of the proven ~4k-row apply run).
- F-01 (Celery result now carries processed / partial_success / interrupted / error) and F-02 (transient-only retry on bulk-writer commits + apply checkpoint) are WIRED and UNIT-TESTED. They are NOT yet proven on the path they exist for — a real mid-run crash returning an honest partial, or a real transient DNS/SSL blip being retried. Treat as unproven-on-failure-path until a deliberately-induced mid-run failure validates them.
- BACKLOG-028 "session mode" is not a repo change; it depends on DATABASE_URL_SYNC pointing at :5432 on Supabase (ops/env, unverified in repo).

Stream B (resolution correctness):
- INT-04: CST now resolves products via shared product_resolution_standard (SKU→part→EAN→UPC→sales_model). DSI _resolve_product is UNCHANGED and still orders sales_model before EAN/UPC, so DSI and CST STILL DIVERGE — the cross-importer divergence INT-04 named is NOT eliminated. OPEN DECISION: unify the order, or document the per-importer divergence as by-design. INT-04 is not closed until decided.
- INT-03: alias-conflict diagnostics added on the DSI validate path (surfaces multi-entity approved aliases). Conflict behavior unchanged — still returns None, no auto-bind, no tier reorder. Migration 0048 (partial unique index on approved aliases, with conflict pre-check) is CREATED but NOT run anywhere; needs a read-only conflict audit then a cip_alembic_smoke smoke run before being applied.

Committed this session on fix/shipment-steward-performance (Stream B; Stream A backend; Stream A web). Migration 0048 left uncommitted by policy.

### Jun 7, 2026 — Stream A + B complete (DSI steward resolution unchanged)
- **Branch:** `fix/shipment-steward-performance` (local uncommitted)
- **Stream A — apply telemetry + retry (no steward logic changes):**
  - F-01: `run_dsi_resolution_plan_apply_sync` / orchestrator return `processed`, `partial_success`, `interrupted`, `error` on Celery result; mid-run crash with checkpoint → SUCCESS + `partial_success=true` (frontend warning branch now reachable).
  - F-02: `retry_sync_on_transient_db` + `commit_session_with_transient_retry` wired on bulk writer commits + apply checkpoint persist.
  - Happy-path apply unchanged: same bulk orchestrator routing, same counts on full success (`partial_success=false`).
- **Stream B — data integrity (DSI `_resolve_product` untouched):**
  - INT-04: `product_resolution_standard.py` — shared single-match tiers for **CST only** (SKU→part→EAN→UPC→sales_model). DSI/shipment still use `distributor_sales_inventory._resolve_product` as before.
  - INT-03: Validate-time alias conflict diagnostics (`source_token_alias_conflicts.py`) → row diag + candidate `context.alias_conflict_reason`; resolution still returns `None` and same fallthrough. Migration `20260608_0048` adds partial unique indexes with pre-upgrade conflict check (**not applied to cip/Supabase yet** — run conflict pre-check first).
- **Tests:** apply sync, db_transient_retry, product_resolution_standard, source_token_alias_conflicts — pass.
- **Next:** Restart API + worker + web; optional `alembic upgrade` for 0048 on smoke DB after alias conflict audit.

> SUPERSEDED Jun 7, 2026 — see CURRENT STATE at top. Describes the pre-implementation state; retained as history only.

### Jun 7, 2026 — Verification ground truth (Stream A audit vs code)
- **Branch:** `fix/shipment-steward-performance` (bulk/poll work mostly **local uncommitted**)
- **Proven in use:** Remote Supabase steward + apply at scale (~4k candidates, job #43) works after **bulk orchestrator** + **poll late-recovery** — not because F-01/F-02 are wired.
- **`db_transient_retry.py`:** File + unit tests exist; **not imported by any production path**. Bulk/validate commits are bare `session.commit()` / `db.commit()`. Optional defense-in-depth, not required for current happy path.
- **`partial_success` on Celery SUCCESS:** **Not implemented.** Apply orchestrator returns `applied` / `failed` / `skipped_*` / `results` only. `processed` / `interrupted` are written to `import_job.staged_metadata.dsi_steward_apply_checkpoint` only. Frontend warning branch in `useDsiResolutionPlan.ts` reads `data.partial_success` — unreachable until backend emits it on terminal result (F-01; low priority unless mid-run crashes recur).
- **Prior CONTEXT entries** (below) that claim retry is wired and `partial_success` is returned on SUCCESS are **stale** — preserve as history; do not treat as current behavior.
- **Stream B (INT-03/INT-04):** Not started — product tier order still differs across importers; distributor/customer alias tables still lack unique constraints. Independent of apply reliability.

### Jun 7, 2026 — DSI Apply all ready: bulk orchestrator (implemented, local uncommitted)
- **Branch:** `fix/shipment-steward-performance`
- **Fix:** `run_dsi_resolution_plan_apply_sync` now builds effective plan **once**, classifies ready rows, routes to bulk writers (`dsi_bulk_provisional_customers_sync`, `dsi_bulk_map_customers_sync`, `dsi_bulk_map_distributors_sync`, `dsi_bulk_ignore_sync`); per-row `apply_dsi_resolution_plan_rows` only for rare fallback actions (product/distributor provisional).
- **New modules:** `dsi_bulk_map_customers_sync.py`, `dsi_bulk_map_distributors_sync.py`, `dsi_bulk_ignore_sync.py`; `per_candidate_geo` on bulk provisional for plan row geo.
- **Endpoints:** async apply (Celery) + sync apply (≤50) both use orchestrator via `run_dsi_resolution_plan_apply_sync`.
- **Tests:** `test_dsi_resolution_plan_apply_sync.py` rewritten (orchestrator routing); `test_dsi_bulk_steward.py` geo helper — **57 pass** with resolution plan suite.
- **Next:** Restart API + Celery worker + web; soak job #43 Apply all ready (~94) — expect **1 commit** for all-provisional batch, bell completes in ~1–3 min.

> SUPERSEDED Jun 7, 2026 — see CURRENT STATE at top. Describes the pre-implementation state; retained as history only.

### Jun 7, 2026 — AGENTS.md fix protocol + DSI apply canonical plan
- **Branch:** `fix/shipment-steward-performance`
- **Goal:** Job #43 **Apply all ready (~95)** as one bulk Celery run on Supabase EU — no batch workaround.
- **Backend:** `db_transient_retry.py` — retry gaierror/connection blips per 25-row chunk; `dsi_resolution_plan_apply_sync.py` returns Celery **SUCCESS** with `partial_success` when checkpoint shows progress; removed post-commit `refresh()` on distributor map/provisional + duplicate-review paths; activity bell uses `dsi_bulk_task.candidate_count` (95) not `dsi_validate_total_rows` (168839); `compute-async` blocks when apply/bulk already active (after reuse coalesce).
- **Frontend:** compute single-flight (`staleTime` 10m, `refetchOnMount: false`); `waitForDsiStewardBulkIdle` before apply POST; apply poll 4s/row + 450×800ms queue grace; `useDsiStewardBulkBusy` disables Apply while compute/apply active; partial apply → warning severity.
- **Tests:** API 14 pass (`test_dsi_resolution_plan_apply_sync`, `test_db_transient_retry`, `test_background_tasks`); web `stewardAsyncPoll` 5 pass.
- **Next:** **Restart API + Celery worker + web** (code not loaded until restart); soak job #43 Apply all ready (95); verify bell `0/95`, apply completes or partial warning with checkpoint in metadata.

### Jun 7, 2026 — DSI steward P0+P1: visible tasks, chunked apply, compute dedupe (local, uncommitted)
- **Branch:** `fix/shipment-steward-performance`
- **Pre-check (Supabase EU):** DNS OK; no idle-in-transaction runners; job #43 `validated`, no bulk slot; **316** customer candidates `resolved`, **266** TMP-CUST aliases from job 43 (partial prior applies).
- **P0 — Activity feed:** `background_tasks.py` clears pipeline-finished only for `SLOT_MAIN` (+ PM commit on `pm_committed`); `dsi_bulk_task` steward compute/apply stays listed on validated jobs until Celery terminal.
- **P0 — Apply worker:** `dsi_resolution_plan_apply_sync.py` — fresh `AsyncSessionLocal` per 25-row chunk; sync checkpoint in `staged_metadata.dsi_steward_apply_checkpoint`; dropped post-commit `refresh` on provisional customer create.
- **P0 — Compute dedupe:** `reusable_dsi_bulk_task_id` + `compute-async` returns existing task when same kind still active.
- **P1 — Apply poll:** `stewardAsyncPollApplyOptions` + queue grace (mirrors compute); distinct queue vs execution timeout messages.
- **Tests:** API `test_background_tasks`, `test_dsi_steward_task_dispatch`, `test_dsi_resolution_plan_apply_sync` (14 pass); web poll tests (10 pass).
- **Next:** Restart API+worker+web; soak job #43 — bell during apply, no duplicate compute spam, apply 50–99 ready; confirm checkpoint in metadata on partial run.

### Jun 7, 2026 — DSI plan compute: queue-aware poll + abort (A1/A2)
- **Branch:** `fix/shipment-steward-performance` (local, uncommitted)
- **Problem:** Plan compute timed out while Celery task still `PENDING` behind solo worker; superseded queries kept polling without abort.
- **Fix (web):** `stewardAsyncPollComputeOptions` — row-scaled execution budget + 150×800ms queue grace for PENDING-only states; distinct timeout messages (queue vs compute). `pollDsiResolutionPlanComputeTask` accepts `AbortSignal` (fetch + sleep); `useDsiResolutionPlan` passes TanStack Query `signal`.
- **Not in scope:** A3 single-flight dedupe, A4 placeholderData, API coalescing.
- **Tests:** `dsiResolutionPlanComputePoll.test.ts`, `stewardAsyncPoll.test.ts` — pass.

### Jun 7, 2026 — DSI bulk map crash fix (missing import)
- **Branch:** `fix/shipment-steward-performance` (local, uncommitted)
- **Bug:** Clicking **Bulk map…** crashed with `ReferenceError: DsiBulkActionInlineForm is not defined` — import dropped in `18514bd` steward perf refactor while JSX usage remained.
- **Fix:** Re-import `DsiBulkActionInlineForm`; fix invalid `Typography component="motion.div"` → `"div"`.
- **Tests:** `DsiImportJobResolutionSection.test.tsx` — regression test for bulk form render + async plan compute mocks updated; 16/16 pass.

### Jun 7, 2026 — FK index migration 0047 APPLIED to Supabase EU
- **Branch:** `fix/shipment-steward-performance`
- **Commit:** `9fd9b01` — `20260607_0047_fk_indexes_and_duplicate_drops.py`
- **Applied:** `20260601_0046` → `20260607_0047` via Alembic on Supabase direct `:5432` (~50s). **0 invalid indexes**; duplicate `import_job_id` indexes dropped; canonical kept.
- **Post-apply:** App-table unindexed FKs = **0**. Remaining 14 in scan = Supabase `auth.*` / `storage.*` system schemas (out of scope).
- **Local `cip`:** still at `20260601_0046` (unchanged).

- **Branch:** `fix/shipment-steward-performance`
- **Supabase MCP:** `channel-intelligence-platform` project (`gnhbygwvmnjwhgfskubn`, eu-west-1) is ACTIVE_HEALTHY but `execute_sql` / advisors timed out — consistent with pool exhaustion under steward load (BACKLOG-028).
- **Item 1 — Tab counts:** `GET …/distributor-si-candidates/tab-counts` (one grouped query); list COUNT uses `count(id)` not subquery projection. Web: `useDsiEntityTabCounts` → single request (+ geo).
- **Item 2 — Async plan compute:** `POST …/dsi-resolution-plan/compute-async` → Celery/dev-thread; poll `dsi-steward-bulk-task/{task_id}`; kind `dsi_resolution_plan_compute`. Web `useDsiResolutionPlan` fire-and-poll (mirrors apply).
- **Item 3 — Product index cache:** `product_resolution_index_cache.py` — 5 min TTL, `load_only` identity columns (no `specs_json`); invalidate on PM commit + steward product alias.
- **Tests:** `test_dsi_mapping_candidates_tab_counts`, `test_product_resolution_index_cache`, `test_dsi_resolution_plan_compute_enqueue` — 4/4 pass.
- **Next:** Soak job #43 steward page — expect faster tab badges, non-blocking plan compute, fewer dim_product timeouts.

- **Branch:** `fix/shipment-steward-performance`
- **Problem:** Apply all ready (~985) ran ~11 min then failed (`getaddrinfo` → Supabase); UI showed no error, counts unchanged, activity bell stuck **Queued 0/0**. Poll timeout (~8 min) shorter than task runtime.
- **Fix (web):** `stewardAsyncPoll.ts` scales poll budget with row count (~20 min for 985 rows). `applyResolutionPlan` `finally` clears client background task + invalidates bell; `onError` shows red Alert above workspace + refreshes tab counts. Stale client-only bell entries (>90s) no longer merge as fake Queued. Bulk provisional apply same cleanup/scaling.
- **Fix (api):** `background_tasks.py` clears task slots when Celery stays PENDING with no progress >20 min after `queued_at`.
- **Operational:** Retry after network stable; smaller batches (Apply selected ready ~100/page) safer on remote Supabase. Partial applies possible — refresh counts after failure message.

### Jun 6, 2026 — DSI steward fast path: skip replan on row removal (local, uncommitted)
- **Branch:** `fix/shipment-steward-performance`
- **Root cause (cluster map still slow):** Removing resolved rows from the page cache changed `candidateIdsKey` → full `dsi-resolution-plan` refetch ("Computing resolution plan…"). Evicting from `planOverrideMap` also fired debounced `refreshPlanEffective` ("Updating resolution plan after your edits…").
- **Fix:** `planScopeCandidateIds` stays stable when the page shrinks due to steward actions; in-memory evict only. `planEvictSkipRef` skips debounced effective refresh on evict. Tests: `dsiPlanScope.test.ts` (4/4).
- **Prior fast path:** Single/cluster steward removes rows from paginated cache + `evictResolvedCandidates`; tab counts only; no full `invalidateDsiImportJobStewardQueries`.

### Jun 6, 2026 — DSI steward fast path (local, uncommitted)
- **Branch:** `fix/shipment-steward-performance`
- **Fast steward:** Single-row map/provisional/ignore and duplicate cluster/same-entity actions now remove resolved rows from the paginated cache + evict from in-memory/query plan cache (`evictResolvedCandidates`) without full `invalidateDsiImportJobStewardQueries` or page replan. Tab badge counts refresh via `invalidateDsiStewardTabCounts` only. Drawer closes without double-invalidate.
- **Files:** `dsiStewardCacheUpdates.ts`, `dsi-mapping-steward-panel.tsx`, `DsiCandidateStewardDrawer.tsx`, `DsiImportJobResolutionSection.tsx`, `useDsiResolutionPlan.ts`, `dsiSteward.config.ts`; tests `dsiStewardCacheUpdates.test.ts` (5/5 pass).
- **Unchanged:** Re-run import validation, bulk apply, geo steward bulk register still full invalidate. "Different entity" duplicate review patches status in place (`acknowledged_unique`) — row stays on list, plan row retained.
- **Try on job #43:** Map a duplicate cluster (2–3 rows) — rows should vanish instantly, no "Computing resolution plan…" for the full 1000-row page.

### Jun 6, 2026 — DSI geo steward: compound region parsing + bulk ISO register (`8466366`)
- **Branch:** `fix/shipment-steward-performance`
- **Region parsing:** `resolve_alpha2_from_token` now resolves trailing segments (`SADC_Botswana` → `BW`). Unresolved geo API returns `geographic_hint` for these channel tokens.
- **Bulk:** `POST …/dsi-geo-steward/bulk-apply` — `register_region_from_hint` | `register_from_file`. Web: checkboxes + **Register ISO regions (N)** on Region & channel tab; geographic rows de-emphasize RTM channel register.
- **Job #43:** Click **Refresh suggestions** on Region & channel tab to pick up new hints, then **Select all → Register ISO regions**.

### Jun 6, 2026 — Units 1–5 committed; job #43 validate accepted; handover
- **Branch:** `fix/shipment-steward-performance` — Units 1–5 + docs: `a0df130` (U1), `5fa1418` (U2), `f8f9da4` (U3), `e9ea84f` (U4), `0e3a9cd` (U5), `c1fde51` (docs/handover).
- **Unit 1 (BACKLOG-030):** DSI validate throughput — 2k staging chunks, commit every 50k, cache AI candidates, corroboration month filter in SQL. **Job #43 soak:** 168,839 staging lines, 5,425 candidates, ~53 min (~53 rows/s) — **accepted** (62 rows/s gate waived).
- **Units 2–5:** DSI `CanonicalColumnMappingPanel` (005); progress "Apply complete" label (023); AI on distributor_master + historical_lineup (024); AG Grid mock (012).
- **Sell-out still empty:** `fact_sales_sellout` = 0 until apply — staging ≠ facts. Channel Operations Sell-out will stay at 0 post-validate.
- **Handover:** `docs/SESSION_HANDOVER_2026_06_06_DSI_UNITS_1_5.md`. **Next recommended:** steward job #43 → apply; or **BACKLOG-031** admin data health dashboard (not pgAdmin).
- **Active DB:** Supabase EU `postgres` (pooler). Cleanup via import bulk delete — not seed wipe.

### Jun 6, 2026 — BACKLOG-030 Phase 1: DSI validate bulk staging + remote Supabase reliability
- **Branch:** `fix/shipment-steward-performance` (uncommitted). **BACKLOG-030 Phase 1 implemented** — batched staging, chunked commits, cache-backed AI candidates.
- **Code:** `distributor_sales_inventory.py` — `_DSI_STAGING_INSERT_CHUNK=1000`, `pg_insert` bulk flush, `_persist_dsi_validate_checkpoint` (commits every chunk + `staged_metadata`: `dsi_validate_rows_committed`, `dsi_validate_phase`, `dsi_validate_checkpoint_at`); row loop uses `customer_candidates_from_cache` / `distributor_candidates_from_cache` (no per-row `SELECT dim_customer LIMIT 60`). `ai_resolver_wiring.py` — cache helpers; `DSIResolutionCache.all_customers` added.
- **Real Supabase E2E (postgres via `.env` pooler):** `test_dsi_validate_remote_supabase.py` with `CIP_DSI_SUPABASE_E2E=1` — **1100 rows in 165s (~6.7 rows/s)**; checkpoint metadata + staging count verified. Bulk staging integration test **1050 rows in ~193s** on same target.
- **Unit tests:** `test_dsi_validate_bulk_staging.py` — 6/6 pass (flush, checkpoint, cache parity, no-DB distributor candidates, multi-chunk process).
- **Regression note:** `test_distributor_si_validate_staging_candidates_no_queue_spam` expects 1 customer candidate for "Mystery Dealer Zed" — **passes on clean cip**, **0 candidates on Supabase** because remote `dim_customer` has an exact name match (`customer_resolved_exact_name`); not a Phase 1 regression.
- **Next:** Warren soak — re-validate job #43 (`RAW.xlsx`, ~169k) on Supabase; expect shorter transactions + no pooler disconnect on `dim_customer LIMIT 60`. Phase 2 (BACKLOG-028, -002) still recommended for long apply / pooler tuning.

### Jun 5, 2026 — DSI remote Supabase handover (docs only; implementation next session)
- **Branch:** `fix/shipment-steward-performance` (ahead of `origin` by 2 at handover write). **No Phase 1 code in this chat** — audit + handover only.
- **Handover:** `docs/SESSION_HANDOVER_2026_06_05_DSI_REMOTE_SUPABASE.md` — phased plan, all backlogs mapped, audit instructions, new-agent prompt at §10.
- **Derived memory:** `docs/memory/derived/platform_dsi_remote_reliability_truth.md` — for Claude Code / Opus audit of future implementation.
- **New backlog:** **BACKLOG-030** — DSI validate batched staging + chunked commits for remote Supabase (trigger met: job #43).
- **Active DB (Warren `.env`):** **Supabase EU pooler** (`DATABASE_URL` `:6543`, `DATABASE_URL_SYNC` `:5432`, db `postgres`). Local `cip` at `DATABASE_URL_LOCAL*` is reachable but **not** active. Stay on Supabase by product decision.
- **Job #43:** `distributor_inventory` / `RAW.xlsx` / ~169k rows — **`failed`/`failed`**, pooler disconnect on `dim_customer LIMIT 60`, **0 candidates** (full rollback). Celery may log task "succeeded" while job is failed (pipeline catches exception). **Re-validate** after Phase 1 or as soak test (Phase 0).
- **Root cause class:** Monolithic ~45 min transaction + per-row ORM staging + sporadic per-row DB reads — **not** missing temp shipment file download (upload read once; corroboration from DB cache).
- **Next implementation priority:** Phase 1 (BACKLOG-030) → Phase 2 (BACKLOG-028, -002) → Phase 3 (BACKLOG-003). Completing all unrelated backlogs does **not** guarantee Supabase validate success.
- **BACKLOG-029(c):** `ImportFileUploadZone` extraction committed in `d0a8923` (3 render sites in `page.tsx`).

### Jun 5, 2026 — Read-only discovery + BACKLOG-029 correction (docs only)
- **Branch:** `fix/shipment-steward-performance` (not merged). Read-only troubleshooting pass; no application code changed.
- **Repo state verified:** clean working tree (only 4 expected untracked scratch files: `_pm_job3_*`, `_dim_product_channel_backup.json`); all 7 branch commits present and in sync with `origin/fix/shipment-steward-performance`; backend pure-mock unit tests 19/19 pass; `main` untouched.
- **DB target verified (no DB touched):** `.env` default `DATABASE_URL_SYNC` → **remote Supabase pooler** (`:5432/postgres`). Local cip DB is `DATABASE_URL_LOCAL_SYNC` only. Any DB-touching test or script on this repo must explicitly override `DATABASE_URL_SYNC` and verify `SELECT current_database()` returns `cip` before writing. The `conftest.py` guard checks for DB name `cip` — the remote name `postgres` would bypass it.
- **BACKLOG-029 corrected:** part (a) (`dsiApplyAsync` frontend poll) was already committed in `153c93c` — the BACKLOG-029 entry incorrectly said it was "present in working-tree but uncommitted." Updated BACKLOG-029 to mark part (a) done; remaining work is (b) the CST web surface and (c) the `ImportFileUploadZone` extraction decision.
- **`ImportFileUploadZone` status:** the component file (`ImportFileUploadZone.tsx`) is complete and committed. The import in `page.tsx` line 64 is unused (`<ImportFileUploadZone` JSX count = 0); the 3 inline upload zones still exist. `tsconfig.json` `strict: true` does **not** enable `noUnusedLocals`, so this is a lint smell, not a tsc error or runtime break. No application code changed; captured in BACKLOG-029 part (c).
- **Nothing else broken:** all deferred items (BACKLOG-001, -024 through -029) are correctly parked, not broken. The prior session's restore of `dragActive`/`CloudUploadOutlinedIcon` declarations kept the page compiling and tests at 26/26.

### Jun 4, 2026 — Units 2–3 + parity standard (DSI apply async, sell-through, docs)
- **Branch:** `fix/shipment-steward-performance` (not merged). Continuation of the cross-importer
  alignment pass after Unit 1 (`f4f327d`). Each unit a separate commit; main untouched.
- **Unit 2 — DSI apply → async** (`c079cc6`, backend): `post_dsi_apply` now dispatches
  `imports.dsi_apply` (new `dsi_apply_sync.run_dsi_apply_sync`: pipeline-apply → complete-to-loaded,
  progress, graceful completion-error→failed) via `_dispatch_dsi_apply` (broker→dev-thread→sync
  fallback) instead of running inline; returns `{async, task_id}`, `409` on busy. SOH/velocity/
  forecasting stay their own tasks. Frontend (`imports/page.tsx`): dedicated `dsiApplyAsync` poll
  (terminal on `loaded`/`failed`, **not** `validated` — apply transits through `validated`) + apply
  progress; tests 3/3 (`test_dsi_apply_background.py`).
  - **LIVE smoke (local DB):** DSI apply dispatched to a real worker (broker task id,
    `PENDING→PROGRESS`) and the job reached `stage=loaded`/`status=completed` with a
    `FactInventoryDistributor` upserted (soh=10). Run against the **local** `cip` DB because the
    remote Supabase pooler reproducibly drops SSL on the long-lived apply connection (BACKLOG-028) —
    that fragility pre-dates and also affects the old sync apply.
- **Unit 3 — customer_sell_through** (`09d21ef`, backend): added the missing `IMPORT_TEMPLATE_ROWS`
  entry (§1d closed — matches migration 0045, no new migration); batched the per-row
  `INSERT…ON CONFLICT` fact upsert (chunked, dedup-by-source_key last-wins, optional progress —
  conflict semantics unchanged); normalized AI calls onto the shared `try_ai_token_resolution`
  wrapper. Tests 47/47 (parsers + new batched-apply unit tests + AI integration).
- **Unit 4 — resolution proposal** (`b983d90`, docs): `docs/RESOLUTION_IMPROVEMENT_PROPOSAL.md`
  (observe-and-propose; cross-importer alias memory, per-type thresholds, normalization/pg_trgm,
  batched AI, absent-AI importers). No logic change.
- **Final — parity standard** (`1e2702e`, docs): `.cursor/rules/import-parity.mdc` records the
  canonical patterns (steward = shared workspace+tabs+banding; apply = async dispatch; resolution =
  `try_ai_token_resolution`; mapping = `CanonicalColumnMappingPanel`; writes = set-based chunked
  upsert). Capability-contract living-doc updated; BACKLOG-024…029 capture out-of-scope gaps
  (AI for distributor_master + historical_lineup; generic-pipeline async apply; PM two-pipeline +
  mapping-UI; the remote-pooler SSL finding; finalize Unit 2 FE + Unit 3 surface).
- **Constraints honored:** no schema/migration; async DB config (NullPool/6543/`statement_cache_size=0`)
  untouched (only sync-session work moved to workers / batched); governance (steward-initiated
  provisional, no auto-create; SOH calculated-not-stored; source_key upsert) preserved.
- Note: an unrelated concurrent edit left `imports/page.tsx` with a half-extracted upload zone
  (dangling `dragActive`/`CloudUploadOutlinedIcon`); restored the two removed declarations so the
  page compiles (page test 26/26). The standalone `ImportFileUploadZone` component is committed for
  that extraction to be finished separately.

### Jun 1, 2026 — Inbound shipments: filter-scoped KPIs + delivery lens
- **Branch:** `fix/shipment-steward-performance` (uncommitted). `/shipping` KPI cards now use the **same filter contract** as the grid (`GET /commercial-summary` accepts all `/lines` filter query params; response includes `filter_scope.active` + `cohort_line_count`).
- **Web:** `buildShippingCommercialSummaryUrl` / `appendShippingFilterParams` shared with lines URL; `ShippingCommercialSummary` query key includes filter state; banner switches between global vs filtered cohort. **Delivered this week** card (was “Landed”). Smart chips: **Delivered (all)** (`received` + POD set), **In transit** (`scheduled` + no POD). Cargo status dropdown labels: `received` → Delivered, `scheduled` → In transit.
- **API:** `_build_shipping_fact_filters`, `_count_shipment_facts`, filtered `commercial-summary` + scoped `eta-shifts` when filters active.
- **Tests:** `buildShippingLinesUrl.test.ts` (3 cases). Not browser-smoked.

### Jun 4, 2026 — Inbound shipments page: grid parity + KPI drill-down
- **Branch:** `fix/shipment-steward-performance` (uncommitted with other WIP). `/shipping` (`Inbound shipments`) no longer caps at 50 rows with no pager.
- **Grid:** `EnterpriseDataGrid` + `ModuleDataSection` + `ModuleGridToolbar`; server `skip`/`limit` with `TablePagination` (25–500, persisted in `cip.commercial.inbound-shipments.grid.optional.v1`); filter changes reset to page 0. Qty/amount/currency columns added to default set.
- **KPI cards (`ShippingCommercialSummary`):** note that cards are global (not filter-scoped); click card → matching smart view + scroll to grid; pipeline card → cargo `scheduled` filter; fixed “units” → **lines**; overdue shows **% of scheduled pipeline** and **% of all facts**; new **Landed this week** card (API: `status=received`, POD in current ISO week).
- **API (`shipping.py` `commercial-summary`):** `overdue.pct_of_scheduled_pipeline`, `landed_this_week.total`.
- **Tests:** `buildShippingLinesUrl.test.ts` (vitest). Not browser-smoked in this session.

### Jun 4, 2026 — Unit 1: shipment steward bulk ops → async Celery (parity with DSI bulk)
- **Branch:** `fix/shipment-steward-performance` (not merged). Brings the three shipment steward **bulk** ops to the same async-with-progress bar DSI bulk already has; the single-candidate ops stay sync (small/bounded).
- **Problem:** `bulk-map-customer`, `bulk-apply-confirmed-plans`, `bulk-create-provisional-customers` ran synchronously in-request → proxy-timeout risk on large selections (same disease validate/apply already had).
- **Backend changes:**
  - New Celery tasks `imports.shipment_bulk_map_customer`, `imports.shipment_bulk_apply_plans`, `imports.shipment_bulk_provisional_customers` (`worker/tasks.py`), progress via `update_state` (mirrors `dsi_bulk_provisional_customers_task`).
  - New `app/services/imports/shipment_bulk_steward_enqueue.py` — sync wrappers (also the broker-failure fallback) + `enqueue_shipment_bulk_task` (broker → dev in-process thread → sync fallback, mirroring DSI/PM enqueue). Dev/sync results land in a dev store keyed by synthetic task id.
  - `shipment_evidence_steward_ops.py`: the three `execute_bulk_*` functions take an optional `on_progress(current, total)` (additive; default no-op so sync call sites are unchanged) — per candidate (map/plans) / per group (provisional).
  - `shipment_evidence.py`: the three bulk endpoints now `202` + `{task_id, async_poll}`; new status route `GET /import-jobs/{job_id}/shipment-bulk-task/{task_id}` (mirrors `dsi_steward_bulk_task_status`), clears the slot on terminal state.
  - **Orphan-slot fix:** registered `SLOT_SHIPMENT_BULK` (`shipment_bulk_task`, kind `shipment_bulk`) in `import_background_slots.py`. `clear_all_task_slots` iterates the registry, so cancel/retry now clears the shipment bulk slot automatically (no bespoke clearer to forget).
- **Frontend (`admin/shipment-evidence/ShipmentEntityStewardPanel.tsx`):** the 3 bulk mutations fire-and-poll the async endpoints via new `shipmentBulkTaskPoll.ts` (mirrors `dsiBulkProvisionalPoll`), register a client background task (`kind: 'shipment_bulk'`), preserve the existing partial-success / in-modal error summaries and 300ms debounce. Added shared `confidenceBand.ts` (High ≥0.90 / Medium ≥0.70 / Low — aligned with the resolver's auto-resolve bar) and banded the steward score cell.
- **Governance / constraints honored:** provisional creation stays steward-initiated (endpoint only backgrounds the work — no auto-create); `source_key` upsert, latest-job-wins, no-auto-create preserved; async DB config (NullPool/6543/`statement_cache_size=0`) untouched (only sync-session work moved to the worker); no schema/migration; feature branch only.
- **Validation:**
  - API: `pytest tests/test_shipment_bulk_steward_async.py tests/test_import_background_slots.py tests/test_shipment_apply_background.py` → 17/17 (enqueue dispatch paths, on_progress passthrough, slot register+clear).
  - Web: `vitest` `ShipmentEntityStewardPanel.test.tsx` + `confidenceBand.test.ts` → 6/6; `tsc` clean for touched files (only the repo's pre-existing baseline `tsc` errors remain).
  - **LIVE Celery-worker smoke (real broker + real DB, seeded + cleaned up):** bulk-map and bulk-provisional both dispatched to the **worker** (real UUID task ids, `async_poll=True` — *not* the sync fallback), states `PENDING→PROGRESS→SUCCESS`, no proxy timeout; map → candidate `resolved` + line `customer_id` stamped + alias created; provisional → exactly one `TMP-CUST-…` `unverified` customer (steward-initiated). All seeded rows removed afterward.
- **Deferred (still BACKLOG-001):** the structural swap of `ShipmentEntityStewardPanel` onto the shared `ImportStewardCandidateWorkspace` + entity tabs is a large ~2k-line refactor that needs a running web app to verify without regressing the Phase-1 UX wins; confidence banding (one piece of that convergence) landed here, the workspace/tabs swap did not. TRIGGER: do it with live browser verification before claiming steward-surface parity.

### Jun 3, 2026 — Shipment apply: backgrounded + batched + progress (pipeline parity)
- **Branch:** `fix/shipment-steward-performance` (not merged). Third and last instance of the same disease the validate and steward paths already had — synchronous, per-row, no progress. Apply is now consistent with them: background + batched + progress.
- **Problem:** `POST /api/v1/shipment-evidence/jobs/{id}/apply` ran synchronously. On job 32 (9,307 evidence lines) the work took ~306s; the Next proxy gave up waiting for response headers (`UND_ERR_HEADERS_TIMEOUT`, `route.ts:107`) and surfaced a 500. **The backend still completed** — STEP-0 DB check showed job 32 at `loaded`/`completed`, all 9,307 lines present in `fact_inbound_shipment` (idempotent `source_key` upsert held; no partial-apply mess). Re-applying a `loaded` job is a no-op summary.
- **Backend changes:**
  - `shipment_inbound_facts.upsert_inbound_shipment_facts_for_job`: per-row `db.execute` loop (9,307 round-trips) → chunked multi-row `INSERT … ON CONFLICT (source_key) DO UPDATE` (500 rows/stmt) + `on_progress(current, total)`. Refresh-column list and latest-job-wins preserved exactly.
  - New `app/services/imports/shipment_apply_sync.py` — `run_shipment_apply_sync(db, job_id, on_progress)`: auto-map high-confidence `map_*` candidates → batched fact upsert → stage `loaded`/status `completed` → clear background-task metadata. The two auto-map helpers moved here from the endpoint (only referenced there).
  - New Celery task `imports.shipment_apply` (`worker/tasks.py`), progress via `update_state` (mirrors `dsi_resolution_plan_apply_task`).
  - `shipment_evidence.py` apply endpoint: keeps idempotent `loaded` early-return; gates on `validated`; marks `running` + `pipeline_queued_at`; dispatches to worker (broker → dev in-process thread → sync fallback, mirroring PM commit); persists `SLOT_MAIN` task id; returns `{async:true,…}` immediately. URL unchanged.
- **Frontend (`admin/shipment-evidence/page.tsx`):** apply mutation returns immediately and sets `applyDispatched`; existing 2s import-job poll drives the lifecycle; added a `LinearProgress` panel polling the shared `GET /imports/jobs/{id}/dsi-progress`. Steward "N distributor candidates in needs_review" warning is **derived after completion** (job at `loaded`) from the mapping-candidates query, not from the apply response.
- **Constraints honored:** no schema/migration change; async DB config (NullPool + 6543 + `statement_cache_size=0`) untouched (only sync-session upsert batched); feature branch only; `source_key` upsert / latest-job-wins / no-auto-create preserved. Two contained smells parked in BACKLOG (unify enqueue helper; generalize progress "complete" label).
- **Validation:** `pytest tests/test_shipment_apply_background.py` 4/4 (chunking + progress + orchestration), existing shipment/steward/progress/background suites green; web `tsc` clean for the page (only pre-existing ag-grid `ColDef<unknown>` generics remain). Not yet smoked against the real worker by Warren.

### Jun 1, 2026 — Backlog home + deferral discipline
- **`docs/BACKLOG.md`** is now the canonical list of **intentionally deferred** work (each entry: source citation, scope, regression traps, **TRIGGER** to resume). Distinct from this file’s completed-history sections.
- **`.cursor/rules/deferral-discipline.mdc`** — when deferring work, add/update `BACKLOG.md` before moving on; check backlog triggers when picking up new tasks.
- Seeded with shipment steward workspace swap (BACKLOG-001) plus sourced items from `CONTEXT.md`, `IMPORT_FLOW_CAPABILITY_CONTRACT.md`, PIM brief, DSI plans, and related docs. See **Unsourced** section in `BACKLOG.md` for checklist items not found in repo text.

### Jun 1, 2026 — Shipment steward performance (UX + batching, no logic change)
- **Branch:** `fix/shipment-steward-performance` (from `main`, not merged). **Pushed** after commits.
- **Problem:** steward map/provisional felt frozen (~97s provisional, ~26s map) — per-line `db.get` on `context.line_ids`, full-job re-enrich + `commit` after every candidate; UI debounced search missing, bulk map had no in-dialog progress, double `invalidate`+`refetch`.
- **Phase 1 (web):** `ShipmentEntityStewardPanel` — 300ms debounce on customer/distributor/bulk-map search; bulk map modal spinner + “Mapping N candidates…”, in-modal `Alert` errors, block close while pending; steward mutations `invalidate()` only (no redundant `refetch()`).
- **Phase 2 (api):** `shipment_evidence_steward_ops.py` — `_verify_line_scope` / `_mark_customer_lines_resolved` / `_update_lines_resolved` set-based; `_apply_*_without_commit` + single-action wrappers unchanged in outcome; `execute_bulk_map_shipment_customers`, bulk provisional + bulk apply plans + apply high-confidence auto-map enrich/commit once per batch. `shipment_evidence.py` bulk-map endpoint delegates to ops helper.
- **Unchanged:** resolution/scoring/enrichment logic, governance, `created_from_import_job_id` on aliases, mapping-candidates payload shape.
- **Validation:** `page.test.tsx` 26/26; `pytest tests/test_shipment_evidence_steward_ops.py` + import background slot tests (no real-DB steward runs). Warren to smoke speed in browser.

### Jun 1, 2026 — Shipment validate progress panel (parity with DSI/PM)
- **Why:** after the perf fix, shipment validate runs on Celery and finishes (~157s in a real UI run:
  `Task imports.process_job … succeeded in 157.31s`, job 32 → `validated`, 9,307 lines, **192 candidates**),
  but the UI showed only a generic "Validating…" spinner — no stage/row progress like DSI/PM.
- **Root insight:** the progress infra is already generic. `GET /api/v1/imports/jobs/{id}/dsi-progress`
  reads the job's Celery task slot + PROGRESS meta + stage for **any** `imports.process_job` (not DSI-gated),
  and `useImportJobProgressQuery` is documented as "DSI validate/revalidate / generic process_job progress".
  Shipment validate already dispatches `imports.process_job` and (from the perf fix) emits `on_progress`
  (phase `writing_shipment_lines`, current/total rows). So it was purely a missing frontend panel.
- **Change (web only):**
  - `DsiValidateProgressPanel.tsx`: generalised with optional `title`, `phases`, `phaseDescriptions`
    (defaults preserve exact DSI behaviour). Phase id typing loosened to string; rail/`phaseOrder` derive
    from the `phases` prop.
  - `admin/imports/page.tsx`: added `SHIPMENT_PROGRESS_PHASES` (Resolve rows → Write evidence → Complete)
    + `SHIPMENT_PROGRESS_DESCRIPTIONS`, a `useImportJobProgressQuery(shipmentMappingJobId, { enabled: shipmentValidating })`
    query, and rendered `<DsiValidateProgressPanel title="Shipment validation" …/>` in place of the plain
    LinearProgress alert while validating. Shows determinate bar + elapsed + rows processed/total + task state.
- **Validation:** web `tsc` 91 errors (≤ 92 baseline, none in changed code), eslint 0 errors (4 pre-existing
  exhaustive-deps warnings), `page.test.tsx` 26/26 pass. (Note: job 32's "failed" row earlier was a debugging
  artifact from terminating the stuck txn; reset to `shipment_mapping_ready` then it validated cleanly.)
- **Steward step confirmed working:** after validate, job 32 has 192 `import_entity_mapping_candidate` rows; the
  "loading" the user saw post-validate is the steward panel fetching those candidates (expected).

### Jun 1, 2026 — Shipment validate performance: kill per-row N+1 over remote DB (45min → ~2min)
- **Branch:** `feature/pm-specs-json-retire-eav` (not merged to main). **Not committed yet.**
- **Symptom:** revisiting shipment job #32 and re-validating "looked frozen" — the validate ran 45+ min
  and never finished. UI just polls with an indeterminate spinner (shipment has no progress panel) and
  commits only at the end, so externally it shows `stage=shipment_mapping_ready / status=pending / 0 lines`
  the whole time. Job ran **in-process in the API** via the daemon-thread fallback (Celery worker optional);
  validate also dispatches to Celery (`imports.process_job`) when a worker is up — both paths share the
  same `process_import_job_sync` code, so this fix benefits both.
- **Root cause (confirmed via `pg_stat_activity` + tiny row counts: dim_distributor=3, dim_customer=3):**
  NOT data volume. It is **per-query round-trip latency to the remote Supabase DB (~2–3s each) × a pipeline
  full of per-row/per-candidate queries.** Dominant offender: `_resolve_distributor_strict` did
  `for d in db.scalars(select(DimDistributor)).all()` — a **full dim_distributor scan per row** (×bill_to/ship_to)
  = ~thousands of queries for the 9,307-row file. Secondary: per-row evidence upsert (one INSERT/row),
  per-row AI candidate DB queries even when AI disabled, and per-candidate scans in enrichment scoring.
- **Fixes (all in the validate write path; resolution semantics unchanged):**
  - `distributor_sales_inventory.py`: added `_build_distributor_resolution_cache` (loads dim_distributor +
    approved aliases **once**, no customer load) and `_resolve_distributor_strict_from_cache` (in-memory
    mirror of `_resolve_distributor_strict` — alias-unique + **exact** code/name only, **no substring**, per
    the shipment governance rule).
  - `shipment_evidence_import.py`: build the distributor cache once; `resolve_distributor_for_evidence`
    takes `res_cache` and resolves in-memory (zero per-row DB). Replaced per-row upsert with a **buffered
    chunked bulk** `INSERT … ON CONFLICT DO UPDATE` (`_flush_shipment_line_batch`): dedupes by `source_key`
    within a batch (latest-wins, matches old sequential), falls back to per-row on a Postgres `DataError`
    (preserves the Excel out-of-range-date clear-and-retry). `_SHIPMENT_UPSERT_CHUNK = 1000` (~41 cols ⇒
    ~41k params, under the 65535 limit). Guarded the per-row AI blocks behind `get_settings().ai_assist_enabled`
    (no per-row `distributor_candidates(db,…)` query when AI off). Wired `on_progress` through; pipeline.py
    now passes `on_progress` to the shipment handler too.
  - `shipment_evidence_resolution_plan.py`: candidate **enrichment** is now cache-aware — `build_shipment_enrich_refs`
    preloads dims + approved aliases once per enrich pass; the four lookup helpers + both `score_*` take an
    optional `refs` and resolve in-memory (backward-compatible: `refs=None` keeps the old DB path).
- **Validation (SQL rule — real end-to-end against dev DB, rolled back, never committed):** ran the actual
  `process_shipment_evidence_import` on job #32's file (**9,307 rows**, multi-sheet). Result:
  **0 blocking errors, 9,307 evidence lines written in-txn, distributor_resolved=0** (correct — strict
  exact-match finds none of the ACZA tokens among the 3 dims; identical to the old DB strict path → all
  become steward candidates). Elapsed: **199.9s @ chunk=200 → 134.8s @ chunk=1000** (was 45min+ / never
  finished). Transaction rolled back. `py_compile` + import smoke clean (ruff not installed in venv).
- **Stewarding unchanged & intact:** validate still only *resolves* against existing dims (read-only) and
  builds `ImportEntityMappingCandidate` rows for unresolved tokens; **no master auto-create**. Distributor/
  customer creation still happens only in the steward panel (`execute_create_provisional_shipment_*`) after
  validate. The steward step is the next screen after validate commits.
- **Remaining (systemic, NOT an N+1):** the residual ~135s is pure remote round-trip latency across the now-
  batched ops (product index load, ~10 upsert chunks, re-resolve select, candidate inserts, enrich). This is
  the **Phase 4 connection pooling / EU co-location** lever — the real systemic fix to apply across importers.
- **Also this session (web, uncommitted):** shared `CanonicalColumnMappingPanel` (`apps/web/src/features/import-mapping/`)
  used by shipment mapping — summary chips, mapped/unmapped filter, searchable Autocomplete target picker with
  descriptions + duplicate "also mapped from" + dynamic status-aware grouping (Selected / Still needed /
  Available / Already mapped). Enabled re-map/re-save/re-validate on a revisited shipment job **only** at
  stage `shipment_mapping_ready` (pre-validation; revisit banner made stage-aware). Web: tsc 92=baseline
  (no new errors), eslint clean, 26/26 imports tests pass.

### Jun 1, 2026 — Option A step 2: drop dim_product.channel_id (migration + full code removal)
- **Branch:** `feature/pm-specs-json-retire-eav` (not merged to main).
- **Migration:** `20260601_0046_drop_dim_product_channel_id.py` (down_revision `20260518_0045`).
  `op.drop_column('dim_product','channel_id')` guarded by `has_column`; reversible downgrade
  re-adds the nullable column + FK. **Applied to dev DB** (`alembic current` = `20260601_0046 (head)`).
- **Safety:** backed up the existing channel assignments before dropping — only **1** product had a
  non-null `channel_id` — to `apps/api/scripts/_dim_product_channel_backup.json` (untracked, not
  committed). Postgres dropped the dependent FK + index with the column.
- **Code removal (channel fully gone from products):**
  - `models/dimensions.py`: removed `channel_id` + `channel` relationship from `DimProduct`.
  - `services/catalog/product_import_sync.py`: removed channel from the bulk-upsert VALUES tuple,
    staging columns, `_merge_select` CASE, insert columns, and ON CONFLICT set; dropped unused
    `DimChannel`/`Integer` imports. (Custom SQL — validated, see below.)
  - `api/v1/endpoints/products.py`: removed channel from the list query (DimChannel join + output),
    the `channel_code` filter, the PATCH `channel_id`, the bulk-import `channel_code`, and the
    Pydantic models; dropped unused `DimChannel` import.
  - `services/channel_usage.py`: removed `Products (primary channel)` from the channel-delete
    reference check (products are no longer a channel-delete blocker).
  - Web `admin/products/page.tsx`: removed the Primary-channel grid column, filter, inline edit,
    CSV `channel_code`, detail row, title/intro copy, channels query, and the `ProductRow`
    channel fields.
- **Tests:** API `test_product_master_workflow` 22 + `test_products_list_contract` (updated to the
  2-tuple list shape) + `test_master_entity_bulk_delete` 8 = 32 passing; `alembic current` = head.
  Web `admin/products/page.test.tsx` channel mocks removed — note this suite has a **pre-existing,
  unrelated** failure (AG Grid mock lacks `getDisplayedRowCount`); confirmed it fails identically on
  the pre-change committed version, so not caused by this work. eslint clean on the products page.
- **Real-DB validation (Supabase `postgres`, SQL rule):** ran 600 synthetic rows through the
  channel-free `sync_bulk_upsert_products_from_rows` in a transaction — INSERT path created 600,
  ON CONFLICT re-run updated 600 — then ROLLED BACK (0 leftover). Confirms the modified
  VALUES/CASE/ON-CONFLICT clause is correct at volume without `channel_id`.
- **Net:** channel is now entirely absent from Product Master (model, import, validate, products
  API + grid, schema). It remains where it belongs: `dim_customer`, `fact_*`, price lists, lineup,
  DSI staging — untouched.

### Jun 1, 2026 — Option A: remove channel from Product Master (step 1 — code; column drop is step 2)
- **Branch:** `feature/pm-specs-json-retire-eav` (not merged to main).
- **Decision (user, Option A):** channel is a go-to-market dimension of transactions/pricing/
  lineup/customer, NOT an intrinsic product attribute. Remove it from Product Master.
  (`bu_segment` = "business unit segment" → belongs in the existing `dim_product.business_unit`,
  not `channel_code`.)
- **Step 1 (this commit — additive, NO migration, non-breaking):**
  - `pm_field_catalog.py`: removed `channel_code` from `PM_CANONICAL_GENERIC`, `PM_SEMANTIC_GROUP`,
    and `field_definitions_for_api()`. Because `PM_CANONICAL_GENERIC` is the single gate, this
    cascades: `validate_mapping_payload` now rejects `channel_code`, `_sync_key_for_generic`
    no longer persists it, and the auto-mappers/suggesters no longer offer it.
  - `pm_suggest_mapping.py`: removed the `channel_code` suggestion entry.
  - `product_master_workflow.validate_product_master_sync`: removed channel column detection,
    the `DimChannel` channels query, and the `unknown_channel` row validation (dead once
    channel_code isn't a target). Dropped now-unused `DimChannel` import.
  - `template_definitions.py`: removed `channel_code` from the `product_master` template
    expected_columns and the sample CSV.
  - `products.py`: removed the `channel` entry from a product's `missing_required_fields`
    (a product with no channel is normal, not incomplete).
- **Still present (intentionally, until step 2 migration):** `dim_product.channel_id` column;
  `product_import_sync.py` channel plumbing (now dormant — `channel_code` never reaches it, so
  existing values are preserved and none are written); the products read model still returns
  `channel_id`/`channel_code` and supports the channel filter/PATCH/bulk-import. These all
  reference the column, so they move together with the column-drop migration.
- **Behavior for existing jobs:** a saved mapping to `channel_code` (e.g. job 30's `bu_segment`)
  now fails fast at the mapping-payload check — `Unknown canonical target 'channel_code' for
  column 'bu_segment'` — a clear mapping-level error instead of 16k row errors. Job 30 reset to
  `validation_failed` / `pm_mapping_saved` with a remediation message.
- **Tests:** `test_product_master_workflow.py` 22 (cap test reworked to `blank_display_name`,
  no longer channel-dependent); `test_products_list_contract.py` updated (asserts `channel` NOT
  in missing_required); `test_imports_templates.py` 2 (after a transient Supabase DNS blip —
  `getaddrinfo failed`, the documented NullPool issue — unrelated to this change).
- **Real-DB confirm (Supabase `postgres`):** `channel_code in PM_CANONICAL_GENERIC == False`;
  re-validating job 30 raises the clear mapping-level rejection naming `bu_segment`. No new SQL.
- **Step 2 (NOT done — needs explicit go + Supabase restore point):** Alembic migration to drop
  `dim_product.channel_id`, plus removing the now-dead channel plumbing from `product_import_sync.py`
  and the channel filter/PATCH/bulk-import/output from `products.py`. Migration = hard stop until approved.
- **User action to clear job 30:** open mapping, remap `bu_segment` → `business_unit` (or ignore),
  re-validate.

### Jun 1, 2026 — PM validation: surface WHY it failed, unblock Back, cap detail at scale
- **Branch:** `feature/pm-specs-json-retire-eav` (not merged to main).
- **Symptom (user):** a PM import showed "Validation failed / 16836 row errors" with **no
  per-row detail**, **nothing in logs/console**, and the wizard **wouldn't let you go Back**
  to fix the mapping. Validation actually *succeeded* in the worker (~57s) — 16,836 of 17,136
  rows legitimately failed one rule.
- **Real cause (read from DB):** all 16,836 errors were `unknown_channel` — source column
  **`bu_segment`** was mapped to `channel_code`; no such channel exists, so every row failed.
- **Three problems fixed:**
  - **B (no detail shown):** PM async validation finishes in the worker; only `pm-import-state`
    was polled, and `validatePm` invalidated `import-job-rows` only at enqueue (202, before any
    rows exist). Added a `page.tsx` effect that refetches row results when status transitions
    `validate_running/queued → validated/validation_failed`. (frontend)
  - **C (can't go Back):** the wizard-realignment effect had `activeStep` in deps and re-derived
    the step on every change → `validation_failed` (=step 5) snapped you back whenever you hit
    Back. Now dedupes by server-derived step (`pmDerivedStepRef`): realigns only on real state
    transitions, never fighting manual nav. (frontend)
  - **D (opaque + unbounded):** backend `validate_product_master_sync` now (a) caps persisted
    per-row detail to `PM_VALIDATION_DETAIL_CAP_PER_CODE=50` per code, (b) emits accurate
    `code_counts` in the `pm_validation_summary` row, and (c) gives `unknown_channel` a clear
    message naming the source column + remediation. `page.tsx` renders a "What failed (grouped
    by issue)" table reading `code_counts` (true totals) with a sample per code. (backend+frontend)
- **Note:** the `page.tsx` half (B/C/D-frontend) was already in the working tree at the start of
  this turn (parallel/desktop edit); this commit completes the backend it depends on and validates
  the whole thing together.
- **Tests:** `test_product_master_workflow.py` 22 passing (+1 new: detail capped at 50/code while
  `code_counts.unknown_channel == 130` total). Web `imports/page.test.tsx` 26/26. eslint 0 errors
  on page.tsx (pre-existing exhaustive-deps warnings only). (`tsc --noEmit` has pre-existing
  project-wide AG Grid/`never` errors — project gates on eslint+vitest, not tsc.)
- **Real-DB run at true volume (Supabase `postgres`):** re-validated job 30 (17,136-row file):
  detail rows **16,836 → 53** (50 capped + 3 structural), summary `code_counts.unknown_channel =
  16836`, message points at column `bu_segment`. Job 30 stays `validation_failed` (still the wrong
  mapping) but now shows the cause. (No new SQL constructs — fewer rows into existing bulk insert.)
- **User action to clear job 30:** remap `bu_segment` off `channel_code` (ignore / staged metadata)
  and re-validate.

### May 31, 2026 — Phase 2 follow-up: cancel now revokes ALL slot tasks
- **Branch:** `feature/pm-specs-json-retire-eav` (not merged to main).
- Closes the Phase 2 known follow-up. Added `iter_slot_task_ids(meta)` to
  `import_background_slots.py`; `import_job_task_control._collect_celery_task_ids` now
  returns every registered slot's Celery task id (registry order: main → dsi_bulk → soh →
  velocity → forecasting → pm_validate → pm_commit → lineup), so cancel **revokes** all
  in-flight sub-tasks — not just main + dsi_bulk. Metadata clearing was already complete.
- Existing revoke tests unchanged (main+dsi_bulk order preserved); regression test now also
  asserts the full revoke list. `test_import_job_task_control` + `test_import_background_slots`
  + `test_background_tasks` = 20 passing.

### May 31, 2026 — Phase 2: Unify job-tracking via single slot registry (+ orphan-slot bug fix)
- **Branch:** `feature/pm-specs-json-retire-eav` (not merged to main).
- **What:** Replaced ~11 copy-pasted `staged_metadata` task-slot writers + 8 hand-coded
  discovery readers + 3 inconsistent clearers with ONE registry.
- **New module `app/services/imports/import_background_slots.py`:** `TASK_SLOTS`
  (8 `SlotDescriptor`s) + helpers `set_task_slot_on_job` / `set_task_slot_by_job_id`
  (writers), `iter_active_slots` (discovery), `clear_task_slot` / `clear_task_slot_on_job`
  / `clear_all_task_slots` (clearers), `jobs_with_possible_background_tasks` (query
  fragment), and `task_label` (moved out of background_tasks). Models the 3 slot shapes:
  fixed-kind, `main` (`celery_task_id`, bare-string, kind from template_slug), and
  `dsi_bulk_task` (kind in payload, legacy `dsi_bulk_provisional_customers` normalized to
  `dsi_bulk_provisional`). On-disk JSON shape preserved (byte-compatible; `dsi_bulk` now
  also stores `async_poll`, harmless).
- **Writers refactored to the registry:** `product_master_workflow.py` (pm_validate,
  pm_commit + clearers), `dsi_velocity_enqueue.py`, `dsi_soh_reconciliation_enqueue.py`,
  `dsi_forecasting_enqueue.py` (each: `_persist_*` delegates + **removed the duplicated
  inline write** in their `dispatch_*`), `lineup_parse_dispatch.py`, `mappings.py`
  (both `dsi_bulk_task` sites), `imports.py` (all 3 `celery_task_id` main sites).
  `background_tasks.py` discovery loop now iterates `iter_active_slots`.
- **Bug fixed (the payoff):** `import_job_background_metadata.clear_background_task_metadata`
  now clears EVERY registered slot (was only `celery_task_id` + `dsi_bulk_task`), so
  cancel/retry (`import_job_task_control`) can no longer leave orphan `pm_*`/`dsi_soh`/
  `dsi_velocity`/`dsi_forecasting`/`lineup_parse` slots the bell kept showing.
- **Known follow-up (deliberately NOT in scope):** `import_job_task_control._collect_celery_task_ids`
  still only *revokes* the main + dsi_bulk Celery tasks (metadata is now fully cleared, but
  pm_commit/validate/soh/velocity/forecasting/lineup sub-tasks are not revoked on cancel).
  Low risk (worker self-completes); extend revoke via the registry in a later pass.
- **Tests:** new `test_import_background_slots.py` (7) + new cancel-clears-all-slots
  regression in `test_import_job_task_control.py`. Focused suites green: background_tasks,
  import_job_task_control, async_broker_dispatch, product_master_workflow, dsi_job_progress,
  dsi_soh_reconciliation, lineup_parse_preview, dsi_velocity_intelligence, import_jobs_list,
  imports_templates (~72 passing).
- **Real DB validation (Supabase `postgres` via `.env`, no mocks):** registry-generated
  `has_key` discovery query executed; `list_active_import_background_tasks_sync` ran
  end-to-end; full write→flush→re-read (`iter_active_slots`)→`clear_all_task_slots`→re-read
  round-trip on a real `import_job` row, then ROLLBACK (no persistence). No new SQL
  constructs (JSONB dict writes via ORM).
- **Next:** Phase 3 (wizard componentization around the contract, static client map first,
  flag-gated per importer) — GATED behind the user's real PM core-loop re-run. Phase 4
  (Supabase write optimizations) still pending approval.

### May 31, 2026 — Phase 1: Import Flow capability contract (DESIGN ONLY, for review)
- **Branch:** `feature/pm-specs-json-retire-eav` (not merged to main).
- **Deliverable:** `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` — declarative per-importer
  flow contract (steps, needs_mapping, mapping_ui, needs_steward, steward_surface,
  apply_mode, apply_requires_confirm, archives_on_complete, import_mode_choice,
  hidden_from_generic_ui, tracking_kinds). **No code/behavior changed** — Markdown doc
  + illustrative Python/TS types only (nothing imports them).
- **Audit grounding (read-only):** wizard `page.tsx` (~3,900 LOC) branches on
  `isPm`/`isDsi`/`isShipmentEvidence` in 80+ spots with 4 hard-coded step arrays;
  job-tracking registration is copy-pasted per importer (`_persist_*_task_metadata` in
  pm_commit/pm_validate/dsi velocity/soh/forecasting/resolution-plan/lineup-parse), with
  parallel readers + clearers in `background_tasks.py`. The existing `import_template`
  row already carries a *partial* contract (`pipeline_handler`,
  `destructive_apply_requires_confirm`, `requires_provider`, …) — capability layer is
  additive on top.
- **Latent bug found (recorded, not fixed):** `import_job_background_metadata.clear_background_task_metadata`
  (used by cancel/retry) only strips `celery_task_id` + `dsi_bulk_task`, leaving orphan
  `pm_commit_task`/`pm_validate_task`/`dsi_soh_reconcile_task`/`dsi_velocity_compute_task`/
  `dsi_forecasting_task`/`lineup_parse_task` slots the feed keeps discovering. Phase 2
  (single slot registry) removes the class of bug.
- **Drift flagged:** `customer_sell_through` is DB-seeded (migration 0045) but absent from
  `template_definitions.py` and the generic wizard — open question in the doc (§9).
- **Decisions locked (user, doc §9 → D1–D5):** D1 `customer_sell_through` = its own
  surface (`hidden_from_generic_ui`, needs_steward yes, fact_upsert_after_steward, no
  confirm; UI/mode deferred to its surface design). D2 deliver contract via **static
  client map first** (documented upgrade path to a `GET /templates` `capability` field if
  the app grows). D3 TS types live in **`packages/types/`**. D4 `inbound_shipments` =
  **"4-step-with-inline-steward"**, revisit explicit mapping/validate steps in Phase 3.
  D5 §5 matrix committed **as-is** as a living doc. §10 = add-only correction log.
- **Next:** produce the Phase 2 (job-tracking unification) file-level plan for approval —
  single slot registry from the contract's `TrackingKind`/`TrackingSlot`, one shared
  register/discover/clear helper, and fix the orphan-slot bug in
  `clear_background_task_metadata`. Still awaiting the user's real Product Master import
  re-run on this branch (commit should finish in seconds, bell indicator visible, job
  stays in list) — gate before Phase 3 wizard componentization.

### May 31, 2026 — Import audit + Phase 0: PM commit job tracking (activity feed, job list, dispatch log)
- **Branch:** `feature/pm-specs-json-retire-eav` (same branch as the EAV retirement; both are PM-commit-area improvements). NOT merged to main.
- **Audit (read-only) — import drift findings:**
  - Importers: `product_master` (own endpoints + 6-step wizard, no steward — correct), `distributor_inventory`/DSI (7-step + steward), `inbound_shipments`/shipment evidence (4-step + steward panel), plus `distributor_master`/`customer_master`/`historical_lineup`/`customer_sell_through`/`current_lineup`. **Capability differences are legitimate; the drift is the lack of a shared flow contract** — each importer grew its own endpoints, wizard branch (`isPm ? … : isDsi ? …`), mapping UI, and job-tracking wiring.
  - `product_attribute_value` only PM writes product attributes; DSI/shipment/sell-through write `fact_*` tables (no PAV). So the specs_json/EAV change is PM-specific; Supabase write-optimization + job-tracking consistency are cross-cutting.
- **Phase 0 bug fixes (the 3 symptoms after switching to broker):**
  1. **No top-right activity-feed indicator for PM commit** — root cause: commit never registered a task slot in `staged_metadata` and its status is `commit_running` (not `running`), so `background_tasks.py` never discovered it. Fix: `run_pm_commit_worker` now writes a `pm_commit_task` slot (`_persist_pm_commit_task_metadata`); feed filter + `_build_background_task_records` + `_clear_task_slot_metadata` handle the `pm_commit` slot / `product_master_commit` kind (frontend already understood that kind).
  2. **Committed job vanished from job list** — root cause: commit set `job.archived_at = now()` and `/jobs` hides archived. Fix: **removed auto-archive on commit success**; a completed PM job stays visible (consistent with DSI). Archiving is now a user action only.
  3. **No Celery detail** — broker dispatch discarded the task id. Fix: capture + `logger.info(... task_id=...)` on dispatch. (Also: commit is now fast after the EAV retirement, so it can complete quickly.)
  - `job_db_indicates_pipeline_finished` now treats `pm_committed` stage and `commit_failed` status as finished so the feed clears the slot in all modes.
- **Tests:** `test_background_tasks.py` (+2: PM commit listed while running; slot cleared once `pm_committed`), `test_product_master_workflow.py`, `test_import_jobs_list.py`, `test_imports_templates.py` = 32 passing.
- **Next phases (new chat) — Phases 1–4 (design in `docs/PRODUCT_MASTER_PIM_DESIGN_BRIEF.md` + import-audit plan):** (1) define a declarative Import Flow capability contract; (2) unify job-tracking/activity-feed registration across all importers via one helper; (3) componentize the web wizard around the capability spec (flag-gated, per importer); (4) apply Supabase write optimizations (bulk writes, pooling) consistently. Gate full componentization behind proving the core loop first. Also still pending: drop existing 2M PAV rows (destructive — approval), connection pooling (`:5432` + modest pool, ECHECKOUTTIMEOUT history), `catalog_product` per-row flush → bulk, EU co-location of API+DB.



### May 31, 2026 — PM commit: retire dead EAV write, consolidate specs on dim_product.specs_json
- **Branch:** `feature/pm-specs-json-retire-eav` (NOT merged to main; for review).
- **Finding (read-only audit):** `product_attribute_value` (~2M rows / 286MB on Supabase) is **write-only** — referenced only in its model, the migration, and the commit *write* path; **zero readers** (no endpoint/read-model/frontend). `catalog_product` **is** read (products endpoint joins it for `last_import_date`). `dim_product.specs_json` (JSONB) **is** the live, read spec store (products grid `specs_flat`/`specs_preview` + commercial planner `product_specs_from_json`/`specs_json_flat_string_map`), and already merges `specs_json.import_staging`.
- **Change (additive, flag-gated, reversible):**
  - Commit now routes **both** `stage_raw` → `specs_json.import_staging` **and** `attribute_candidate` → `specs_json.attribute_candidates` (distinct key so steward review can still distinguish). All dispositioned file columns land in the canonical, read JSONB store.
  - `commit_catalog_and_eav(..., write_attribute_values=False)` — **skips** the legacy PAV write by default (no attr-def creation, no PAV rows); still upserts `catalog_product`. Gated by new setting `pm_write_legacy_eav` (env `PM_WRITE_LEGACY_EAV`, default off) as a reversible escape hatch.
  - `read_model._flatten_specs_json` now flattens `attribute_candidates` (like `import_staging`) so those columns surface as optional grid columns / planner specs; container keys excluded from `specs_flat` + `_compact_specs_preview`.
- **Impact:** PM commit stops writing ~1 row per (product × attribute) — commit drops from minutes to seconds, 286MB stops growing — with zero reader impact (PAV had none). Existing 2M PAV rows are **left in place** (dropping them is destructive — needs explicit approval).
- **Not done (next, explicit approval / careful validation):** drop/retire existing `product_attribute_value` data; connection pooling fix (session pooler `:5432` + modest pool — note prior **ECHECKOUTTIMEOUT** history, validate carefully); `catalog_product` per-row `flush()` → bulk `INSERT…ON CONFLICT`; deployment co-location (API next to DB in EU) as the biggest latency lever; full PIM/category-template model.
- **Tests:** `test_product_master_workflow.py` (21) + `test_commercial_planner_api.py` + `test_products_list_contract.py` = 98 passing. New: EAV-gating (skips PAV by default, writes when flag on), `attribute_candidates` routing into specs_json, and specs_flat surfacing. No new SQL constructs introduced (logic-only change). Real end-to-end import re-run recommended as final confirmation.



### May 31, 2026 — PM commit cast fix; project rules updated with SQL validation rule
- **PM commit `DatatypeMismatch: CASE types integer and text`:** `_merge_select()` in `product_import_sync.py` used `opt_str` (designed for string columns) for `channel_id` (Integer), `launch_date` (Date), and `retired_date` (Date). psycopg3 sends Python `None` as a typeless NULL; PostgreSQL defaults untyped NULLs to `text`; CASE expression trying to unify `text` (staging) with `integer`/`date` (ORM column) → `DatatypeMismatch`. Fix: `cast(st.c.channel_id, Integer)`, `cast(st.c.launch_date, Date)`, `cast(st.c.retired_date, Date)` in the CASE branches.
- **Project rules updated:** Added `psycopg3 typeless NULLs in VALUES clause` to Known Gotchas. Added "SQL Validation Rule" section: any task writing custom SQL constructs (VALUES clauses, CASE expressions, bulk INSERT/SELECT from staging) must run at minimum one real end-to-end execution against the actual DB before declaring done. Mock-only tests are not sufficient proof for SQL correctness.

### May 31, 2026 — PM commit crash fixed; dev process kill hardened
- **PM commit crash (`Wrong number of elements for 36-tuple`):** `_staging_tuple()` in `product_import_sync.py` was spreading `str_dim_flags` (`list[tuple[bool,str|None]]`) with `*str_dim_flags`, producing 26 elements instead of 36. Fixed to `*(item for pair in str_dim_flags for item in pair)` — flattens 10 pairs → 20 scalars → 36 total. Known gotcha now resolved.
- **PM commit error quality:** `commit_product_master_sync` `except Exception` now raises `ValueError(f"Product commit failed: {msg[:500]}")` instead of a generic placeholder. `job.error_summary` now contains the real error (e.g. `ArgumentError: Wrong number of elements…`) not "See import row results for details."
- **PM commit row results at step 6:** `page.tsx` commit step now renders the `previewRows` table when `commit_failed`, so the user sees the `product_commit_db_error` row result inline without navigating back to the review step.
- **Dev process kill hardened:**
  - `stop-dev.ps1`: adds `Stop-ProcessTree` (kills PID + all descendants recursively); reads `.cip-dev-pids/*.pid` files and kills trees first; port sweep second; WMI name+path sweep third; removes non-existent `celery.exe` from `$procNames`; extends wait to 5s; verifies ports 8001/3000 are free after kill and warns if not.
  - `restart-dev.ps1`: writes each spawned window PID to `.cip-dev-pids/<service>-window.pid`; clears PID dir on each restart.
  - `dev-api.js` / `dev-worker.js` / `dev-web.js`: each writes `process.pid` to `.cip-dev-pids/<service>.pid` on start and deletes it on exit/SIGTERM/SIGINT.
  - `.cip-dev-pids/` added to `.gitignore`.

### May 31, 2026 — Bulk delete SQL proof: 2 statements (not 21); confirm timeout → 504
- **Measured (real session, Supabase `postgres` via `.env`, no mocks):** `preview_master_bulk_delete` for 3 customers = **2** cursor executes (1 `UNION ALL` reference check + 1 label `SELECT IN`), **~3.6s**. `customer_hard_reference_breakdown_batch` alone = **1** execute.
- **Instrumentation:** `db_sql_counter.py` (`before_cursor_execute` on engine); bulk-delete customer routes return `X-CIP-SQL-Count` + log `bulk_delete_sql_probe statements=N`. Script: `apps/api/scripts/measure_bulk_delete_sql.py`.
- **If :8001 still ~24–30s with empty `X-CIP-SQL-Count`:** stale uvicorn process (pre-union code). Restart API (`pnpm dev:api` / `stop-dev.ps1`); header should show `2`.
- **Confirm:** `OperationalError` / SQLSTATE `57014` (statement_timeout) → `MasterBulkDeleteTimeoutError` → HTTP **504** with `error: statement_timeout`. FK `IntegrityError` still → **409** with `references`. Confirm logs `exc_type=...` on failure.
- **Tests:** `test_master_bulk_delete_sql_integration.py` (real `AsyncSessionLocal`, asserts `counter.count == 2`); 25/25 bulk-delete tests passing with `ALLOW_TESTS_ON_DEV_DB=1`.

### May 31, 2026 — Customer bulk delete: DSI staging blockers, confirm 409, dev port kill
- **Reference matrix:** `import_distributor_si_staging_line.resolved_customer_id` is in customer `_SPECS` (`DSI_STAGING_REF_LABEL`); `customer_source_token_alias` remains a **preview blocker** (not auto-deleted as child — explicit bulk delete before `dim_customer` for session consistency; DB also CASCADE).
- **Confirm:** Restored batched `_batch_refs` re-check when `deletable_ids` is sent (1 UNION ALL query) — blocks stale preview (e.g. CUST-1001 + 11 DSI staging rows). `is_db_integrity_error()` maps asyncpg/sqlalchemy FK violations to `MasterBulkDeleteIntegrityError` → HTTP **409** with `references`, not 500.
- **Preview perf:** UNION ALL uses homogenized `cnt` types (`BigInteger`) and `row._mapping` parsing; tests assert **1** `db.execute` per breakdown and **1** `_batch_refs` call for 6 customers (2 queries total for preview).
- **Dev restart:** `scripts/stop-dev.ps1` uses `Get-NetTCPConnection` for ports 8001/3000/5555; `scripts/dev-api.js` kills stale CIP API on :8001 when OpenAPI matches, then starts uvicorn.
- **Tests:** 20/20 in `test_customer_bulk_delete_staging_block.py` + `test_master_entity_bulk_delete.py`.

### May 31, 2026 — Master delete: UNION ALL reference checks, no NameError, no redundant re-check
- **Bug fix:** `customer_usage.py` was missing `from sqlalchemy import func` → `NameError` at runtime → bulk delete 500. Added `func` (and `literal`, `Select`) to imports.
- **Performance:** All six `*_usage.py` reference checks now execute as a **single UNION ALL query** (one network round trip) instead of 19–25 sequential awaited queries. Before: ~2s × 21 queries ≈ 42 s. After: 1 round trip (~1–3 s for the UNION).
- **Architecture:** New `count_subquery_for_columns(label, columns, ids)` + `batch_counts_multi_table(db, subqueries, ids)` utilities in `master_usage_batch.py`. Multi-column tables (roadmap product_id + replacement_candidate_id, lineup 3 roles) are aggregated via an inner `UNION ALL` subquery — one entry per entity, not one per column.
- **Confirm path:** When `deletable_ids` is provided from the preview, the full reference re-check is skipped. A single `_batch_entity_labels` batch SELECT replaces the old `_batch_refs` (21 queries) + per-entity label loop (N queries). Preview cost: 2 queries. Confirm cost: 1 query (existence) + delete operations.
- **Children deletes:** `delete_customer_children` and `delete_distributor_children` now use bulk `DELETE WHERE customer_id = ?` SQL instead of per-row ORM deletes.
- **Exception safety:** `raise_bulk_delete_http_error` now handles all exception types (not just `ValueError`/`MasterBulkDeleteIntegrityError`) and always raises `HTTPException`. All confirm endpoints use `except Exception`.
- **Tests:** 12/12 passing; patches retargeted from `_batch_refs`/`batch_counts_for_column` to `_batch_entity_labels`/`batch_counts_multi_table`.
- **Modules changed:** `master_usage_batch.py`, `customer_usage.py`, `product_usage.py`, `distributor_usage.py`, `channel_usage.py`, `region_usage.py`, `master_entity_bulk_delete.py`, `master_bulk_delete_http.py`, endpoints: `customers`, `products`, `distributors`, `catalog`.

### May 30, 2026 — Product Master staging: file is source of truth (no row JSONB blob)
- **Validate** no longer builds or persists per-row `staged_metadata` maps (`"0"`…`"17135"` keys). Stores scalar `pm_staged_row_count` only; `pm_validate_task` and other import-type slots in the same JSONB column are unchanged.
- **Commit** re-reads the uploaded file and derives `stage_raw` values into `specs_json.import_staging` and catalog `row_staged_snapshot`; `dim_product` / `catalog_product` / PAV use chunked IN batch loads (no per-row `SELECT` by SKU).
- **GET …/product-master/jobs/{id}/state** returns `staged_row_count` instead of the full `staged_metadata_preview` blob (stops polling multi‑MB JSON every few seconds).
- **Module:** `app/services/imports/pm_staging.py` (shared helpers).

## Branch
`cursor/commercial-planner-program-84b1` (Commercial Planner program phases 1–2 complete)

### May 30, 2026 — Commercial Planner program (phases 2 complete)
- **Celery:** `commercial_planner.parse_lineup_case`; parse-upload/apply returns **202** when file ≥512KB or ≥500 preview rows; activity feed `lineup_parse_task`.
- **Intelligence:** Candidate product union; customer-scoped `FactForecast`; budget request + buy plan signals; ranking snapshots (in-process POST/GET).
- **Steward:** `GET …/lineup-cases/{id}/steward-export`; web **Steward export** download on case workbench.
- **Dashboard:** `kpis.commercial_planner` on `GET /dashboard/summary`; web KPI when flag on.
- **Modularity:** `commercial_planner_auth.py`, `commercial_planner_lineup_routes.py`, `commercial_planner_intelligence_routes.py`, `plan_readiness.py`, `lineup_parse_api.py`.
- **Tests:** API 90 CP tests; web 91 CP tests passing.

### May 30, 2026 — Commercial Planner program (phase 1 finish + QA)
- **Flag:** `CIP_COMMERCIAL_PLANNER_ENABLED` / `NEXT_PUBLIC_CIP_COMMERCIAL_PLANNER_ENABLED` (default on).
- **Lineup:** preview → apply on retry parse and **create-case** dialog; `can_apply` requires ≥1 resolved product.
- **Intelligence:** rankings use sellout, forecast, lineup MSRP, customer net price, promo plan; returns `suggested_srp_local`; intelligent add uses it.
- **Suggestions:** Prefer current `CommercialLineupCase` on plan before historical lineup job.
- **Docs:** `docs/COMMERCIAL_PLANNER_PROGRAM.md`, **`docs/COMMERCIAL_PLANNER_GAP_ANALYSIS.md`** (risks, gaps, test matrix).
- **Tests:** API 13 focused + 74 route tests; web 91 CP tests (page + CurrentLineupSection + autocomplete). DB bootstrap test needs Postgres.
- **Deferred:** Celery parse task (`lineup_parse_worker.py` scaffold only), router split, dashboard widgets, steward mapping bridge.

### May 30, 2026 — Commercial Planner program (phase 1 initial)
- **Flag:** `CIP_COMMERCIAL_PLANNER_ENABLED` / `NEXT_PUBLIC_CIP_COMMERCIAL_PLANNER_ENABLED` (default on).
- **Lineup:** `POST …/parse-preview` + `POST …/parse-apply?confirm=true`; upload dialog uses preview then apply.
- **Intelligence:** `GET …/plans/{id}/intelligence/customer/{cid}/product-rankings`; web **Intelligent add** dialog.
- **Suggestions:** Prefer current `CommercialLineupCase` lines on plan before historical lineup job.
- **Docs:** `docs/COMMERCIAL_PLANNER_PROGRAM.md`
- **Tests:** `test_commercial_planner_intelligence.py`, `test_lineup_parse_preview.py`

### May 30, 2026 — Master bulk delete: complete FK checks, batched preview, 409 on confirm
- **Fix:** Extended `customer_usage` / `product_usage` / `distributor_usage` / `channel_usage` / `region_usage` with staging lines, token aliases, mapping candidates, catalog links, etc.
- **Performance:** `*_hard_reference_breakdown_batch` + `master_usage_batch.py`; preview no longer N×15 queries per id.
- **Confirm:** Body `{ entity_ids, deletable_ids? }`; skips full re-preview when `deletable_ids` sent; batched recheck; `IntegrityError` → 409 with `references` (all-or-nothing).
- **Web:** Confirm passes `deletable_ids`; `MasterBulkDeleteImpactDialog` shows 409 reference detail; `apiPost` raises `HttpConflictError` on 409.
- **Docs:** `docs/MASTER_BULK_DELETE_AUDIT.md`
- **Tests:** `test_master_entity_bulk_delete.py`, `test_customer_bulk_delete_staging_block.py`, `MasterBulkDeleteImpactDialog.test.tsx` (14 API + 3 web passing).

## Branch (prior)
`main` (merged `feat/master-delete-reference-checks-bulk`)

## Head commit
`d004264` on `main` (feature: `448ee1d` — channels/regions admin grids, distributor bulk delete, premium nav)

### May 29, 2026 — Master data admin grids, bulk delete, premium nav
- **Merge:** `feat/master-delete-reference-checks-bulk` → `main` (reference-check delete + customers/products bulk delete).
- **Channels & Regions:** `GET/DELETE` + bulk preview/confirm on `catalog.py`; admin page `/admin/channels-regions` with `CatalogDimensionGridPanel` (row delete 409 alerts, `BulkSelectionToolbar`, `MasterBulkDeleteImpactDialog`).
- **Distributors:** bulk preview/confirm API + `BulkSelectionToolbar` on distributor master grid (mirrors customers/products).
- **Nav (shell only):** `navConfig.ts` + `AppShell.tsx` — grouped IA (Overview → Admin), collapsible groups, icon rail + flyout when collapsed, `cip.shell.nav.collapsed.v1` + `cip.shell.nav.groupExpanded.v1` in localStorage. No route/page file changes except new `channels-regions` page.
- **Tests:** `test_master_entity_bulk_delete.py` extended for channels/regions/distributors bulk preview routes.

### May 30, 2026 — Master delete reference checks + bulk delete
- **Reference-check delete** (mirrors `product_usage.py`): `customer_usage`, `distributor_usage`, `channel_usage`, `region_usage`, `customer_location_usage` + structured 409 + GET refs on API.
- **UI:** Customers + Products admin grids: row-delete conflict alerts; Distributors row-delete alert; customer location delete alert in drawer.
- **Bulk delete:** `BulkSelectionToolbar` + `MasterBulkDeleteImpactDialog` on **Admin → Customers** and **Admin → Products**; `POST …/bulk-delete-preview` and `…/bulk-delete-confirm` (skips blocked rows, deletes deletable only).
- **Catalog API:** `DELETE /catalog/channels/{id}`, `DELETE /catalog/regions/{id}` with reference breakdown (no dedicated channel/region admin grid yet).
- **Tests:** `test_customers_delete.py`, `test_master_entity_bulk_delete.py`, `MasterBulkDeleteImpactDialog.test.tsx` (+ existing `test_products_delete.py`).

## Alembic Head
`20260518_0045` — Customer sell-through Phase 0 (`fact_customer_sellthrough`, staging, `customer_report_config`, template seed). Prior: `0043` `fact_dsi_forecast`, `0042` `fact_customer_velocity`. Smoke: **`cip_alembic_smoke`** at `0045`.

## Current State
- **Local dev:** Windows, **no Docker**; Supabase `cip` via `DATABASE_URL` transaction pooler `:6543` + `NullPool` (`app/db/session.py`).
- **Redis:** Celery requires `127.0.0.1:6379` from Windows; WSL-only ping is not enough. Fallback: `CIP_DEV_CELERY_DISPATCH=in_process_thread` in `apps/api/.env`.
- **`stop-dev.ps1` / `restart-dev.ps1`:** fixed `$pid` bug; restart waits for Redis on Windows.

### May 30, 2026 — Dev reliability + PM imports (local, pending commit)
| Area | Before | After |
|------|--------|--------|
| `stop-dev.ps1` | Crashed on `$pid`; orphans on :8001/:3000 | Kills listeners + repo-scoped processes |
| `restart-dev.ps1` | Windows could not see Redis; windows closed on error | Waits for `:6379`; error + Enter on failure |
| PM `validate_running` stuck | Jobs hung after dead worker (e.g. job #4) | `reconcile_stale_pm_validate_sync` (30 min) on GET `/state`, enqueue, worker |
| PM GET `/state` payload | ~100KB+ inferred samples every poll | `inferred_schema_for_state_payload` trims samples (mapping UI unchanged) |
| Imports jobs grid | Full “Loading data…” on refetch | Spinner only when `jobs == null` |
| New PM wizard | Stale `lastJobId` could confuse steps | Cleared when picking a new import type |

**Tests run:** `test_product_master_workflow.py` 18/18; `test_ai_resolver_integration.py` 16/16; `imports/page.test.tsx` 26/26. Full `pnpm test:web` has unrelated failures/timeouts elsewhere.

**AI:** `AI_ASSIST_ENABLED=false` locally → Anthropic not called; package installed.

---

## Latest work (May 2026) — Product Master validation at scale

### Backend
- **`validate_product_master_sync`**: row-level `ImportRowResult` rows collected in memory, flushed via **`insert(ImportRowResult)` in 2k chunks** (replaces ~14k individual `db.add()` + one flush).
- **Celery task** `imports.product_master_validate` → `product_master_validate_task` / `run_product_master_validate_job` / `run_pm_validate_worker`.
- **POST `/api/v1/imports/product-master/jobs/{id}/validate`**: returns **202** with `pm_validate.outcome=enqueued` when dispatched; polls via existing **GET …/state**.
- **Activity bell**: `staged_metadata.pm_validate_task` slot (`kind: product_master_validate`) in `background_tasks.py`.
- **DB pools** (Supabase): async **`NullPool`** + `statement_cache_size=0` (`c4a8cf9`); sync `prepare_threshold=None`.

### Web
- PM validate mutation accepts **202**; polls state while `validate_queued` / `validate_running`.
- **`?job=N` resume** for PM: steps 3–6 from `stage` / `status` (no read-only stub).
- **Next.js proxy**: `AbortSignal.timeout(600_000)` for validate/commit/apply POST paths.

### Tests
- `tests/test_product_master_workflow.py` — bulk insert assertion (`db.execute`); `from_worker=True` in staged-metadata test.
- `tests/test_async_broker_dispatch.py` — validate job dispatch helper.

### PM mapping (same release train)
- PgBouncer `statement_cache_size=0` on async engine; PM SKU aliases / mapping UI (`4ba9529`, `224e886`, `8868d0b`).
- Imports UI error banners for PM state / jobs list; stale `?job=` redirect on 404.

---

## Latest work (May 2026) — Customer Sell-Through Phase 0

### Foundation
- fact_customer_sellthrough: grain
  (customer_id, customer_location_id nullable,
   product_id, period_start_date)
  period_type: 'daily' | 'weekly' | 'monthly'
  daily supported in schema for future API connectors
  raw_mtd_units + is_mtd_estimate for FNB MTD pattern
  unit_cost and unit_sell_price captured where present
  reported_soh captured from customer files
- import_customer_sellthrough_staging_line: mirrors DSI
  staging pattern, no resolution plan layer
- customer_report_config: per-customer cadence, structure
  type, overdue threshold, last received date
- import_template seeded: slug=customer_sell_through
  column aliases cover all 7 confirmed retailers
- Pipeline handler skeleton: dispatches on 5 structure
  types (flat/pivoted/multi_sheet/mtd_delta/wide_extract)
  All parsers raise NotImplementedError — Phase 1
- Store-level FK: customer_location.id (existing table)
  nullable for chain-level reports
- Migrations: 0044 (fact table), 0045 (staging + config
  + template seed)
- Smoke migration: 0044+0045 applied on cip_alembic_smoke

### Retailers and structure types
- flat:         Evetech, Takealot
- pivoted:      Game, Makro
- multi_sheet:  Computer Mania
- mtd_delta:    FNB (cumulative MTD → weekly delta)
- wide_extract: IC / Incredible Connections (197 cols)

### Phase 1a — Flat parser
- `parsers/customer_sell_through_flat.py` — `parse_flat_report()` →
  `ParseResult` (no DB, isolated)
- No retailer-specific logic — works for any flat source
- Header detection: best-match scan across first 10 rows
- Column mapping: `field_mapping` first, aliases fallback
- Period extraction: date column → filename date range → filename
  date → week number → None + warning
- Formula/apostrophe normalisation on all text fields
- Rows skipped if product token or `units_sold` missing
- `customer_sell_through_apply.py`: upsert resolved staging lines to
  `fact_customer_sellthrough`
- `customer_report_config.last_report_received` updated on flat import
- Fixtures: `tests/fixtures/customer_reports/` (generic synthetic xlsx)

### Phase 1b-1e — All parsers + AI resolver layer

#### Parsers (all generic, no retailer-specific logic)
- `pivoted`: period columns detected by pattern, auto-unpivot, SOH on latest period only
- `multi_sheet`: all data sheets processed, summary sheets excluded, chronological order
- `mtd_delta`: prior week lookup from staging, `derived_units = current - prior`,
  `is_mtd_estimate` flag when no prior exists
- `wide_extract`: header-first streaming, 500-row chunks, falls back to pivoted unpivot
  if period cols found

#### AI resolver layer (`ai_import_resolver.py`)
- Gated behind `AI_ASSIST_ENABLED` env var (default False)
- `suggest_column_mapping`: first-time format classification
- `suggest_token_resolution`: unresolved token matching — auto_resolved ≥ 0.90 confidence,
  `ai_suggested` below
- `detect_format_drift`: set comparison + AI for partial drift
- Generic — works across all import types
- AI failure never breaks import — always falls back

  #### Testing
  - `AI_ASSIST_ENABLED=false`: deterministic only (default)
  - `AI_ASSIST_ENABLED=true`: AI layer active
  - All AI calls mocked in `test_customer_sellthrough_parsers.py`

### AI resolver wired into existing import handlers

Handlers updated (surgical additions only):
- `product_master` (workflow commit): token + description matching fallback
- `customer_master` (pipeline): FK code resolution for region/channel/preferred distributor
- `distributor_master`: no unresolved-token path (direct upsert by code)
- `distributor_sales_inventory`: product/customer/distributor AI after deterministic + format drift
- `shipment_evidence_import`: product/distributor AI + format drift

Pattern: deterministic first, AI only on failure. Confidence >= 0.90 → auto-apply ID.
Below 0.90 → `ai_suggested` diagnostic on staging/shipment payload. AI failure graceful.
`AI_ASSIST_ENABLED=false` → zero AI calls (default). Shared helpers: `ai_resolver_wiring.py`.

### Phase 1 (remaining — non-parser)
- Missing data coverage grid
- Multi-file bulk upload panel (frontend)

### Phase 2 (after Phase 1 validated)
- SOH derivation service (chain level:
  Σ DSI sell-out − Σ sell-through)
- Cost derivation from DSI purchase history
- Sales price fallback chain
- Coverage alerts in Channel Operations
- Customer sell-through velocity

### Phase 3 (future)
- API connectors (Amazon SP-API, distributor APIs)
  daily data slots into fact_customer_sellthrough
  via period_type = 'daily' unchanged
- Inter-customer stock movement tracking
- KPI system

---

## Latest work (May 2026) — Phase 5 Channel Operations page

- Extended existing sell-out page into Channel Operations
- Intelligence depth toggle: Raw|Operational|Strategic|Forecast
  persisted in localStorage `cip_intel_depth`, default Operational
- Four tabs: Overview (charts + KPIs + banners), Sell-out
  (existing page preserved as tab), Inventory, Movements
- Backend: GET `/channel-ops/summary|sell-out|inventory|movements|forecasts`
  registered in router
- Reads: `fact_sales_sellout`, `fact_inventory_distributor`,
  `fact_inventory_reconciliation`, `fact_customer_velocity`,
  `fact_dsi_forecast`, `shipment_evidence_line` (`ShipmentEvidenceLine`)
- `fact_dsi_forecast` only — `fact_forecast` never touched
- All tabs handle empty tables and missing distributor
  gracefully with informative states not blank screens

---

## Latest work (May 2026) — DSI Phase 3 + Phase 4

### Phase 3 — Velocity learning
- Migration 20260518_0042: fact_customer_velocity
  Grain: (distributor_id, product_id, customer_id) —
  one current row per combination, updated each apply.
  computed_through_date = max(transaction_date) from
  fact_sales_sellout — exact source date, no rounding.
  Windows: velocity_4wk (28d), velocity_13wk (91d),
  velocity_52wk (364d). model_confidence: high/medium/low
  based on distinct weeks of history.
  seasonal_index = 1.0 when < 2 calendar years available.
  is_promotional_period always False until CPOR module built.
- dsi_velocity_intelligence.py: compute_distributor_velocity
- dsi_velocity_sync.py: run_dsi_velocity_compute_sync
  chains to dsi_forecasting_enqueue on completion
- dsi_velocity_enqueue.py: mirrors soh enqueue pattern
  Celery task: imports.dsi_velocity_compute
  Activity bell kind: dsi_velocity_compute
  Payload: { distributor_id } — no date, computes from max
- Dispatch: dsi_apply_completion.py dispatches SOH and
  velocity in parallel after apply completion
- dsi_import_state_awareness.py: fixed week_start_date →
  COUNT(DISTINCT DATE_TRUNC('week', computed_through_date))
- Tests: tests/test_dsi_velocity_intelligence.py — 9 passed

### Phase 4 — DSI forecasting
- Migration 20260518_0043: fact_dsi_forecast (new table)
  DO NOT confuse with fact_forecast (Commercial Planner)
  Grain: (distributor_id, product_id, forecast_date)
  forecast_date = future date being forecast, not a period.
  Formula: velocity_52wk * seasonal_index
  Confidence band from 4wk/52wk variance ratio.
  lower_band floored at 0.
  Only medium/high confidence velocity rows feed forecasts.
  Skips products with null or zero velocity_52wk.
- dsi_forecasting.py: generate_distributor_forecasts
  weeks_ahead=13 default
- dsi_forecasting_sync.py: run_dsi_forecasting_sync
- dsi_forecasting_enqueue.py: mirrors soh enqueue pattern
  Celery task: imports.dsi_forecasting
  Activity bell kind: dsi_forecasting
  Payload: { distributor_id }
- Chained from velocity sync after velocity commits
- Tests: tests/test_dsi_forecasting.py — 7 passed

### Migrations applied
- 20260518_0042 + 20260518_0043 applied on cip_alembic_smoke
- NOT yet applied on cip — pending approval

### Task chain (post-apply)
  dsi_apply_completion
    → Task 2: imports.dsi_soh_reconciliation (parallel)
    → Task 3: imports.dsi_velocity_compute (parallel)
      → Task 4: imports.dsi_forecasting (chained from Task 3)

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

### Bug fixes (May 2026)
- **intelligence_state JSONB persistence:** `flag_modified` on `staged_metadata` writes and re-persist at end of validate so Celery validate commits retain `intelligence_state` (`dsi_import_state_awareness.py`, `distributor_sales_inventory.py`).
- **Post-apply loaded + SOH dispatch:** `POST /jobs/{id}/dsi-apply` calls `complete_dsi_import_job_to_loaded` so jobs reach `loaded` and `dsi_soh_reconciliation` dispatches (`imports.py` → `dsi_apply_completion.py`).

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

## Next (PM validation)

- Smoke PM validate on Supabase with 14k+ row file (worker + bell + state poll).
- Restart API + worker after deploy.

---

### Jun 5, 2026 — Unit B: CST steward backend (commit B on `fix/shipment-steward-performance`)

**What shipped (BACKLOG-022 + BACKLOG-025 + CST steward backend):**

| Area | File(s) | What changed |
|------|---------|--------------|
| **Dispatch extraction** (BACKLOG-022) | `app/services/imports/import_dispatch.py` (NEW) | `enqueue_import_worker_task(job_id, *, task_name, log_label, in_process_thread_name, sync_work) → (bool, str\|None)` extracted from `imports.py`. Third caller (CST apply) triggered extraction. |
| **Dispatch delegation** | `app/api/v1/endpoints/imports.py` | `_enqueue_import_worker_task` now delegates to `import_dispatch.enqueue_import_worker_task`. |
| **Dispatch delegation** | `app/api/v1/endpoints/shipment_evidence.py` | `_dispatch_shipment_apply` now delegates to same helper. Removed now-unused `threading`, `get_settings`, `DEV_CELERY_LOGGER` imports. |
| **Async `/process`** (BACKLOG-025 part A) | `app/api/v1/endpoints/imports.py` | `POST /jobs/{id}/process` now enqueues `imports.process_job` via `_enqueue_import_pipeline_job`; returns `{async: bool, task_id: str\|None, job_id: int}`. Was inline-sync. No frontend caller existed — no breaking change. |
| **CST candidates service** | `app/services/imports/cst_mapping_candidates.py` (NEW) | `upsert_cst_mapping_candidates(db, job_id)` — aggregates unresolved staging tokens into `ImportEntityMappingCandidate` (entity types `cst_product_token`, `cst_location_token`). Preserves terminal-status rows (steward resolutions survive re-runs). Cleans stale `needs_review` rows. `load_resolved_cst_candidates(db, job_id) → (product_map, location_map)` for apply-pass re-application. `list_cst_mapping_candidates_sync`, `cst_mapping_state_dict`, `_serialize_cst_candidate`. |
| **CST endpoints** | `app/api/v1/endpoints/imports.py` | Added `GET /jobs/{id}/cst-mapping-state` + `GET /jobs/{id}/cst-candidates` (paginated, filterable by `entity`/`status`). |
| **CST staging → candidates** | `app/services/imports/customer_sell_through.py` | Both `_handle_flat` and `_ingest_parse_result` now: (1) load resolved candidates before the row loop; (2) apply candidate resolutions as last fallback after deterministic+AI resolution; (3) call `upsert_cst_mapping_candidates` after `db.flush()`. |
| **Pipeline stage fix** | `app/ingestion/pipeline.py` | CST `import_mode=apply` + no errors → `STAGE_LOADED` (was `STAGE_VALIDATED` unconditionally — bug). |

**Design decisions:**
- Reused `ImportEntityMappingCandidate` — all existing reads filter by `entity_type`, so CST rows don't contaminate DSI/shipment queries.
- Preserved `ImportEntityMappingCandidate` rows with terminal status on re-runs (mirrors DSI's `preserved_candidate_steward` dict pattern). Only `needs_review` candidates are updated/deleted.
- Candidate resolution applied inline in the creation loop (load once before loop, not per-row query).
- Normalizer keys: product uses existing `_product_token_key` (`.strip().lower()`); location uses same pattern via `_location_token_key`.
- CST mutations (resolve-product, resolve-location, ignore) deferred to Unit C (no browser consumer yet).

**Headless proof:**
- `GET /jobs/{id}/cst-mapping-state` and `GET /jobs/{id}/cst-candidates` routes registered (verified via `router.routes`).
- 17 new unit tests in `tests/test_cst_mapping_candidates.py` — 17/17 pass.
- Full CST test suite: 53 pass, 4 pre-existing failures unchanged (file-not-found mocking issue in `test_customer_sell_through_foundation.py`).
- All 6 modified modules pass AST syntax check.
- Browser acceptance (apply round-trip, candidates populated in UI): pending (Unit C).

**BACKLOG updated:** BACKLOG-022 → Done; BACKLOG-025 → Done (part A); part B (frontend progress panel for CST apply) deferred to Unit C.

**Next:** Unit C — CST web surface (`CanonicalColumnMappingPanel` + `ImportStewardCandidateWorkspace` + async apply with progress).
