# Backlog — intentionally deferred work

**Scope:** Intentionally deferred / future work. Each entry has a **trigger condition** for when to resume. Distinct from `CONTEXT.md` (completed history and current branch state).

**Entry template:** ID + title · status/parked-date · effort · the idea · why it matters (and why deferrable) · what the work is · regression traps / hard constraints · behavior to retain · out-of-scope · **TRIGGER**

---

## BACKLOG-001 — Shipment steward panel → shared `ImportStewardCandidateWorkspace` (adapter swap)

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-01 (post `fix/shipment-steward-performance` audit) |
| **Effort** | Large (web); adapter + tests; no API contract change if done correctly |
| **Source** | Read-only swap audit (conversation); `apps/web/src/features/import-steward/dsi-mapping-steward-panel.tsx` (lines 94–97); `useInboundEvidenceMappingCandidatesListModel.ts` (lines 11–13); `inboundEvidenceMappingCandidates.domain.ts` (lines 7–8) |
| **Idea** | Replace the monolithic `ShipmentEntityStewardPanel` list shell with `ImportStewardCandidateWorkspace`, wired through a shipment-specific section adapter (pattern: `DsiImportJobResolutionSection`), while keeping all steward mutations on **shipment-evidence** endpoints. |
| **Why it matters / deferrable** | Reduces ~1,900-line duplication and aligns shipment with DSI list UX; deferrable until Phase 1 steward perf (debounce, bulk-map modal, invalidate-only) and Phase 2 batching (`b8ccfd0`) are merged and stable. |
| **What the work is** | (1) `ShipmentImportJobResolutionSection` (or equivalent) composing `ImportStewardCandidateWorkspace` + `useInboundEvidenceMappingCandidatesListModel` + `buildInboundEvidenceMappingCandidateColumns`. (2) Shipment-only bulk/single-row dialogs and mutations (map, provisional, bulk-map, bulk-provisional, apply-plans, special-category, reject). (3) **Do not** drop in `DsiMappingStewardPanel` or `useDsiBulkSteward` wholesale. |
| **Regression traps** | Wrong API family (`/api/v1/mappings/...` bypasses Phase 2 shipment batching); entity types (`shipment_distributor` / `shipment_customer_token` ≠ DSI tokens); losing 300ms search debounce, bulk-map “Mapping N…”, in-modal errors; double `refetch` after `invalidate`; `steward_rejected` terminal handling. |
| **Behavior to retain** | All `POST /api/v1/shipment-evidence/import-candidates/...` paths including `bulk-map-customer`, `bulk-create-provisional-customers`, `bulk-apply-confirmed-plans`; governance (no auto-create masters); `created_from_import_job_id` on aliases; resolution/scoring/enrichment logic unchanged. |
| **Out of scope** | DSI product resolve, duplicate-review, open-channel, ignore bulk, resolution-plan toolbar, region/channel tab, paginated DSI candidate API. |
| **TRIGGER** | `fix/shipment-steward-performance` merged to `main` and Warren signs off steward perf smoke; then a dedicated “shipment steward workspace swap” task is approved. |

---

## BACKLOG-002 — Phase 4: Supabase connection pooling (`:5432` session pooler + modest pool)

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-05-31 |
| **Effort** | Medium–large (config + validation across API/worker/Celery) |
| **Source** | `CONTEXT.md` (Jun 1 validate perf “Remaining”; May 31 PM EAV “Not done”; May 31 import audit “Phase 4 … pending approval”); `docs/PRODUCT_MASTER_PIM_DESIGN_BRIEF.md` (§1 NullPool / `:5432` session pooler recommendation) |
| **Idea** | Move async engine from `NullPool` + transaction pooler `:6543` to session pooler `:5432` with a modest connection pool so requests reuse connections. |
| **Why / deferrable** | Biggest cross-importer latency lever after query batching; deferrable until correctness path is stable and pooling change can be validated without `ECHECKOUTTIMEOUT` regressions. |
| **What the work is** | Update `DATABASE_URL` / `app/db/session.py` pool settings; keep `statement_cache_size=0` / `prepare_threshold` fixes; load-test validate, steward, PM commit; document revert to NullPool. |
| **Regression traps** | Prior **ECHECKOUTTIMEOUT** history; `DuplicatePreparedStatementError` on wrong pooler; Celery worker + API must share compatible config. |
| **Behavior to retain** | Correctness on Supabase; ability to revert to NullPool quickly. |
| **Out of scope** | Changing business logic; schema migrations. |
| **TRIGGER** | Explicit approval to change DB connection strategy + successful staged test on dev Supabase (no production until signed off). |

---

## BACKLOG-003 — EU co-location: deploy API + worker next to Supabase DB

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-05-31 |
| **Effort** | Infra / deployment (not app code) |
| **Source** | `CONTEXT.md` (Jun 1 “Phase 4 connection pooling / EU co-location”; May 31 “deployment co-location (API next to DB in EU) as the biggest latency lever”) |
| **Idea** | Run application tier in the same region as the Postgres instance to cut ~2–3s round-trip tax on remote dev DB. |
| **Why / deferrable** | Complements pooling; pure infra; no value until target hosting region is chosen. |
| **What the work is** | Deployment topology change (API, worker, Redis if needed) in EU; update env URLs; smoke importers. |
| **Regression traps** | Secrets, CI, and local-dev docs must stay coherent with `AGENTS.md` local-no-Docker mode. |
| **Behavior to retain** | Same DB identity (`cip`); no data migration. |
| **Out of scope** | Application feature work. |
| **TRIGGER** | Production or shared dev Supabase is pinned to EU and team approves infra move. |

---

