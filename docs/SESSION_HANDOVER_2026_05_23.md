# Session Handover — DSI Steward Finalize (2026-05-23)

**Purpose:** Let a new Cursor session resume without re-discovering context.  
**Do not treat this file as committed** — it was written post-push and is local-only until explicitly staged.

---

## 1. Current state

| Item | Value |
|------|--------|
| **Branch** | `main` |
| **HEAD** | `597af85` — `dsi: duplicate steward review, same-entity greenfield, cascade fixes, async revalidate UX` |
| **Prior commit** | `da28a74` — `dsi: region evidence, geo steward UX, background tasks, and jobs list perf` |
| **Pushed to `origin/main`** | Yes (`f1c007c..597af85`) |
| **Working tree** | Clean |
| **Alembic head (code + DB)** | `20260517_0037` (`fact_sales_sellout_source_key`) — verified via `alembic current` on local `cip` |
| **Active database** | `cip` @ `localhost:5432` |
| **No migrations this session** | All duplicate/steward state lives in `import_entity_mapping_candidate.context` JSONB |

### Runtime (local, Windows — no Docker)

- Web: http://localhost:3000 — `pnpm dev:web`
- API: http://localhost:8001 — `pnpm dev:api`
- Worker: `pnpm dev:worker` (Redis :6379) or `CIP_DEV_CELERY_DISPATCH=in_process_thread` in `apps/api/.env`
- Memory palace: `CONTEXT.md` (updated in `597af85`)

### Reference job used during debugging

- **DSI import job `733`** — large historical DSI (~168k rows). Duplicate hints in DB are **stale** relative to latest cascade (see §5). One known partial same-entity outcome: row **92425** (`axiom systems africa`) still `needs_review` while peer **93369** was resolved via same-entity — caused by self-referential `peer_normalized_key` before guards landed; repair by mapping 92425 to `customer_id=298` or re-running same-entity correctly.

---

## 2. What was built this session

### 2.1 Duplicate detection — Phase 1 + 1.5 cascade

**What it does**

- Two-stage similarity on customer display names: **distinctive stem** gate (≥ 0.90, exact cutoff 0.98) then **full-string** (≥ 0.88, relaxed 0.72 when generic tails align).
- Suppresses generic-only suffix matches (`technologies`, `systems`, etc.).
- Single-token edit suppression (e.g. NRC vs NGR) when shared prefix is too short.
- Distributor-scoped overlap when building `possible_duplicate_of` hints on candidates.

**Files**

| Layer | Path |
|-------|------|
| Normalization + scoring | `apps/api/app/services/imports/dsi_customer_name_normalization.py` |
| Hint annotation | `apps/api/app/services/imports/dsi_customer_intelligence.py` |
| Validate pipeline hook | `apps/api/app/services/imports/distributor_sales_inventory.py` |
| Plan gate | `apps/api/app/services/imports/dsi_resolution_plan.py` (`duplicate_review_required`) |
| Unresolved filter (list) | `apps/api/app/services/imports/dsi_mapping_candidates_list.py` |

**Tests**

- `apps/api/tests/test_dsi_duplicate_detection_cascade.py` (incl. Aeonic/Benric, Cloud IT/its, NRC/NGR)
- `apps/api/tests/test_dsi_customer_name_normalization.py`
- Session aggregate: **143 passed** (API + web unit; no `cip`)

---

### 2.2 Short prefix gate (TB / B4 / FT)

**What it does**

- When leading distinctive tokens are **&lt; 3 chars** and **differ** (e.g. `tb` vs `b4` vs `ft`), cascade returns no match — stops false positives like “TB Computers” ↔ “B4 Computers” on shared `"computers"` tail.
- When leads are the **same** short prefix, cascade still runs with boosted ratio floor.

**Files**

- `dsi_customer_name_normalization.py` — `_leading_distinctive_token()`, `short_prefix_pair` branch in `dsi_duplicate_similarity_score()`

**Tests**

- `test_dsi_duplicate_detection_cascade.py` — TB/B4/FT cases added this session

---

### 2.3 Same entity — greenfield flow (provisional + atomic dual map)

**What it does**

