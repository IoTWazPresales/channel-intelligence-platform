# Platform Import System Truth

## Template/source model
- Import behavior is template-driven (`import_template`) and source-bound (`source_definition`).
- Template flags control visibility, admin-only constraints, file types, and destructive-confirm requirements.
- Source can carry parser hints, expected template overrides, and optional target product catalog linkage.

## Generic import lifecycle
- `POST /api/v1/imports/jobs` stores file and creates `import_job`.
- For non-Product-Master templates, sync processing can run in-process (`process_import_job_sync`).
- Pipeline stages include uploaded/raw/schema/mapped/validated/loaded/failed semantics.

## Product Master constrained lifecycle
- Dedicated endpoints under `/api/v1/imports/product-master/jobs/*`.
- Stages:
  - upload/infer headers
  - mapping decisions save
  - validate (staged metadata + row results)
  - commit (background, async status model)
- Mapping allows canonical targets plus explicit dispositions (`ignore`, `stage_raw`, `attribute_candidate`).

## Persistence behavior
- Validation pass writes staging snapshot (`staged_metadata`) and messages in `import_row_result`.
- Commit writes canonical product updates and optional catalog/EAV materialization.
- Commit-level state and diagnostics persist in `pm_commit_meta` and `error_summary`.

## Notable import truths/quirks
- Product Master bypasses legacy generic one-shot processing once constrained workflow metadata exists.
- Descriptor-row stripping, scalar normalization, and mapper-memory behavior are explicitly tested in API suite.
- Generic async import task exists in worker but is not the dominant API-triggered runtime path today.

## Operationally meaningful risk notes
- Import outcomes are observable via rows + progress metadata, but cross-job lineage reporting is still mostly per-job/manual.
- Product Master has stronger state machine controls than many other import templates, which are still lighter-weight.

---

## Checkpoint: `historical_lineup` (as of 2026-04-26)

Compact record of governed **historical lineup** import work shipped on `main` in this period. Broader repo init may include earlier foundation (template, handler, models, migrations); the commits below are the **discrete follow-on** slices that landed after that baseline.

### Commits completed (newest first)

| Commit | Summary |
|--------|---------|
| `0d6f50d` | **Apply post-success (web):** On successful `historical_lineup` **apply**, clear `historicalValidatedJobId` and `lastGenericFile` so “Apply validated file” hides immediately; dedicated success `Alert` (“Apply job #N completed…”) with `data-testid="apply-success-alert"`; generic “Job created / Refresh preview” alert suppressed when `upload.data.import_mode === 'apply'`. **Also:** generic upload mutation only requires `source_id` when `selectedTemplate.requires_provider` is true (fixes impossible guard for no-provider templates). Vitest: `apps/web/src/app/(app)/admin/imports/page.test.tsx` (8 tests). |
| `8dd2972` | **Job revisit (web):** `?job=<id>` loads job via `GET /imports/jobs/{id}`; wizard sync (revisit mode, step 4 for non-PM); revisit banner; jobs grid ID links to `/admin/imports?job=`; Start over / template change clears revisit + URL. |
| `5f3cc06` | **Phase 1A (API):** `historical_lineup.py` — cross-field `model_name` vs `sales_model_name` ambiguity guard; ILIKE fallback extended to `part_number` / model fields; test hardening + positive paths / apply persistence tests. |
| `0588973` | **Phase 1 (API):** `historical_lineup.py` — product resolution (SKU, `part_number`, `model_name`, `sales_model_name`, unique ILIKE); `invalid_quantity`; severity/diagnostic behavior; stability/apply-focused tests in `test_historical_lineup_*`. |

*(Local dev port/proxy alignment and `historical_lineup_workbook` dispatch fixes were done in-session; if not visible as separate commits on your branch, treat them as environment/config truth in `platform_runtime_truth.md` rather than duplicating here.)*

### Current verified behavior (automated / design intent)

- **Template:** `historical_lineup` with validate-then-apply workflow; pipeline handler `historical_lineup_workbook` (sync job path).
- **Backend:** Workbook parse → sheet/header detection → row diagnostics → normalized `HistoricalLineupImportHeader` / `HistoricalLineupImportLine` on apply; row results on `import_row_result` with first token as `code`, full list in `message`.
- **Product match:** Exact fields + guarded ILIKE; `ambiguous_product_match` / `unknown_product` / `product_matched_by_ilike` etc. as designed in Phase 1/1A.
- **Web:** Validate upload sets validation job + enables Apply when file still in session; apply clears gate + shows apply-only success alert; revisit via `?job=` without mutating old jobs.

### Manual testing result (this checkpoint)

- **Not re-executed** while writing this doc-only checkpoint.
- **Recommended checklist** (from prior gated specs): validate real workbook → Apply appears → Apply → success alert + button gone → diagnostics still visible → hard refresh `?job=<apply_job_id>` still loads rows.

### Remaining deferred items

- Diagnostics UX: `code` vs `message` / severity mismatch (e.g. first diagnostic vs max severity); optional `diagnostic_codes JSONB` — **not** implemented.
- Backend: duplicate-apply guard for `historical_lineup` — **deferred**.
- Mapping review UI, column mapping drafts, `match_strategy` JSONB, generic mapping framework — **deferred**.
- Commercial Planner candidate ranking / planner UI tied to lineup — **out of scope** for import Phase 1–2.

### Recommended next phase

- **Small, gated “Phase 2B”** (pick one): either (a) minimal diagnostics display clarification without JSONB, or (b) backend idempotent / duplicate-apply policy for `historical_lineup`, or (c) first slice of mapping review — each as its own short prompt; avoid bundling.

### Cost-control note

- Prefer **small scoped prompts** (single concern, explicit allowed files, explicit non-goals). Avoid **broad implementation** passes that mix UI + API + schema + refactors; they inflate review surface and regression risk.