## BACKLOG-004 — Import Flow Phase 3: capability-driven wizard componentization

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-05-31 |
| **Effort** | Very large |
| **Source** | `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` (§7 Phase 3, §9 D2/D4); `CONTEXT.md` (May 31 “Next: Phase 3 … GATED behind PM core-loop re-run”) |
| **Idea** | Replace `isPm` / `isDsi` / `isShipmentEvidence` branches in `admin/imports/page.tsx` with `ImportFlowCapability` from static client map (`packages/types/`), mounting `mapping_ui` and gating steps per importer. |
| **Why / deferrable** | Contract Phase 1 is design-only done; implementation gated until PM core loop is re-proven end-to-end. |
| **What the work is** | Static capability map; flag-gated rollout per importer; optional later promotion to `GET /templates` `capability` field (D2 upgrade path). |
| **Regression traps** | Breaking shipment 4-step inline steward; PM 6-step commit; DSI validate/apply modes. |
| **Behavior to retain** | Per-importer legitimate differences in `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` §5 matrix. |
| **Out of scope** | Phase 4 write optimizations (separate entry). |
| **TRIGGER** | PM core-loop re-run passes on target branch **and** explicit approval to start Phase 3 implementation. |

---

## BACKLOG-005 — Roll `CanonicalColumnMappingPanel` to DSI column mapping

| Field | Detail |
|-------|--------|
| **Status** | **Done · 2026-06-06** — DSI mapping step uses `CanonicalColumnMappingPanel` with `DSI_MAPPING_REQUIRED_GROUPS` (parity with shipment). |
| **Effort** | Medium (web) |
| **Source** | `apps/web/src/features/import-mapping/CanonicalColumnMappingPanel.tsx` (lines 26–35: “DSI / shipment” family); `CONTEXT.md` (Jun 1: panel built, “used by shipment mapping”); `admin/imports/page.tsx` (shipment mount ~3558; DSI still uses legacy DSI mapping UI elsewhere in same file) |
| **Idea** | Use the shared mapping panel for DSI canonical column mapping (parity: summary chips, mapped/unmapped filter, searchable targets, duplicate warnings). |
| **Why / deferrable** | Shipment mapping UX was the first adopter; DSI mapping works today. |
| **What the work is** | Wire DSI mapping step to `CanonicalColumnMappingPanel` with DSI `targetOptions` / required groups; preserve save + validate mutations. |
| **Regression traps** | DSI disposition model differs from PM; do not pull PM-only disposition into DSI. |
| **Behavior to retain** | Existing DSI mapping payload and validate/revalidate flows. |
| **Out of scope** | Shipment steward swap (BACKLOG-001). |
| **TRIGGER** | Shipment mapping panel stable on `main` and DSI import mapping UX task is prioritized. |

---

## BACKLOG-006 — Slim shipment `mapping-candidates` API response (paginate / omit `line_ids`)

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-01 |
| **Effort** | Medium (API + web) |
| **Source** | `CONTEXT.md` (Jun 1 steward perf: “Unchanged: … mapping-candidates payload shape”); `apps/api/app/api/v1/endpoints/shipment_evidence.py` (`list_shipment_import_job_mapping_candidates` returns full `context` per row); contrast `apps/api/app/schemas/dsi_mapping_candidates.py` (paginated DSI list) |
| **Idea** | Reduce steward panel load time (~3–5s GET for large jobs) by paginating candidates and/or omitting `context.line_ids` from list payload while keeping `row_count` (and fetch line scope only on steward apply server-side). |
| **Why / deferrable** | Explicitly left unchanged during steward perf work to limit risk; batching addressed apply path first. |
| **What the work is** | New query params or list DTO; optional `GET .../candidates/{id}/context`; update `ShipmentEntityStewardPanel` / future workspace adapter queries. |
| **Regression traps** | Steward ops still require `line_ids` server-side (`shipment_evidence_steward_ops._line_ids_from_context`); client must not break bulk selection scope. |
| **Behavior to retain** | Steward apply semantics and job-bound line verification. |
| **Out of scope** | Changing enrichment/scoring. |
| **TRIGGER** | Post-merge steward perf smoke shows `mapping-candidates` GET still dominant in browser waterfall for jobs with 100+ candidates. |

---

## BACKLOG-007 — Shipment post-validation: edit mapping, re-validate, and `source_key` stability

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-01 |
| **Effort** | Medium–large (web + validate pipeline) |
| **Source** | `CONTEXT.md` (Jun 1: re-map only at `shipment_mapping_ready` / pre-validation); `apps/web/src/app/(app)/admin/imports/page.tsx` (lines 3468–3477 revisit read-only; 3543–3573 mapping panel gated to `shipment_mapping_ready`); `apps/api/app/models/shipment_evidence.py` (lines 19–20: upsert on `(import_job_id, source_key)`); `apps/api/app/services/imports/shipment_evidence_source_keys.py` (business key from mapped canonical fields) |
| **Idea** | Allow “edit mapping & re-validate” on a revisited shipment job **after** validation (not only pre-validation), with explicit handling when mapping changes alter `source_key` fragments (upsert vs orphan lines / candidate rebuild). |
| **Why / deferrable** | Pre-validation re-map was shipped first; post-validation requires pipeline + UX design for evidence line lifecycle. |
| **What the work is** | Stage-aware UI; re-run `process_shipment_evidence_import`; document operator flow for mapping corrections; tests for `source_key` change when mapped columns shift. |
| **Regression traps** | Duplicate evidence lines; stale `import_entity_mapping_candidate` rows; steward mappings tied to old line ids; latest-job-wins semantics on `fact_inbound_shipment`. |
| **Behavior to retain** | Idempotent re-validate intent (replace-in-place per job, not duplicate jobs); governance boundaries. |
| **Out of scope** | Auto-create masters from evidence. |
| **TRIGGER** | Operator story approved: fix column mapping on job #N after validate without re-uploading file. |

---