- POST duplicate same-entity can omit `customer_id` when **both** peers have no `customer_id`.
- Creates one provisional `dim_customer` from primary evidence, maps **both** candidates via no-commit helpers, **single** `commit` at end.
- If `suggested_entity_id` conflicts between peers → **409**.
- If `customer_id` provided → map both to that customer (existing path).

**Files**

| Layer | Path |
|-------|------|
| Ops | `apps/api/app/services/imports/dsi_steward_candidate_ops.py` — `execute_dsi_duplicate_same_entity`, `_apply_map_dsi_customer_without_commit`, `_create_provisional_dim_customer_for_same_entity` |
| Route | `apps/api/app/api/v1/endpoints/mappings.py` |
| UI | `apps/web/src/features/import-steward/dsi-mapping-steward-panel.tsx` |
| Case classification | `apps/web/src/features/import-steward/dsiStewardCandidateFilterLogic.ts` |

**Tests**

- `apps/api/tests/test_dsi_duplicate_review.py` — greenfield, suggested id, conflict, paired keys (mocked DB)

---

### 2.4 Self-peer 400 guard (backend)

**What it does**

- After peer lookup by `peer_normalized_key`, if `peer.id == cand.id` → **400** before any writes (prevents mapping only one side of a pair).

**Files**

- `dsi_steward_candidate_ops.py` — `execute_dsi_duplicate_same_entity`

**Tests**

- `test_dsi_duplicate_review.py` — self-referential peer cases

---

### 2.5 Frontend — dialog state reset + self-hint filter

**What it does**

- Filters own `normalized_key` out of `possible_duplicate_of` before defaulting peer key.
- Client guard if selected peer key equals candidate’s key.
- `useEffect` on `candidate?.id` clears: `dupSamePeerKeyError`, `dupPeerKey`, `dupSameOpen`, `expandedDuplicatePeerKey`, `dupAuditNote`.

**Files**

- `dsi-mapping-steward-panel.tsx`
- `DsiImportJobResolutionSection.tsx` (reset deps)
- `dsiStewardCandidateFilterLogic.ts`

**Tests**

- `apps/web/src/features/import-steward/dsiStewardCandidateFilterLogic.test.ts`

---

### 2.6 `lookupPeerCandidate` vs `openPeerCandidateByNormalizedKey` split

**What it does**

- **`lookupPeerCandidateByNormalizedKey`** — pure find in current page candidate list; **no `setState`**.
- **`openPeerCandidateByNormalizedKey`** — opens full steward drawer for peer (optional navigation).
- Compare expand uses lookup only so drawer **does not swap** the active candidate.

**Files**

- `apps/web/src/app/(app)/admin/imports/DsiImportJobResolutionSection.tsx`
- `apps/web/src/features/import-steward/DsiCandidateStewardDrawer.tsx` — passes `lookupPeerCandidate` / `onOpenPeerByNormalizedKey` separately
- `apps/web/src/features/import-steward/dsi-mapping-steward-panel.tsx`

---

### 2.7 Inline peer compare fix

**What it does**

- **Compare / Hide compare** under each duplicate hint in steward drawer (`dsiDuplicatePeerCompare.tsx`).
- Expanding compare does **not** scroll to top or replace drawer candidate.
- “Open full steward for peer” only when `onOpenPeerByNormalizedKey` provided.
- Message when peer not on current paginated grid.

**Files**

- `apps/web/src/features/import-steward/dsiDuplicatePeerCompare.tsx` (new)
- `dsi-mapping-steward-panel.tsx`, `DsiCandidateStewardDrawer.tsx`

---

### 2.8 Validation completion — DB-authoritative `dsi-progress`

**What it does**

- `GET /jobs/{id}/dsi-progress` trusts **DB finished state** first (`job_db_indicates_pipeline_finished`) — avoids stale Celery `PROGRESS` after completion showing incomplete UI.

**Files**

- `apps/api/app/api/v1/endpoints/imports.py` — `get_dsi_job_progress`
- `apps/api/app/services/imports/import_job_background_metadata.py` — `job_db_indicates_pipeline_finished`, `ACTIVE_CELERY_STATES`

**Tests**

- `apps/api/tests/test_dsi_job_progress.py`

---

### 2.9 Revalidate async UX (`status=running`, 409, progress panel)

