# Session Handover — DSI Remote Supabase Reliability (2026-06-05)

**Purpose:** Hand off audit findings, phased work plan, and full backlog map so a **new agent session** (or Claude Code audit) can implement without re-discovering context.

**Read order for any new agent:**

1. This file
2. `CONTEXT.md` (top section — Jun 5 remote Supabase handover)
3. `docs/memory/derived/platform_dsi_remote_reliability_truth.md` (audit lens)
4. `docs/BACKLOG.md` (canonical deferred work — includes new **BACKLOG-030**)
5. `.cursor/rules/Supply-Chain-Intelligence-Project-Rules.mdc` + `AGENTS.md`

**Transcript:** Cursor chat `8f23ab25-8439-42fe-8129-dd62cc7b38aa` (DSI job #43 failure audit, remote DB investigation).

---

## 1. Executive summary

Warren is developing against **remote Supabase EU** (not local `cip`) intentionally — to test and optimize for remote latency and slow connections. **DSI import job #43** (`distributor_inventory`, `RAW.xlsx`, **168,839 rows**) failed after ~45 minutes with `psycopg.OperationalError: server closed the connection unexpectedly` on `SELECT … FROM dim_customer LIMIT 60`. Job rolled back: **status/stage `failed`, 0 mapping candidates**.

**Root cause class:** Long-lived single DB transaction + remote pooler + per-row ORM writes and sporadic per-row DB reads — **not** missing temp-file download of shipment evidence.

**Decision:** Do **not** switch to local `cip` for convenience; fix the pipeline for remote Supabase.

**This session produced:** Read-only audit + this handover. **No application code changed** in the audit chat.

---

## 2. Current environment state (verified 2026-06-05)

| Item | Value |
|------|--------|
| **Branch** | `fix/shipment-steward-performance` (ahead of `origin` by 2 commits at handover write) |
| **Recent HEAD** | `26d1837` Unit B CST steward; `d0a8923` ImportFileUploadZone extraction; `4ee230e` docs |
| **Active DB config** | `apps/api/.env` → `DATABASE_URL` / `DATABASE_URL_SYNC` → **Supabase EU pooler** (`aws-0-eu-west-1.pooler.supabase.com`, db `postgres`, ports **6543** async / **5432** sync) |
| **Local DB (dormant)** | `DATABASE_URL_LOCAL*` → `localhost:5432/cip` (reachable but **not** used by app unless URLs swapped) |
| **Job #43 (Supabase)** | `failed` / `failed`; `error_summary` = pooler disconnect; `candidate_count=0`; `import_row_result_count=0` |
| **Job #43 (local cip)** | Does not exist (local max job id was 743 at check time — different dataset) |
| **Reboot needed?** | **No** — transient pooler + API startup race |

### Runtime (Windows local dev — no Docker)

| Service | Command | Port |
|---------|---------|------|
| API | `pnpm dev:api` (uses `--reload` — avoid during 45+ min validates) | 8001 |
| Web | `pnpm dev:web` | 3000 |
| Worker | `pnpm dev:worker` | Celery + Redis :6379 |
| Stable API (long jobs) | `cd apps/api && .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001` (no reload) | 8001 |

---

## 3. What actually happens during DSI validate (architecture truth)

### 3.1 Upload file — already “land once, parse once”

```
Upload → storage.save() → RawFileMetadata.storage_key
Validate → storage.read() once → read_tabular() → pandas DataFrame in worker RAM
```

Code: `apps/api/app/ingestion/pipeline.py` (~783–785), `apps/api/app/ingestion/infer.py`.

Raw file is **kept** for audit/re-validate; deleted only on import job bulk delete. **Not** re-downloaded per row.

### 3.2 Shipment corroboration — DB cache, not temp file

DSI does **not** download a temp shipment evidence file. It preloads `shipment_evidence_line` into `ShipmentCorroborationCache` (2 batch queries → in-memory lookups).

Code: `apps/api/app/services/imports/dsi_shipment_corroboration.py`.

### 3.3 Master data preload (good)

`_build_resolution_cache()` loads full `dim_distributor`, `dim_customer`, aliases once before row loop.

Code: `apps/api/app/services/imports/distributor_sales_inventory.py` (~550–578).

### 3.4 Row loop gaps (bad for remote)

| Pattern | Shipment validate | DSI validate |
|---------|-------------------|--------------|
| Staging writes | Batched `INSERT … ON CONFLICT` chunks | `db.add(line)` per row (~169k) |
| Transaction | Still one commit at pipeline end | **One monolithic transaction** until `pipeline.py` commit |
| Extra DB reads | Reduced via batching | `customer_candidates(db, …)` → `SELECT dim_customer LIMIT 60` **per unresolved customer row** (AI path) |
| Wall time @ 169k | N/A at this scale | ~45 min observed |

### 3.5 Failure mechanics

1. Exception inside `process_import_job_sync` try block
2. `db.rollback()` — **all staging + candidates lost**
3. Job `status=failed`, `error_summary=str(exc)`
4. Celery task **still returns without re-raise** → worker log shows **“succeeded”** while job is **failed**

Code: `apps/api/app/ingestion/pipeline.py` (908–919), `apps/api/app/worker/tasks.py` (87–94).

### 3.6 Why “temp file download → validate → delete” is not the fix

| Proposed pattern | Reality |
|------------------|---------|
| Download temp DSI file | Already read once from storage |
| Download temp shipment file | Evidence is in DB; already memory-cached |
| Delete after validate | Breaks audit trail and re-validate |

**Best practice for remote:** shorter transactions, batched writes, checkpoint/resume, worker near DB, pooler-tuned connections — not delete-after-validate.

---

## 4. Phased implementation plan

**Goal:** Reliable DSI (and other large imports) on **remote Supabase** from dev machines with high latency.

**Governance constraints (do not violate):**

- No auto-create `dim_product` / `dim_distributor` / `dim_customer` from import evidence
- DSI resolution tier order unchanged without explicit architectural approval
- Steward workflow remains mandatory for ambiguous entities
- SQL changes require **real DB execution** against target Supabase (not mock-only)
- No migrations without explicit approval
- Feature branch only until Warren says “promote to main”

---

### Phase 0 — Immediate ops (no code) — **before Phase 1**

| # | Action | Owner | Done when |
|---|--------|-------|-----------|
| 0.1 | Confirm stack: Redis, worker, API (prefer **no reload**), web | Warren / agent | `GET /api/v1/imports/jobs/43` → 200 |
| 0.2 | **Re-run validation** on job #43 (`RAW.xlsx`, 169k rows) | Warren | Steward tabs show non-zero candidates; `stage=validated` |
| 0.3 | Budget **~45+ min** uninterrupted; no saves under `apps/api` if using `--reload` | Warren | Validate completes or fails with new error (capture logs) |
| 0.4 | Record baseline: wall time, worker log, `error_summary` if fail | Agent | Entry in `CONTEXT.md` after run |

**Risk:** Phase 0 alone may fail again on Supabase until Phase 1 lands. Treat as soak test.

---

### Phase 1 — DSI validate reliability (code) — **highest priority**

**Triggers BACKLOG-030 (new).** Directly addresses job #43 failure class.

| # | Work item | Primary files | Acceptance criteria |
|---|-----------|---------------|---------------------|
| 1.1 | **Batched staging upsert** (shipment parity) | `distributor_sales_inventory.py`; mirror `shipment_evidence_import.py` bulk upsert pattern | 169k rows written in chunks; measurable wall-time reduction |
| 1.2 | **Chunked commits + checkpoint** | `pipeline.py` and/or DSI processor; `import_job.staged_metadata` progress fields | Pooler drop after chunk N does not zero rows 1..N-1; re-run idempotent or resumes |
| 1.3 | **Remove per-row `customer_candidates` DB hits** | `distributor_sales_inventory.py` (~1600–1610); use `res_cache` or preloaded slice | No `SELECT dim_customer LIMIT 60` in row loop |
| 1.4 | **Real Supabase E2E test** | New integration test or scripted job on dev Supabase | Full validate of representative file (or subset fixture) completes without disconnect |
| 1.5 | **Progress phases** | Existing `on_progress` hooks | UI shows `loading_caches` / `processing_rows` / `building_candidates` accurately |

**Tests:** API unit tests + **mandatory** real execution on Supabase per project SQL rule.

**Does NOT complete:** pooling (Phase 2), co-location (Phase 3).

---

### Phase 2 — Connection / pooler stability (infra + config)

**BACKLOG-028 TRIGGER MET** (validate failure + prior apply SSL drops).

| # | Backlog | Work | Remote impact |
|---|---------|------|---------------|
| 2.1 | **BACKLOG-028** | Reproduce long-held sync session on `:5432`; tune keepalives, `idle_in_transaction_session_timeout`; document worker DSN strategy | **High** — direct failure class |
| 2.2 | **BACKLOG-002** | Async `NullPool`/`:6543` → session pooler `:5432` + modest pool in `session.py` | **High** latency; test `ECHECKOUTTIMEOUT` / prepared statement traps |
| 2.3 | **BACKLOG-018** | Geo token indexes (migration — needs approval) | Medium — steward geo tab slowness only |

**Order:** 1.x first (shorter transactions), then 2.1, then 2.2 with staged load tests.

---

### Phase 3 — Deployment topology

| # | Backlog | Work | Remote impact |
|---|---------|------|---------------|
| 3.1 | **BACKLOG-003** | Deploy API + Celery worker in **EU** next to Supabase | **Highest** systemic latency lever for dev/staging |

Complements Phase 1–2; does not replace batched writes.

---

### Phase 4 — Import module parity & UX (web + API surfaces)

| # | Backlog | Status | Work summary | Remote impact |
|---|---------|--------|--------------|---------------|
| 4.1 | **BACKLOG-001** | Parked | Shipment steward → `ImportStewardCandidateWorkspace` adapter | Low (steward UX) |
| 4.2 | **BACKLOG-005** | Parked | DSI column mapping → `CanonicalColumnMappingPanel` | Low |
| 4.3 | **BACKLOG-006** | Parked | Paginate / slim shipment `mapping-candidates` payload | Medium (steward load time) |
| 4.4 | **BACKLOG-007** | Parked | Shipment post-validation re-map + `source_key` stability | Low |
| 4.5 | **BACKLOG-023** | Parked | Generalize progress terminal label (“Validation” vs “Apply” complete) | None |
| 4.6 | **BACKLOG-029** | Partial | **(a) DONE** dsiApplyAsync; **(b)** CST web surface; **(c) DONE** `ImportFileUploadZone` in `d0a8923` | Low |
| 4.7 | **BACKLOG-004** | Parked | Import Flow Phase 3 capability wizard | Low |
| 4.8 | **BACKLOG-013** | Parked | `customer_sell_through` dedicated UI (D1) | Medium when built |
| 4.9 | **BACKLOG-020** | Parked | PM full job revisit in wizard | Low |
| 4.10 | **BACKLOG-015** | Parked | Cancel: revoke all Celery tasks in slot registry | Medium (ops) |

---

### Phase 5 — DSI steward & resolution depth

| # | Backlog | Status | Work summary | Remote impact |
|---|---------|--------|--------------|---------------|
| 5.1 | **BACKLOG-008** | Parked | DSI region hints from shipment evidence (read-only) | Low |
| 5.2 | **BACKLOG-016** | Parked | DSI steward finalize deferred items (see `DSI_STEWARD_FINALIZE_PLAN.md`) | Mixed |
| 5.3 | **BACKLOG-017** | Parked | Embedding-based duplicate detection | Low |
| 5.4 | **BACKLOG-024** | Parked | AI resolver for `distributor_master` + `historical_lineup` | Low |

---

### Phase 6 — Product Master & catalog performance

| # | Backlog | Status | Work summary | Remote impact |
|---|---------|--------|--------------|---------------|
| 6.1 | **BACKLOG-009** | Parked | PIM typed-attribute promotion from `specs_json` | N/A |
| 6.2 | **BACKLOG-010** | Parked | Drop legacy PAV ~2M rows (destructive) | N/A |
| 6.3 | **BACKLOG-011** | Parked | `catalog_product` bulk upsert on PM commit | Medium on large catalogs |
| 6.4 | **BACKLOG-026** | Parked | Consolidate PM two apply pipelines | Low |
| 6.5 | **BACKLOG-027** | Parked | PM + historical → `CanonicalColumnMappingPanel` | Low |

---

### Phase 7 — Other importers & platform

| # | Backlog | Status | Work summary | Remote impact |
|---|---------|--------|--------------|---------------|
| 7.1 | **BACKLOG-014** | Parked | Customer classification mapping import | Low |
| 7.2 | **BACKLOG-019** | Parked | Historical lineup deferred bundle | Medium when prioritized |
| 7.3 | **BACKLOG-021** | Parked | Commercial Planner RBAC + durable rec store | N/A |
| 7.4 | **BACKLOG-012** | Parked | AG Grid mock `getDisplayedRowCount` | None (tests) |

---

### Phase 8 — Completed (reference for auditors)

| Backlog | Done | How / where |
|---------|------|-------------|
| **BACKLOG-022** | 2026-06-05 | `import_dispatch.enqueue_import_worker_task` |
| **BACKLOG-025** | 2026-06-05 part A | `POST /jobs/{id}/process` async; CST benefits |
| **BACKLOG-029(a)** | `153c93c` | DSI apply frontend poll |
| **BACKLOG-029(c)** | `d0a8923` | `ImportFileUploadZone` rendered 3× in `page.tsx` |

---

### Phase 9 — Unsourced (confirm with Warren)

From `BACKLOG.md` § Unsourced:

- `customer_po` shipment column — not in canonical targets
- Shipment async steward endpoints — parity gap vs DSI bulk async (no explicit deferral doc)

---

## 5. Will completing ALL backlogs guarantee Supabase import success?

| Answer | Detail |
|--------|--------|
| **No** | Many backlogs are UI, PM, or unrelated importers |
| **Yes (combined)** | **Phase 1 + Phase 2 + Phase 3** materially improve odds for 169k DSI on remote Supabase |
| **Minimum viable** | **BACKLOG-030** (Phase 1) + **BACKLOG-028** (Phase 2.1) |

---

## 6. Audit instructions (for Claude Code or Opus review)

When reviewing implementation from a future session:

1. **Read this handover + `platform_dsi_remote_reliability_truth.md`** before judging diffs.
2. **Compare against shipment validate batching** (`shipment_evidence_import.py` `_shipment_evidence_line_bulk_upsert_statement`) — DSI should converge, not invent a third pattern.
3. **Verify governance:** no auto-create masters; DSI tier order unchanged; steward gates intact.
4. **Verify SQL rule:** any VALUES/CASE/bulk SQL ran against **Supabase dev** (or documented override), not mock-only.
5. **Check Celery semantics:** job `failed` vs task `succeeded` — consider re-raising after STAGE_FAILED writeback if operators find logs confusing (optional, separate from reliability).
6. **Score alternatives:** chunked commits vs smaller files vs local-only dev — document tradeoffs if implementer chose differently.
7. **Job #43 regression:** after Phase 1, re-validate `RAW.xlsx` on Supabase; record wall time and candidate counts.

**Files most likely touched in Phase 1:**

- `apps/api/app/services/imports/distributor_sales_inventory.py`
- `apps/api/app/ingestion/pipeline.py`
- `apps/api/app/services/imports/ai_resolver_wiring.py` (if candidate preload refactored)
- `apps/api/tests/test_distributor_sales_inventory_import.py` (+ new integration test)
- `docs/BACKLOG.md` (status updates)
- `CONTEXT.md` (completion entry)

---

## 7. Key code references

| Topic | Path |
|-------|------|
| Pipeline commit / rollback | `apps/api/app/ingestion/pipeline.py` |
| DSI validate processor | `apps/api/app/services/imports/distributor_sales_inventory.py` |
| Shipment bulk upsert (template) | `apps/api/app/services/imports/shipment_evidence_import.py` |
| Corroboration cache | `apps/api/app/services/imports/dsi_shipment_corroboration.py` |
| Per-row customer_candidates | `distributor_sales_inventory.py` ~1600–1610 |
| Async DB session (NullPool) | `apps/api/app/db/session.py` |
| Sync worker session (pool) | `apps/api/app/db/session_sync.py` |
| Celery process_job | `apps/api/app/worker/tasks.py` |
| Import parity rules | `.cursor/rules/import-parity.mdc` |

---

## 8. Related documents

| Doc | Role |
|-----|------|
| `docs/BACKLOG.md` | Canonical backlog incl. **BACKLOG-030** |
| `docs/RESOLUTION_IMPROVEMENT_PROPOSAL.md` | Resolution ideas (observe-only) |
| `docs/DSI_RESOLUTION_PERFORMANCE.md` | DSI perf notes |
| `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` | Import wizard contract |
| `CONTEXT.md` | Living history (insert-only at top) |
| Agent transcript | `8f23ab25-8439-42fe-8129-dd62cc7b38aa` |

---

## 9. Suggested commit message (when docs staged)

```
docs: DSI remote Supabase handover + BACKLOG-030 + memory palace (Jun 5)
```

**Stage explicitly:** `docs/SESSION_HANDOVER_2026_06_05_DSI_REMOTE_SUPABASE.md`, `docs/memory/derived/platform_dsi_remote_reliability_truth.md`, `docs/BACKLOG.md`, `CONTEXT.md`

---

## 10. Copy-paste prompt for new agent session

Use this **after** pulling latest on `fix/shipment-steward-performance` (or a child branch). Start a **new chat** for implementation — do not continue the audit thread.

```
You are implementing Phase 1 of the DSI remote Supabase reliability plan for Channel Intelligence Platform.

READ FIRST (in order):
1. docs/SESSION_HANDOVER_2026_06_05_DSI_REMOTE_SUPABASE.md
2. CONTEXT.md (top section — Jun 5 DSI remote Supabase handover)
3. docs/memory/derived/platform_dsi_remote_reliability_truth.md
4. docs/BACKLOG.md — BACKLOG-030 (primary), BACKLOG-028 / -002 / -003 (later phases)
5. AGENTS.md + .cursor/rules/Supply-Chain-Intelligence-Project-Rules.mdc + .cursor/rules/import-parity.mdc

ENVIRONMENT:
- Windows local dev, NO Docker
- Active DB: remote Supabase EU via apps/api/.env (DATABASE_URL / DATABASE_URL_SYNC) — do NOT switch to local cip unless I explicitly ask
- Branch: fix/shipment-steward-performance (feature branch; do not push to main)
- Failed job: import job #43 (distributor_inventory, RAW.xlsx, ~169k rows) — failed with pooler disconnect; 0 candidates

GOAL (Phase 1 — BACKLOG-030):
Implement DSI validate reliability for remote Supabase:
1. Batched staging upsert for import_distributor_si_staging_line (mirror shipment_evidence_import.py bulk pattern)
2. Chunked commits + checkpoint metadata so a pooler drop does not zero an entire 45-minute run
3. Remove per-row customer_candidates() DB SELECT in distributor_sales_inventory.py row loop — use preloaded resolution cache
4. Real Supabase E2E execution required (project SQL rule — not mock-only)

GOVERNANCE (non-negotiable):
- Do NOT change DSI resolution tier order or eligibility/corroboration ordering
- Do NOT auto-create dim_product / dim_distributor / dim_customer from import evidence
- No Alembic migrations without my explicit approval
- Verify SELECT current_database() before any DB write; document which DB you hit

VALIDATION:
- Focused API tests for new bulk/chunk logic
- At least one real run against Supabase dev (subset or full file — document wall time)
- pnpm lint + relevant test:api scope
- Update CONTEXT.md (insert at top only) when done

DO NOT:
- Implement unrelated backlogs in the same PR unless I ask
- Use git add -A
- Commit unless I ask

Start by reading the handover Phase 1 table, then read distributor_sales_inventory.py and shipment_evidence_import.py side by side, then propose a minimal implementation plan before editing.
```

### Optional prompt — Phase 0 ops only (re-validate soak test, no code)

```
Read docs/SESSION_HANDOVER_2026_06_05_DSI_REMOTE_SUPABASE.md Phase 0 only.

Help me re-run DSI validation for import job #43 on remote Supabase:
- Confirm Redis, Celery worker, API (no --reload), web are up
- I will click Re-run validation in /admin/imports?job=43
- Monitor worker logs and GET /api/v1/imports/jobs/43/dsi-progress
- Do NOT change code unless the run fails and you can identify a one-line ops fix
- Record outcome in CONTEXT.md when finished
```

### Optional prompt — Claude Code audit (after Phase 1 is implemented)

```
Audit-only mode. Read:
- docs/SESSION_HANDOVER_2026_06_05_DSI_REMOTE_SUPABASE.md §6
- docs/memory/derived/platform_dsi_remote_reliability_truth.md
- git diff against fix/shipment-steward-performance merge-base for BACKLOG-030 work

Compare implementation to:
1. Shipment bulk upsert pattern (shipment_evidence_import.py)
2. Import parity rule (.cursor/rules/import-parity.mdc)
3. Governance constraints in Supply-Chain-Intelligence-Project-Rules.mdc

Report: what matches the handover plan, what diverges, what you would do differently, whether real Supabase E2E evidence exists. No code changes unless I approve.
```

---

*End of handover.*