## BACKLOG-008 — DSI region evidence: read-only hints from shipment evidence

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · (plan doc) |
| **Effort** | Medium |
| **Source** | `docs/DSI_REGION_EVIDENCE_AND_FALLBACK_PLAN.md` (architecture diagram line 47: “(Later) shipment / other modules — read-only hints”) |
| **Idea** | Add shipment-derived region hints into DSI customer region evidence rank (read-only; steward confirm still required for `region_id` from channel). |
| **Why / deferrable** | Phase A–B DSI-only region engine first; shipment module is separate consumer. |
| **What the work is** | Extend `dsi_customer_region_evidence` (or batch builder) with shipment evidence source; unit tests; no auto-write `region_id` from channel/shipment without steward. |
| **Regression traps** | Channel token geographic hint rules; do not conflate with product shipment tie-break (`dsi_product_shipment_tiebreak.py`). |
| **Behavior to retain** | DSI resolution order; corroboration tier order. |
| **Out of scope** | Shipment import changes. |
| **TRIGGER** | Region evidence Phases A–B shipped and steward UX stable; user requests cross-module hints. |

---

## BACKLOG-009 — PIM: typed-attribute promotion from `specs_json` (longer-term)

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-05-31 |
| **Effort** | Very large |
| **Source** | `docs/PRODUCT_MASTER_PIM_DESIGN_BRIEF.md` (§5 proposed architecture “for debate”; §7 safety: additive, feature-flagged; “not built”); `CONTEXT.md` (May 31 “full PIM/category-template model” in Not done) |
| **Idea** | Category templates + typed storage (typed EAV or hybrid JSONB) promoted from today’s canonical `dim_product.specs_json` read store. |
| **Why / deferrable** | Design brief only; `specs_json` is already canonical for reads; PIM is lower risk as additive path. |
| **What the work is** | Schema/templates, steward-approved attribute definition creation, feature flag, real-DB scale validation per SQL rule. |
| **Regression traps** | Hot `product_import_sync` path; 2M-row scale. |
| **Behavior to retain** | `specs_json` as current read store until flag flip; no silent schema creation. |
| **Out of scope** | Dropping legacy PAV (separate entry). |
| **TRIGGER** | Explicit product decision to fund PIM phase + migration plan approved. |

---

## BACKLOG-010 — Drop legacy `product_attribute_value` rows (~2M, destructive)

| Field | Detail |
|-------|--------|
| **Status** | **N/A for this branch · 2026-06-06** — destructive ops require explicit Warren approval + Supabase PITR; no code change. Remains a future ops task when PM `specs_json` path is production-proven. |
| **Effort** | Medium (ops) + approval |
| **Source** | `CONTEXT.md` (May 31 PM EAV: “left in place (dropping … needs explicit approval)”; import audit “still pending: drop existing 2M PAV rows”) |
| **Idea** | Remove dead write-only PAV data after `specs_json` commit path is proven in production. |
| **Why / deferrable** | Destructive; reversible only via DB backup/PITR. |
| **What the work is** | Approved migration or one-off script; verify zero readers; backup before run. |
| **Regression traps** | Any hidden reader; `PM_WRITE_LEGACY_EAV` escape hatch users. |
| **Behavior to retain** | `specs_json` commit path. |
| **Out of scope** | Re-enabling EAV writes by default. |
| **TRIGGER** | Explicit Warren approval + Supabase restore point taken. |

---

## BACKLOG-011 — `catalog_product` commit path: per-row `flush()` → bulk `INSERT…ON CONFLICT`

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-05-31 |
| **Effort** | Medium |
| **Source** | `CONTEXT.md` (May 31 “Not done: catalog_product per-row flush → bulk”) |
| **Idea** | Batch catalog upsert on PM commit like product bulk upsert. |
| **Why / deferrable** | PM commit already fast after EAV write removal; diminishing returns until large catalogs return. |
| **TRIGGER** | PM commit profiling shows catalog flush as dominant cost again. |

---

## BACKLOG-012 — AG Grid test mock: `getDisplayedRowCount` for products web suite

| Field | Detail |
|-------|--------|
| **Status** | **Done · 2026-06-06** — shared `agGridReactMock.tsx` + products page test mock extended (`getDisplayedRowCount`, `deselectAll`); 15/15 pass. |
| **Effort** | Small |
| **Source** | `CONTEXT.md` (Jun 1 Option A: “pre-existing … AG Grid mock lacks `getDisplayedRowCount`”; fails on pre-change commit too) |
| **Idea** | Extend shared AG Grid test mock so `admin/products/page.test.tsx` passes. |
| **Why / deferrable** | Unrelated to product channel removal; test-only. |
| **What the work is** | Add `getDisplayedRowCount` to vitest grid mock (match `CatalogDimensionGridPanel` usage). |
| **TRIGGER** | Products page test suite required in CI gate. |

---

## BACKLOG-013 — `customer_sell_through` own import surface (D1)

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-05-31 |
| **Effort** | Large |
| **Source** | `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` (§9 D1, §5 row, §10; `hidden_from_generic_ui`, deferred `mapping_ui` / `steward_surface`); `apps/api/app/services/imports/customer_sell_through.py` (line 96: parser not implemented for some structure types) |
| **Idea** | Dedicated UI + parsers for customer sell-through (not generic wizard). |
| **TRIGGER** | Sell-through importer prioritized in roadmap. |

---

## BACKLOG-014 — Customer classification mapping import (template deferred)

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · (template seed) |
| **Effort** | Medium |
| **Source** | `apps/api/app/services/imports/template_definitions.py` (line 298: “intentionally deferred; not wired for apply yet”) |
| **TRIGGER** | Business requests customer classification import apply path. |

---

## BACKLOG-015 — Import cancel: revoke all Celery tasks in slot registry (follow-up)