**What it does**

- Dispatch sets `job.status = running` immediately; stores `celery_task_id` in `staged_metadata`.
- Second dispatch while pipeline active → **409** with conflict message.
- Frontend: `notifyDsiAsyncPipelineStarted` → nav bell + `DsiValidateProgressPanel`; no blocking `pollDsiImportPipelineUntilDone` on HTTP thread.
- `background-tasks` list respects in-flight Celery for DSI validate.

**Files**

| Layer | Path |
|-------|------|
| Dispatch / 409 | `apps/api/app/api/v1/endpoints/imports.py` |
| Background task registry | `apps/api/app/services/imports/background_tasks.py` |
| Metadata helpers | `import_job_background_metadata.py` |
| Web async helper | `apps/web/src/features/import-steward/dsiAsyncPipelineRun.ts` |
| Imports page | `apps/web/src/app/(app)/admin/imports/page.tsx` |
| Bell / hook | `GlobalBackgroundTasksIndicator.tsx`, `useGlobalBackgroundTasks.ts`, `importJobProgress.types.ts` |

**Tests**

- `test_dsi_job_progress.py`, `test_background_tasks.py`

---

### 2.10 Task cancel / retry control

**What it does**

- Revokes Celery task IDs from `staged_metadata` (`celery_task_id`, `dsi_bulk_task`), clears background metadata, marks job failed; retry path for failed jobs.
- Wired to global background tasks UI and imports API.

**Files**

- `apps/api/app/services/imports/import_job_task_control.py` (new)
- `apps/api/app/api/v1/endpoints/imports.py` — cancel/retry routes
- `apps/web/src/features/background-tasks/importJobTaskControl.ts` (new)

**Tests**

- `apps/api/tests/test_import_job_task_control.py`

---

### 2.11 Also in `da28a74` (prior commit, same push)

- Region evidence on plan rows + geo steward tab (ISO fallback default off).
- Global background tasks (nav bell, cancel/retry patterns).
- Import jobs list performance (paginated projection, no heavy JSONB on list).
- Inter-disti hint: `distributor_master_collision` on customer tokens matching `dim_distributor` — `test_dsi_distributor_name_collision.py`.

---

## 3. Architectural decisions (must respect)

| Decision | Reasoning |
|----------|-----------|
| **`duplicate_review` in `context` JSONB** | No migration; steward decisions are job-scoped evidence, not master data. |
| **`acknowledged_unique` is non-terminal** | Steward can still map or change mind; only `resolved` / `ignored` / `waived_open_channel` are terminal for steward ops. |
| **Same-entity uses no-commit map helpers + one `commit`** | Prior per-row commits left peer unmapped on partial failure; atomic dual map required for greenfield pairs. |
| **`lookupPeerCandidate` must be pure** | Side-effect lookup caused Compare to swap drawer candidate and stale dialog errors (Blast-style false blocks). |
| **Self `peer_normalized_key` → 400** | UI can send self as peer when hints misfire; backend must refuse before writing `paired_normalized_key` to self. |
| **`paired_normalized_key` from DB canonical keys** | Stored after successful same/different entity, not raw request strings. |
| **Duplicate Same/Different → local plan refresh only** | Does not trigger full server revalidate (expensive on 168k jobs); revalidate is explicit user action. |
| **Plan apply blocked by `duplicate_review_required`** | Unresolved hints with no `duplicate_review.decision` gate resolution plan rows. |
| **Hints are similarity-only, not truth** | Steward must confirm; cascade reduces false positives but does not auto-merge customers. |
| **Region vs duplicate independence** | Do not auto-split customers by region in duplicate logic; region via `customer_location` / evidence. |
| **Corroboration after eligibility (unchanged)** | Do not move shipment corroboration before historical/weekly eligibility filtering. |
| **Historical vs weekly modes stay separate** | `dsi_historical_product_eligibility_relaxed` on `staged_metadata`; never apply historical relaxation to weekly jobs. |
| **`dsi-progress` DB-first when finished** | Celery PROGRESS can linger in Redis after job row is terminal. |
| **409 on double pipeline dispatch** | Prevents overlapping validate/revalidate corrupting staged state. |
| **No auto-create `dim_*` from import evidence** | Provisional customer only via explicit steward actions (same-entity greenfield, create provisional route). |
| **Inter-disti customer column** | Map as sell-out counterparty; does not write buyer `fact_inventory_distributor`. |

