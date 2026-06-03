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
| **Status / parked** | Parked · 2026-06-01 |
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
| **Status / parked** | Parked · 2026-05-31 |
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
| **Status / parked** | Parked · 2026-06-01 |
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
| **Status / parked** | Parked · 2026-05-31 |
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
| **Status / parked** | Parked · 2026-06-03 (during shipment apply backgrounding) |
| **Effort** | Small |
| **Source** | `apps/api/app/api/v1/endpoints/imports.py` (`_enqueue_import_worker_task`, ~line 71); `apps/api/app/api/v1/endpoints/shipment_evidence.py` (`_dispatch_shipment_apply`) |
| **Idea** | `_dispatch_shipment_apply` deliberately duplicates the broker-send → dev in-process thread → sync fallback logic of `imports._enqueue_import_worker_task` (only `task_name` + `sync_work` differ). Extract the helper into a shared service (e.g. `app/services/imports/import_dispatch.py`) and import it from both endpoints. |
| **Why / deferrable** | Duplication chosen to avoid coupling the apply path to the validate endpoint module and to keep the working validate dispatch untouched while shipping the apply fix. Pure refactor; no behavior change. |
| **What the work is** | Move the generic enqueue helper to a service module; update `imports._enqueue_import_pipeline_job` and `shipment_evidence._dispatch_shipment_apply` to call it; keep dev-fallback + task-id semantics identical. |
| **Regression traps** | Must preserve `(dispatched, task_id)` contract, dev `CIP_DEV_CELERY_DISPATCH=in_process_thread` branch, and sync inline fallback; do not change validate dispatch behavior. |
| **Behavior to retain** | Validate (`imports.process_job`) and shipment apply (`imports.shipment_apply`) dispatch + fallback semantics. |
| **Out of scope** | Changing task definitions or progress reading. |
| **TRIGGER** | A third caller needs the same dispatch helper, or the duplication is flagged in review. |

---

## BACKLOG-023 — Generalize `dsi-progress` terminal label beyond "Validation complete"

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-03 (during shipment apply backgrounding) |
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

## Unsourced — confirm with Warren

These were on a verification checklist but **no deferral/pending wording** was found in repo docs, comments, or planning files:

| Topic | Notes |
|-------|--------|
| **`customer_po` shipment column** | Not present in `SHIPMENT_CANONICAL_TARGETS` (`shipment_field_mapping.py`) or docs grep. |
| **Shipment async steward endpoints** | DSI documents `dsi-steward-bulk-provisional-customers/apply-async` (`docs/DSI_RESOLUTION_PERFORMANCE.md`); shipment-evidence routes have no parallel async steward apply-async pattern in `shipment_evidence.py`. No explicit “defer shipment async” text — parity gap only. |

If either is intended backlog, add a sourced entry after confirming where the decision is recorded.