| Field | Detail |
|-------|--------|
| **Status** | **Done · prior to 2026-06-06** — `import_job_task_control._collect_celery_task_ids` uses `iter_slot_task_ids` across all registered slots (main, dsi_bulk, pm_*, dsi_*, lineup). |
| **Effort** | Small–medium |
| **Source** | `CONTEXT.md` (May 31 Phase 2: “Known follow-up … extend revoke via the registry”) |
| **Idea** | On cancel, revoke `pm_commit` / `pm_validate` / `dsi_soh` / velocity / forecasting / lineup tasks, not only main + `dsi_bulk`. |
| **TRIGGER** | Orphan workers observed after cancel or user reports zombie tasks. |

---

## BACKLOG-016 — DSI steward finalize: scoped later items

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · (plan) |
| **Effort** | Large (multiple features) |
| **Source** | `docs/DSI_STEWARD_FINALIZE_PLAN.md` (§ Deferred); `docs/SESSION_HANDOVER_2026_05_23.md` (§6 Scoped for later) |
| **Idea** | Duplicate Phase 2 clusters; distributor hub/branch SOH; web/registry enrichment for duplicate decisions; open peer cross-page lookup; `shipment_evidence_line.distributor_id` index (`CREATE INDEX CONCURRENTLY`); DSI upload Celery infer backgrounding. |
| **TRIGGER** | Explicit approval per row in SESSION_HANDOVER §6 (do not bundle). |

---

## BACKLOG-017 — DSI embedding-based duplicate detection

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · (doc) |
| **Effort** | Large |
| **Source** | `docs/DSI_RESOLUTION_PERFORMANCE.md` (lines 3–7: “not implemented … stopped before implementation”) |
| **Idea** | True embedding similarity vs current `difflib` pairwise job-local scoring. |
| **TRIGGER** | Steward false-positive/negative rate still unacceptable after cascade tuning. |

---

## BACKLOG-018 — DSI geo token indexes (recommended, not applied)

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · (doc) |
| **Effort** | Small (migration, needs approval) |
| **Source** | `docs/DSI_RESOLUTION_PERFORMANCE.md` (§ `dsi-unresolved-geo-tokens`: “Recommended indexes … not applied”) |
| **TRIGGER** | `EXPLAIN` on geo collection still slow after cache fix. |

---

## BACKLOG-019 — Historical lineup: deferred import Phase items

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-04-26 checkpoint |
| **Effort** | Large (bundle) |
| **Source** | `docs/memory/derived/platform_import_system_truth.md` (§ “Deferred items (as of f47bcea)”) |
| **Idea** | EntityMappingQueue customer token resolution; loaded lineup inspect UI; post-apply navigation; jobs list pagination; duplicate-apply guard; multi-sheet mapping; `match_strategy` JSONB framework; etc. |
| **TRIGGER** | Historical lineup module prioritized; pick **one** slice per `platform_import_system_truth.md` “Phase 2B” guidance. |

---

## BACKLOG-020 — Product Master: full job revisit in wizard

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · (UI) |
| **Effort** | Medium |
| **Source** | `apps/web/src/app/(app)/admin/imports/page.tsx` (line 2024: “Full PM revisit is not yet supported”); `page.test.tsx` (“deferred template visibility”) |
| **TRIGGER** | PM ops need edit mapping / re-validate on committed or validated PM jobs from `?job=`. |

---

## BACKLOG-021 — Commercial Planner: RBAC, durable recommendation store, router extraction

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-05-30 |
| **Effort** | Large |
| **Source** | `docs/COMMERCIAL_PLANNER_GAP_ANALYSIS.md` (executive summary lines 11–12, security row) |
| **TRIGGER** | Commercial Planner production hardening phase approved. |

---

## BACKLOG-022 — Unify the import worker enqueue helper (validate vs shipment apply)

| Field | Detail |
|-------|--------|
| **Status** | **Done · 2026-06-05** (triggered by CST apply — third caller) |
| **Effort** | Small |
| **Source** | `apps/api/app/api/v1/endpoints/imports.py` (`_enqueue_import_worker_task`, ~line 71); `apps/api/app/api/v1/endpoints/shipment_evidence.py` (`_dispatch_shipment_apply`) |
| **Idea** | `_dispatch_shipment_apply` deliberately duplicates the broker-send → dev in-process thread → sync fallback logic of `imports._enqueue_import_worker_task` (only `task_name` + `sync_work` differ). Extract the helper into a shared service (e.g. `app/services/imports/import_dispatch.py`) and import it from both endpoints. |
| **Why / deferrable** | Duplication chosen to avoid coupling the apply path to the validate endpoint module and to keep the working validate dispatch untouched while shipping the apply fix. Pure refactor; no behavior change. |
| **Shipped** | `app/services/imports/import_dispatch.py` — `enqueue_import_worker_task(job_id, *, task_name, log_label, in_process_thread_name, sync_work) → (bool, str\|None)`. `imports._enqueue_import_worker_task` now delegates to it; `shipment_evidence._dispatch_shipment_apply` now delegates to it. Preserves `(dispatched, task_id)` contract and both dev-fallback paths. |

---

## BACKLOG-023 — Generalize `dsi-progress` terminal label beyond "Validation complete"

| Field | Detail |
|-------|--------|
| **Status** | **Done · 2026-06-06** — `_dsi_terminal_progress_label()` returns "Apply complete" when `stage=loaded` / apply mode; validate label unchanged. |
| **Effort** | Small |
| **Source** | `apps/api/app/api/v1/endpoints/imports.py` (`get_dsi_job_progress`, the `job_db_indicates_pipeline_finished` branch hardcodes `phase_label = "Validation complete"`) |
| **Idea** | The shared progress reader is reused by shipment **apply** (which finishes at stage `loaded`), but its terminal label always says "Validation complete". Derive the label from `import_mode` / stage (e.g. "Apply complete" when `import_mode == 'apply'`). |
| **Why / deferrable** | Cosmetic only — the apply progress panel transitions to the success state correctly; just the transient terminal label is validate-flavored. |
| **What the work is** | Branch the terminal `phase_label` on `import_mode`/stage in `get_dsi_job_progress`; optionally thread a label through the progress response. |
| **Regression traps** | Don't change `phase`/`pct`/`status` shape consumed by `useImportJobProgressQuery` and the global indicator. |
| **Behavior to retain** | DSI + shipment validate progress labels unchanged. |
| **Out of scope** | Changing how completion is detected. |
| **TRIGGER** | Apply progress label is reported as confusing, or a per-mode label is otherwise prioritized. |