---

## 4. DSI module completion status

### Done (production-ready on `main`)

- Historical DSI validate pipeline with caches (shipment corroboration, resolution).
- Workflow mode inference: `auto` / `historical` / `weekly` on upload (`dsi_workflow_mode` in `staged_metadata`).
- Entity steward workspace: distributors → customers → products → region & channel.
- Duplicate Phase 1 + 1.5 cascade + steward Same/Different + same-entity greenfield.
- Resolution plan with blockers (duplicate, geo, strategic channel in weekly mode, etc.).
- Async validate/revalidate UX + global background tasks + cancel/retry.
- Region evidence + bulk geo apply.
- Import jobs list perf pass.
- Unit test coverage for duplicate, progress, task control, normalization (no `cip`).

### Not done (honest gaps)

| Gap | Notes |
|-----|--------|
| **Bulk duplicate review** | No multi-select resolve; one pair at a time in drawer. |
| **Peer off current page** | Lookup only searches loaded candidate page; no API fetch by `normalized_key`. |
| **Duplicate Phase 2** | No cluster graph / one provisional leader for sibling groups. |
| **Revalidate job 733** | DB hints pre-date short-prefix + latest cascade fixes. |
| **DSI upload Celery infer** | Still inline `infer_dsi_job_sync` — not backgrounded. |
| **Hub/branch SOH** | `distributor_location` exists; facts are per-distributor only. |
| **Inter-disti stock reconciliation** | Derived receipt vs buyer SOH — not built. |
| **Phase 1.5+** | Registry/VAT columns, cross-job learning, phonetic keys. |
| **Web enrichment** | Deferred. |
| **`shipment_evidence_line.distributor_id` index** | Needs approved `CREATE INDEX CONCURRENTLY`. |
| **Weekly DSI product UX** | Backend weekly rules exist; **next feature** is operational weekly upload journey (see §7). |

---

## 5. Known pending items (do first in new session)

1. **Revalidate job 733** (or full revalidate after deploy)  
   - Refresh `possible_duplicate_of` hints with current cascade (TB/B4/FT false hints still in DB).  
   - Command path: Admin → Imports → job 733 → “Re-run import validation (server)” (async; watch bell / progress panel).  
   - Repair **92425** / Axiom pair if still split after revalidate.

2. **Bulk duplicate review UX**  
   - Select multiple hint pairs; batch Same/Different/same-entity.  
   - Needs API design (transaction boundaries, plan refresh strategy).

3. **Peer-not-on-current-page**  
   - Optional `GET` candidate-by-`normalized_key` for job, or server-side peer card without full grid row.  
   - Listed in `CONTEXT.md` scoped table.

---

## 6. Scoped for later (do not start without explicit approval)

Copied from `CONTEXT.md` — **do not implement** until user approves:

| Feature | Notes |
|---------|--------|
| **Duplicate Phase 2** | Cluster connected components; one provisional leader + map siblings in-job; richer plan copy. |
| **Distributor hub / branch SOH** | `distributor_location` in master; `fact_inventory_distributor` has no `location_id`. Later: per-location SOH, hub vs branch, transfer lines. |
| **Inter-disti stock reconciliation** | Derived receipt at buyer from seller sell-out vs buyer inventory snapshot — separate from steward map. |
| **Duplicate Phase 1.5+** | Registry/VAT columns; cross-job learning; phonetic keys — only if steward load still high. |
| **Web / external enrichment** | Deferred — low trust, ops cost. |
| **Open peer cross-page** | API lookup by `normalized_key` when peer not on current candidates page. |
| **`shipment_evidence_line.distributor_id` index** | `CREATE INDEX CONCURRENTLY` when approved. |
| **DSI upload Celery infer** | Still inline (`infer_dsi_job_sync`). |

Also see `docs/DSI_STEWARD_FINALIZE_PLAN.md` (committed in `597af85`) for steward finalize scope boundaries.

---

## 7. Next feature — weekly DSI uploads

**Start here in the new session.**

### What already exists (backend)

- Upload form sends `dsi_workflow_mode`: `auto` | `historical` | `weekly` (`apps/web/src/app/(app)/admin/imports/page.tsx` → `imports.py` upload).
- On validate, `distributor_sales_inventory.py` sets:
  - `meta["dsi_workflow_mode"]` — `historical` if date majority &gt; 90 days old (or explicit historical), else `weekly`
  - `meta["dsi_historical_product_eligibility_relaxed"]` — `true` only for historical
- **Weekly mode behaviour** (from project rules — do not weaken without approval):
  - Strict product eligibility (inactive products excluded unless steward exception).
  - Strategic / marketplace classification gates apply.
  - No auto-apply at 0.55 confidence — steward exceptions only.
- **Historical mode** (contrast):
  - Relaxed inactive product eligibility.
  - Skips strategic/marketplace gates.
  - Auto-apply candidates at confidence ≥ 0.55.

### What is not built (likely product work)

- Dedicated **weekly upload** workflow UX (wizard copy, defaults to `weekly`, eligibility preview).
- Incremental **current-period** file expectations vs bulk historical.
- Operational runbook: when to revalidate vs apply plan after weekly file lands.
- Monitoring/notifications for weekly jobs (may reuse async progress from this session).

### Suggested first steps for new session

1. Read `distributor_sales_inventory.py` (`dsi_historical_workflow_from_import_job`, validate loop gates).
2. Read `dsi_resolution_plan.py` weekly vs historical branches.
3. Confirm with user: single weekly file per distributor per week vs multi-distributor combined.
4. Add/adjust UI defaults and post-upload checklist — **no schema change** unless explicitly approved.

---

## 8. Constraints that never expire

Permanent rules from project brief (`AGENTS.md`, `.cursor/rules/Supply-Chain-Intelligence-Project-Rules.mdc`):

1. **Never run tests against `cip`** unless `ALLOW_TESTS_ON_DEV_DB=1` is explicitly set for that run.
2. **Never `git add .` or `git add -A`** — explicit path staging only (user may override for a one-off; default is explicit paths).
3. **Never `alembic upgrade` against `cip`** (or production) without explicit user approval; always `alembic current` first.
4. **Never push to `main`** without explicit instruction (“push”, “promote to main”, “merge to main”).
5. **Never auto-create** `dim_product`, `dim_distributor`, or `dim_customer` from import evidence without steward approval.
6. **No weak joins / substring entity resolution** — explicit token-to-dim mappings with steward confirmation.
7. **DAP ≠ PM bottom cost (`controlled_cost_amount`) ≠ landed cost** — three distinct pricing concepts.
8. **DSI resolution order** — product tiers: `item_code → EAN/UPC → sales_model_name → alias` (do not reorder without architectural approval).
9. **Corroboration after eligibility** — do not move corroboration before eligibility filtering.
10. **Fact table semantics** — `source_key` upsert; shipment latest-job-wins; sell-out/customer sales transaction-immutable (resolution FKs only).
11. **Handle missing tables** — `data_unavailable: true`, not 500, on optional facts.
12. **Local Windows dev** — no Docker unless `CURSOR_CLOUD`; Postgres/Redis on localhost.

---

## Quick test commands (safe)

```powershell
cd apps/api
.\.venv\Scripts\python.exe -m pytest tests/test_dsi_duplicate_detection_cascade.py tests/test_dsi_distributor_name_collision.py tests/test_dsi_duplicate_review.py tests/test_dsi_job_progress.py tests/test_import_job_task_control.py tests/test_background_tasks.py tests/test_dsi_customer_name_normalization.py -q
```

```powershell
cd c:\Users\warren_eliason\channel-intelligence-platform
pnpm --filter @cip/web test -- dsiStewardCandidateFilterLogic
```

Do **not** set `ALLOW_TESTS_ON_DEV_DB=1` for routine agent runs.

---

## Key commits (full messages on disk)

```text
597af85 dsi: duplicate steward review, same-entity greenfield, cascade fixes, async revalidate UX
da28a74 dsi: region evidence, geo steward UX, background tasks, and jobs list perf
```

---

*End of handover. File: `docs/SESSION_HANDOVER_2026_05_23.md` — not committed per session instruction.*