---

## BACKLOG-024 — AI resolver absent for `distributor_master` + `historical_lineup`

| Field | Detail |
|-------|--------|
| **Status** | **Done · 2026-06-06** — `try_ai_token_resolution` wired in `_process_distributor_master` (in-memory candidates via `distributor_candidates_from_dim_list`) and `historical_lineup.py` for customer/distributor/product misses. |
| **Effort** | Small–medium per importer |
| **Source** | This branch's importer audit; `apps/api/app/ingestion/pipeline.py::_process_distributor_master` (no AI); `apps/api/app/services/imports/historical_lineup.py` (no `ai_*` import) |
| **Idea** | Wire the shared `try_ai_token_resolution` wrapper into the two importers that currently hard-error on unknown FK/token instead of offering an AI suggestion — matching `customer_master` (FK codes) and DSI/shipment. |
| **Why / deferrable** | Same class of unresolved-token failure the wrapper already handles elsewhere; deferrable because these importers are lower-traffic and were not on the shipment→DSI→customer-reports critical path. |
| **What the work is** | In `_process_distributor_master`, AI-resolve unknown codes via the wrapper + `distributor_candidates`; in historical lineup parsing, AI-resolve customer/distributor/sku tokens on deterministic miss. Deterministic-first, ≥0.90 auto. |
| **Regression traps** | Don't auto-create masters (governance); keep deterministic resolution first; wrapper no-op when AI disabled. |
| **Behavior to retain** | Existing hard-error path when AI disabled or below threshold. |
| **TRIGGER** | An importer-resolution-consistency task is approved, or one of these importers hits real unresolved-token volume. |

---

## BACKLOG-025 — Generic-pipeline apply → async (masters / historical / sell-through)

| Field | Detail |
|-------|--------|
| **Status** | **Done (part A) · 2026-06-05** — `/process` endpoint async, returns `{async, task_id, job_id}`. CST is the initial beneficiary. Masters/historical still use the same endpoint and get the async path for free. |
| **Effort** | Medium |
| **Source** | This branch's audit; `apps/api/app/api/v1/endpoints/imports.py::process_job` runs `process_import_job_sync` inline |
| **Idea** | Move the generic `POST /jobs/{id}/process` (apply path for `distributor_master`, `customer_master`, `historical_lineup`, `customer_sell_through`) onto the async-dispatch pattern (broker→dev-thread→sync-fallback) with progress, like DSI/shipment apply. |
| **Shipped** | `POST /jobs/{job_id}/process` now calls `_enqueue_import_pipeline_job` (reuses `imports.process_job` Celery task) and returns `{"async": bool, "task_id": str\|None, "job_id": int}`. No frontend caller existed so no breaking change. Progress polling via existing `imports.process_job` task slot is available but not yet wired to a frontend panel. |
| **Remaining** | Frontend progress panel for CST apply (Unit C); slot registration for CST apply; masters/historical may need their own panels if they become async-heavy. |

---

## BACKLOG-026 — Product Master: consolidate the two apply pipelines

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-04 (out-of-scope this pass) |
| **Effort** | Medium–large |
| **Source** | This branch's audit; dedicated `product_master_workflow.py` (`pm_validate`/`pm_commit`, bespoke mapping, AI desc-remap) vs generic `pipeline.py::_process_product_master` (inline, channel-only AI) |
| **Idea** | One product_master apply path. Today two code paths exist for one slug with divergent AI + mapping behavior and double maintenance. |
| **Why / deferrable** | Drift risk + duplicate maintenance; deferrable because both currently work and PM is not on this pass's critical path. |
| **What the work is** | Pick the workflow path as canonical; route the generic handler to it (or delete the generic branch); reconcile AI (description remap vs channel-only) and mapping (bespoke `pmMappingHelpers` vs panel). |
| **Regression traps** | `specs_json` canonical; two-phase validate→commit semantics; existing PM tests. |
| **TRIGGER** | A PM consolidation task is approved (pairs naturally with BACKLOG-027). |

---

## BACKLOG-027 — PM + historical mapping UI → shared `CanonicalColumnMappingPanel`

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-04 (out-of-scope this pass) |
| **Effort** | Medium (web) |
| **Source** | This branch's audit; PM bespoke `pmMappingHelpers`/`pmMappingTargetOptions`; historical override mapping; vs shared panel used by DSI/shipment |
| **Idea** | Replace the PM and historical-lineup bespoke mapping tables with the shared `CanonicalColumnMappingPanel` (parity rule §4). |
| **Why / deferrable** | Removes a third/fourth mapping-UI shape; deferrable, cosmetic-ish, no correctness gap. |
| **What the work is** | Mount the panel with PM/historical target options + samples; keep server validation; delete bespoke helpers once parity verified in-browser. |
| **Regression traps** | PM `pm_mapping_saved` stage flow; historical override semantics. |
| **TRIGGER** | A mapping-UI unification task is approved (pairs with BACKLOG-026). |

---

## BACKLOG-028 — Infra: remote Supabase pooler drops SSL on long-lived apply connections

| Field | Detail |
|-------|--------|
| **Status / parked** | **Superseded** · 2026-06-09 — sync engine verified on `:5432` session mode; job #43 validate drop was a **~15 min monolithic transaction** (50k-row commit interval + nested savepoints per 2k chunk), not `:6543` misconfig. Fix: per-chunk commit + F-02 on validate (`distributor_sales_inventory.py`); see CONTEXT.md Jun 9 entry. Apply long-transaction risk may still apply separately — chunk apply remains BACKLOG-002/-003 territory. |
| **Effort** | Investigation (infra), then config |
| **Source** | This branch's DSI-apply live smoke (2026-06-04): `psycopg.OperationalError: SSL connection has been closed unexpectedly` during the long-held `SELECT … FROM dim_product` (17k rows) deep in `complete_dsi_import_job_to_loaded`, then statement timeout; reproducible across two runs. Short isolated scans (~5–8s) succeed. |
| **Idea** | The session pooler (`:5432`) drops a connection held open for a long apply transaction, which then lingers server-side as `idle in transaction` holding row locks. This caps how large a DSI apply can run synchronously **or** in a single worker transaction, and it (not this branch's code) blocked the Unit 2 end-to-end facts smoke. |
| **Why / deferrable** | Environmental, not a code defect — the old sync apply hits the same fragility. Backgrounding is still strictly better (no proxy timeout; clean `STAGE_FAILED`). Deferrable to an infra/connection-strategy task. |
| **What the work is** | Reproduce against the pooler; tune `statement_timeout` / keepalives / `idle_in_transaction_session_timeout`; consider chunking the apply transaction or BACKLOG-002/-003 (session pooler config / EU co-location). Re-run the Unit 2 facts smoke against a stable DB to confirm. |
| **Regression traps** | Don't disable statement_timeout globally; keep `statement_cache_size=0`/`prepare_threshold` fixes. |
| **TRIGGER** | An infra/DB-stability task is approved, or DSI apply fails for Warren in normal use. |

---

## BACKLOG-029 — Unit 3 sell-through surface + `ImportFileUploadZone` extraction decision

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-05 (updated; part (a) already done) |
| **Effort** | Medium (sell-through surface) + Small (upload-zone decision) |
| **Source** | This branch: DSI apply async backend committed `c079cc6`; **`dsiApplyAsync` frontend poll committed `153c93c`** (7 occurrences in `page.tsx` — `setDsiApplyAsync`, `dsiApplyPollJob`, `dsiApplyAsync || dsiApplyPollJob`, poll `useEffect`, `onSuccess` handler; terminal on `loaded`/`failed`, not `validated`). `ImportFileUploadZone` component committed in `153c93c` but **never rendered as JSX** — the import at line 64 of `page.tsx` is unused; the 3 inline upload zones still exist. customer_sell_through backend committed `09d21ef` (no web surface yet). |
| **Part (a) — DONE** | `dsiApplyAsync` poll wiring committed in `153c93c`. Not a pending task. |
| **Part (b) — CST surface** | Build the minimal drivable `customer_sell_through` surface by composing the shared `CanonicalColumnMappingPanel` + `ImportStewardCandidateWorkspace` + async apply (do not build bespoke UI). Requires running browser for verification. |
| **Part (c) — DONE** | `ImportFileUploadZone` extraction committed in `d0a8923` — component rendered at 3 sites in `imports/page.tsx`. Browser upload/drag smoke still recommended when touching that page. |
| **Regression traps** | Apply poll: transits through `validated` before `loaded` — terminal condition must stay `loaded`/`failed` only (already correct). Upload zones: preserve drag-and-drop, `canUpload` gating, `pending` progress bar; do not break the DSI / shipment / generic upload flows. |
| **Governance** | Provisional creation stays steward-initiated; no auto-create. |
| **TRIGGER** | (b) sell-through: surface prioritized in roadmap + running browser available. (c) upload-zone: a browser-verified frontend task is approved for this branch, or the unused import is flagged by linter in CI. |

---

## BACKLOG-030 — DSI validate: batched staging upsert + chunked commits (remote Supabase reliability)

| Field | Detail |
|-------|--------|
| **Status** | **Done (Phase 1) · 2026-06-06** — batched staging (2k chunks), commit every 50k rows, cache-backed AI candidates, SQL month filter on corroboration. **169k Supabase soak (job #43):** 168,839 staging lines, ~3,190 s (~53 min, ~53 rows/s) — **accepted** (62 rows/s gate waived). `fact_sales_sellout` still 0 until apply. |
| **Effort** | Large (API); integration test against remote Supabase required |
| **Source** | Jun 5 audit: job #43 `failed` with `psycopg.OperationalError` on `SELECT dim_customer LIMIT 60` after ~45 min; full rollback → 0 candidates. Shipment validate already batched (`shipment_evidence_import.py`); DSI still per-row `db.add` + monolithic transaction. |
| **Idea** | Bring DSI validate write path to import-parity bar: chunked `INSERT … ON CONFLICT` for `import_distributor_si_staging_line` (and related row results where applicable); optional **chunked commits** with checkpoint metadata so pooler drops do not zero entire 45-minute runs; eliminate per-row `customer_candidates(db, …)` DB round-trips (use `_build_resolution_cache` / in-memory slice). |
| **Why / deferrable** | **Not deferrable** for remote Supabase 100k+ row DSI files — BACKLOG-028/002/003 help but do not replace shorter transactions. Warren explicitly staying on remote Supabase for realistic testing. |
| **What the work is** | (1) Bulk staging upsert mirroring shipment pattern. (2) Chunk boundary + `staged_metadata` checkpoint (design: commit every N rows or per chunk with idempotent re-run). (3) Remove hot-loop `customer_candidates` SELECT. (4) Real Supabase E2E validation per SQL rule. (5) Record wall time vs baseline (~62 rows/sec / ~45 min @ 169k). |
| **Regression traps** | DSI resolution tier order; eligibility before corroboration; governance (no auto-create); historical vs weekly mode; `source_key` / staging line identity on re-chunk; Celery `process_job` still catches exceptions → job `failed` (document or fix separately). |
| **Behavior to retain** | `ShipmentCorroborationCache` preload; steward candidate aggregation semantics; idempotent re-validate intent. |
| **Out of scope** | Temp-file shipment evidence download (wrong layer); switching dev to local `cip`; changing corroboration order. |
| **Pairs with** | BACKLOG-028 (pooler tuning), BACKLOG-002 (pooling), BACKLOG-003 (EU co-location). |
| **TRIGGER** | **Met** — job #43 failed on remote Supabase during validate. Implement Phase 1 of `SESSION_HANDOVER_2026_06_05_DSI_REMOTE_SUPABASE.md`. |

---

## BACKLOG-031 — Admin data health dashboard (table counts + import evidence viewer)

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-06 |
| **Effort** | Medium (API read models + web admin page) |
| **Source** | Jun 6 session: Supabase has ~222k DSI staging lines but Channel Operations sell-out shows 0 until apply; operator needs visibility without raw pgAdmin/SQL. |
| **Idea** | Read-only admin page: per-table row counts + approximate sizes (facts vs staging vs masters), import job summary (validate vs apply, staging vs fact counts per job), link to existing import bulk-delete. Not a full pgAdmin — curated CIP views only. |
| **Why / deferrable** | Validates system health and explains validate≠apply confusion; deferrable until post–Unit 1–5 delivery and steward/apply next steps are chosen. |
| **What the work is** | API: `GET /admin/data-health` (async, `data_unavailable` graceful); web: `/admin/data-health` with ModuleDataSection cards + job drill-down. Optional: Supabase dashboard link for deep DBA work. |
| **Regression traps** | Read-only; no destructive actions on this page; do not expose connection strings or raw SQL console by default. |
| **Behavior to retain** | Import job cancel/bulk-delete stays on imports page; governance unchanged. |
| **Out of scope** | Embedded pgAdmin; schema migrations; auto-apply. |
| **TRIGGER** | Operator asks for DB health visibility again, or before next large Supabase soak (apply on job #43). |

---

## BACKLOG-032 — Post import bulk-delete: targeted VACUUM / disk reclamation runbook

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-06 |
| **Effort** | Small (ops script + docs) · Medium if automated after delete |
| **Source** | Supabase dev: bulk delete of import jobs (except active job #43); repeated `VACUUM` in SQL editor; `VACUUM FULL` times out; dashboard disk size unchanged. |
| **Idea** | Document and optionally script **targeted** post-delete maintenance: `VACUUM (ANALYZE)` on evidence/staging tables affected by import job bulk delete; `VACUUM FULL` only as a manual, maintenance-window ops step when dead-tuple bloat is confirmed — not from the app or SQL editor transaction wrapper. |
| **Why / deferrable** | Regular `VACUUM` does not return disk to the OS; `VACUUM FULL` requires exclusive locks + long runtime (timeouts on Supabase dashboard / pooler). Autovacuum handles most dead tuples; ops step needed only after large evidence deletes when dashboard disk stays high. |
| **What the work is** | (1) Ops doc: connect via **session** `:5432` psql, `SET statement_timeout = 0`, stop API/worker, one table at a time. (2) Read-only bloat query (`pg_stat_user_tables`, `pg_total_relation_size`) before choosing FULL vs ANALYZE. (3) Optional `apps/api/scripts/vacuum_import_evidence_tables.py` (explicit table list, dry-run, confirms `current_database()`). (4) Do **not** hook into app delete path automatically — governance + lock risk. |
| **Regression traps** | `VACUUM FULL` on `import_distributor_si_staging_line` while job #43 is active blocks steward/validate; never run inside a transaction; avoid `:6543` pooler for long maintenance; credentials never in repo. |
| **Behavior to retain** | Import bulk delete remains the supported cleanup path; vacuum is follow-up ops only. |
| **Out of scope** | Embedded pgAdmin; app-triggered `VACUUM FULL` on every delete; `VACUUM FULL` on all public tables. |
| **TRIGGER** | After large import evidence bulk delete AND (`n_dead_tup` still high 24h later OR Supabase disk quota pressure) AND Warren approves maintenance window. |

---

## BACKLOG-033 — Bitemporal shipment evidence model (append-only observations + current-state view)

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-14 |
| **Effort** | Very large (schema + import pipeline + fact layer + consumer migration) |
| **Source** | Session audit (jobs #32 Jun-1, #34 Jun-3, #40 Jun-4 — same workbook, distinct temporal snapshots); `apps/api/app/services/imports/shipment_evidence_source_keys.py` (`stable_source_key_for_row`, `report_type:state|order_no_or_delivery_no|item`); `apps/api/app/models/shipment_evidence.py` (upsert on `(import_job_id, source_key)`); `apps/api/app/services/imports/shipment_inbound_facts.py` (`fact_inbound_shipment` copies evidence per job); `apps/api/app/services/imports/dsi_soh_reconciliation.py` (aggregates `FactInboundShipment.product_id` / quantity); `apps/api/app/services/imports/dsi_shipment_corroboration.py` (reads `resolved_unique` evidence lines) |
| **Idea** | Restructure shipment evidence/facts so each import is a dated, append-only **observation** of a shipment line's state (`eta_date`, `est_pod_date`, `promise_date`, `ship_confirm_date`, `pod_date`, `line_state`), keyed by a **stable natural identity** (`order_no` + `order_line` + `item_code`). Derive a **current-state view** = latest observation per key, which feeds volume / corroboration / reconciliation. Never overwrite prior observations. |
| **Why it matters / deferrable** | **Logistics / ETA-arrival prediction** (roadmap) needs the history of how each shipment's ETA drifts and how predicted ETA compares to actual POD. Proven in data: job #32 (Jun-1) vs job #40 (Jun-4) snapshots of the same orders show `eta_date` drift and `pod_date` going null → actual arrival — that predicted-vs-actual delta is the training signal. Deleting or overwriting snapshots destroys it. **Without a current-state view**, inbound volume double-counts: the same shipment is counted once as `open_order` (keyed by `order_no`) and again as `shipped` (keyed by `delivery_no`), because `source_key` embeds `report_type` + a state-specific id. Inflates inbound totals every week as open orders convert to shipped. Deferrable until weekly shipment cadence or ETA-prediction work is imminent — but **before** either goes live. |
| **What the work is** | (1) **Observation store**: append-only rows per import with `observation_date` (from `import_job.created_at` or explicit column) + mutable-state columns; stable line identity separate from `source_key`. (2) **Current-state view** (materialized view or query): `DISTINCT ON (order_no, order_line, item_code) ORDER BY observation_date DESC` (or equivalent). (3) **Fact layer**: `fact_inbound_shipment` reads current-state only (or becomes the view). (4) **Migrate consumers**: `dsi_soh_reconciliation`, inbound volume APIs, corroboration cache — all read current-state. (5) **Related guard**: import-time duplicate **detection** — same workbook re-imported with no `duplicate_review_required` flag; flag accidental re-runs (distinct from intentional weekly snapshots). (6) **Preserve** jobs #32 / #34 / #40 as observations once model exists — do not delete. **REJECTED:** idempotent upsert that overwrites in place (erases ETA history). |
| **Regression traps** | Any consumer summing `quantity` across all fact/evidence rows (`dsi_soh_reconciliation`, inbound volume) **must** read current-state or it double-counts open+shipped and across weeks. Corroboration already dedupes on distinct `product_id` (not broken today) but should read current-state once available. Do **not** filter to shipped-only and lose open-order observations (needed for prediction). `source_key` today is **not** stable across lifecycle (`delivery_no` only exists post-ship). |
| **Behavior to retain** | Steward / entity resolution on evidence lines; `resolved_unique` corroboration semantics; governance (no silent master creation); historical observation rows immutable after write. |
| **Out of scope** | DSI sell-out bitemporal model; logistics/ETA ML model training (downstream of this substrate); deleting legacy jobs #32/#34/#40 before migration path exists. |
| **TRIGGER** | Before the first real **weekly shipment cadence** goes live, **OR** before **logistics/ETA-prediction** (DSI Phase 4/5) work starts — whichever comes first. |

---

## BACKLOG-034 — Product Master launch/retire date integrity

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-14 |
| **Effort** | Large (audit + governed steward corrections + re-validation plan) |
| **Source** | Session audit: job #40 unique-SKU `inactive_only` anchor analysis (1,965 lines); `apps/api/app/services/imports/distributor_sales_inventory.py` (`_product_eligible_for_dsi_auto`, launch/retire window); `apps/api/app/models/dimensions.py` (`DimProduct.launch_date`, `retired_date`, `lifecycle_status`); shipment SKU-anchor override commit `6c865ea` (identity routed around bad dates) |
| **Idea** | Audit and correct `dim_product.launch_date` / `retired_date`. Multiple confirmed corruption classes. |
| **Why it matters / deferrable** | These dates gate product eligibility in DSI resolution (relaxed/strict) and would gate shipment-evidence, sell-through, and current-assortment views. Bad dates silently mis-classify products. **Confirmed on job-40 unique-SKU inactive_only anchors (1,965 lines):** 319 rows have `retired_date < launch_date` (inverted/impossible); 758 lines ship before `launch_date` (implausible at scale → likely late/wrong launch dates); 268 ship after `retired_date`. Plus: `B1403CVA-S61905W` retired 2025-12-22 before launch 2026-01-19; rows with `is_active=true` AND `lifecycle_status` in (Discarded/Disabled). This is the root cause routed around with the SKU-anchor identity rule. The override is correct for **identity**, but dates stay wrong for every other consumer. Deferrable until commercial outputs depend on lifecycle windows — but **before** SKU-anchor override is reconsidered or assortment/sell-through windows go live. |
| **What the work is** | (1) Start with the **319 inverted-window** rows — unambiguously wrong, no domain judgment. (2) Resolve `is_active` vs `lifecycle_status` inconsistency: pick the canonical eligibility driver. (3) **before_launch** cases need Warren's domain call: real pre-launch channel-fill vs late launch dates. (4) Correct via governed update; never guess values — derive from OEM/trusted source or steward review. (5) Re-validate affected DSI/shipment jobs after corrections. |
| **Regression traps** | Fixing dates changes DSI eligibility outcomes → re-validate affected jobs after. Do **not** widen windows blindly; that defeats eligibility purpose. |
| **Behavior to retain** | SKU-exact shipment identity anchor (identity ≠ sellability); DSI historical vs weekly mode semantics; steward governance on master edits. |
| **Out of scope** | Auto-correcting dates from import evidence without steward approval; reversing SKU-anchor identity rule. |
| **TRIGGER** | Before relying on lifecycle/eligibility for any commercial output (assortment, sell-through windows), and before the SKU-anchor override is reconsidered. **Pairs with** BACKLOG-033 (bitemporal shipment cleanup). |

---

## Unsourced — confirm with Warren

These were on a verification checklist but **no deferral/pending wording** was found in repo docs, comments, or planning files:

| Topic | Notes |
|-------|--------|
| **`customer_po` shipment column** | Not present in `SHIPMENT_CANONICAL_TARGETS` (`shipment_field_mapping.py`) or docs grep. |
| **Shipment async steward endpoints** | DSI documents `dsi-steward-bulk-provisional-customers/apply-async` (`docs/DSI_RESOLUTION_PERFORMANCE.md`); shipment-evidence routes have no parallel async steward apply-async pattern in `shipment_evidence.py`. No explicit “defer shipment async” text — parity gap only. |

If either is intended backlog, add a sourced entry after confirming where the decision is recorded.
