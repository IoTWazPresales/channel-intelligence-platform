# SESSION E Evidence — Unit 11 import parity

**Collection timestamp:** 2026-08-30 (Sunday), ~20:38 UTC+2 — **supplemented 2026-08-31 ~10:45 UTC+2** — **cip_test runtime 2026-08-31 ~11:30 UTC+2**  
**Collector:** Cursor agent (VERIFY run + SESSION E continuation)  
**Branch (verified):** `feat/ns-1a-fx-readiness-chips` @ `b88657a` (`git rev-parse --short HEAD` on 2026-08-31 cip_test pass)  
**Contract version (file):** **1.6 · 2026-07-27 · Owner: Warren** — matches seed expectation  
**Environment:** local Windows; web `:3000`, API `:8001`  
**Database policy:** writes on `cip_test` only after proof gate; API restored to `cip` after walk (`session_d_poll_health.py` → `"database":"cip"`)  
**Waiver lines from unit prompt:** *(none supplied — all S1–S14 in scope)*

**Surfaces in scope (operator):**

1. `/admin/imports` — Product Master (`product_master`) `CanonicalColumnMappingPanel`
2. `/admin/imports` — Historical Lineup (`historical_lineup`) `CanonicalColumnMappingPanel`
3. `ShipmentImportJobResolutionSection` — full steward flow (Import Centre step 6 revisit for job **1159**)

**Evidence-only artifact for Opus CONSULT.** No `VERDICT:` line in this file.

---

## Collection methods

| Method | Result (2026-08-30) | Result (2026-08-31 supplement) | Result (2026-08-31 cip_test) |
|--------|---------------------|--------------------------------|------------------------------|
| Code read (`Read` / `Grep`) | **Succeeded** | **Succeeded** (unchanged) | **Succeeded** (unchanged) |
| `git rev-parse` / branch | **Succeeded** @ `3f10ae4` | **Succeeded** @ `8f3c10f` | **Succeeded** @ `b88657a` |
| Playwright MCP | **Partial** — login redirect; guard blocked follow-ups | Not used | **Partial** — login + HL wizard to upload; **`PLAYWRIGHT_FILE_ROOT`** blocked file drop |
| `cursor-ide-browser` MCP | **Blocked** by EIF guard | **Succeeded** — admin @ `:3000` | **Partial** — HL wizard to upload step; **`FILE_CHOOSER_UNAUTOMATABLE`** |
| Apply/progress on `cip_test` | **Not executed** | **`CIP_TEST_NOT_EXECUTED`** | **Executed** — shipment job **640**; see S10–S11 below |
| Read-only / write DB | Not run | **`current_database(): cip`**; zero HL jobs on `cip` | **`current_database(): cip_test`** on every SQL block in `session_e_cip_test_walk.py` |

---

## 2026-08-31 browser supplement — Rule #4 (Column mapping)

Shared component: `apps/web/src/features/import-mapping/CanonicalColumnMappingPanel.tsx`.

| Surface | Route / job | OBSERVED (browser) | vs code-read (2026-08-30) |
|---------|-------------|-------------------|---------------------------|
| **PM** | `/admin/imports?job=30` → Back to column mapping (step 4) | **Full panel live:** per-column **Examples** (sample values), **Recommended** hints, **Target** dropdown, **Disposition** dropdown (e.g. Retain as staged metadata), required-core alert (display_name + technical_product_id), bulk mapping action buttons (All unmapped → Ignore/Stage, Apply suggested, Clear all). | **Confirms** code-read PASS-equivalent mount (**page.tsx 3163–3181** with `columnSamples`, `requiredGroups`, dispositions). |
| **PM revisit** | `?template=product_master&job=95` | Read-only revisit banner: *Full PM revisit is not yet supported* — mapping panel **not** shown. | **`PM_REVISIT_READONLY`** — use in-progress job (e.g. **30**) for live mapping, not completed apply revisit. |
| **HL** | `?template=historical_lineup` | Import type picker only; **no validated HL job** on `cip` to reach post-validate mapping review (`historicalValidatedJobId`). DB: zero `import_job` rows with `template_slug='historical_lineup'`. | **Confirms** code-read thin mount (**4481–4488**) but **HL mapping panel UNABLE_TO_RENDER** — **`HL_NO_JOBS_ON_CIP`**. |
| **Shipment (reference)** | `?job=1159` → Back to validate & resolve | Full `CanonicalColumnMappingPanel` on step 5 in wizard (not re-captured this pass; prior code-read reference **3505–3518**). | Unchanged code evidence |

**HL thin-mount parity finding (code + data):** Implementation passes only `testIdPrefix`, `fileHeaders`, `draft`, `targetOptions`, `dirty` — no `columnSamples`, `requiredGroups`, `blockingErrors`, or disposition column. **Cannot refute or confirm in live UI** until a validated HL job exists on dev DB.

---

## 2026-08-31 cip_test runtime supplement — proof gate + HL + shipment apply

**Collection timestamp:** 2026-08-31 (Monday), ~11:28 UTC+2  
**Script:** `apps/api/scripts/ops/session_e_cip_test_walk.py`  
**Fixture:** `apps/api/scripts/ops/session_e_hl_fixture.xlsx` (1-row Historical Lineup Apr sheet + Summary sheet; seeded dims `DIST-HL-01`, `CUST-HL-01`, `SKU-HL-01`, channel `RET`)  
**Proof gate (pre-write):** `GET /health/ready` → `{"status":"ready","database":"cip_test","ok":true}` with `DATABASE_URL`, `DATABASE_URL_SYNC`, `DATABASE_URL_SYNC_MIGRATE` rewritten via `session_d_run_api.py cip_test`.  
**Post-walk restore:** killed `:8001` listener; `session_d_run_api.py env` → `GET /health/ready` → `"database":"cip"`.

### HL validated job on `cip_test`

| Field | OBSERVED |
|-------|----------|
| Job id | **639** (`HL_JOB_ID` from walk script) |
| `current_database()` | **`cip_test`** on seed + post-validate queries |
| `template_slug` / mode | `historical_lineup` / `validate` |
| `stage` / `status` | `validated` / `completed` |
| File | `session_e_hl_fixture.xlsx` |

### HL mapping panel — live browser (Rule #4 unit 11)

**Goal:** After validate, expand **Column mapping review → Show / edit** and compare panel vs PM (`columnSamples`, `requiredGroups`, `blockingErrors`, disposition column).

| Attempt | OBSERVED | Blocker |
|---------|----------|---------|
| `cursor-ide-browser` | Admin session; HL wizard through provider select → upload step (**Choose file** visible) | **`FILE_CHOOSER_UNAUTOMATABLE`** — no file-input attach in cursor-ide-browser |
| `user-playwright` | Login `admin@local`; same wizard to upload step; **`browser_drop`** on drop zone | **`PLAYWRIGHT_FILE_ROOT`** — fixture path outside MCP allowed roots (`~/.playwright-mcp`, home root only) |
| `browser_run_code_unsafe` | Not run | **`BROWSER_UNSAFE`** — EIF hook denies evaluate/unsafe execution |

**Code finding (CONFIRMED — mount props):** `page.tsx` **4481–4488** passes only `testIdPrefix="hl"`, `fileHeaders`, `draft`, `targetOptions`, `dirty`. PM mount **3163–3181** passes `columnSamples`, `requiredGroups`, `dispositionOptions`, `dispositionDraft`, `onDispositionChange`, `formatSamples`.

**Expected operator-visible panel when mapping review is expanded (from `CanonicalColumnMappingPanel` + HL props — not a verdict):**

| PM feature | HL expected render |
|------------|-------------------|
| Per-column sample values | **`Examples: —`** on each row (`formatSamples` default when `columnSamples` absent); testids `hl-samples-*` present but show em dash |
| Required-group summary chips | **Absent** — only **Mapped:** / **Unmapped:** chips (`requiredGroups` not passed → `groupStatus` empty) |
| Blocking mapping alert | **Absent** — no **Fix mapping before validating** (`blockingErrors` not passed) |
| Disposition / bulk mapping toolbar | **Absent** — table is **File column + Maps to** only (no **Unmapped handling** column; no Apply suggested / All unmapped → Ignore) |
| Show columns filter + mapping table | **Present** (shared panel shell) |

**Manual operator check (to close live-browser gap):** On `cip_test` API (`/health/ready` → `cip_test`), Import Center → Historical lineup → upload `session_e_hl_fixture.xlsx` → validate → expand **Show / edit** under **Column mapping review**. Confirm table matches table above vs PM job **30** step 4.

**AUTOMATION_LIMIT — not a product defect:** live HL mapping snapshot blocked by **`FILE_CHOOSER_UNAUTOMATABLE`** + **`PLAYWRIGHT_FILE_ROOT`**; code mount + component defaults are the corroborating evidence until manual attach succeeds.

### Shipment apply + progress (S10–S11) on `cip_test`

**Job:** **640** (`inbound_shipments`, validate completed; 1 evidence line, 1 mapping candidate). All SQL: **`current_database(): cip_test`**.

| Row | EXPECTED | OBSERVED (runtime) |
|-----|----------|-------------------|
| **S10** | Async dispatch; `{async, task_id}`; job → `running` / apply | **OBSERVED:** `POST /api/v1/shipment-evidence/jobs/640/apply` → **200**; body `async: true`, `task_id: b6a64ac3-b3fd-4fb4-b258-9cd729cec78a`, `status: running`, `import_mode: apply`. Post-dispatch SQL: stage `validated`, status `running`, mode `apply`. |
| **S11** | Progress poll → phases advance → terminal `loaded` / facts written | **PARTIAL:** `GET /api/v1/imports/jobs/640/dsi-progress` **200** for ~90s; repeated payload `phase: processing_rows`, `task_state: STARTED`, `pct: 0`, `pipeline_started_at: null`. Post-poll SQL: still `validated`/`running`/`apply`. `fact_inbound_shipment` rows matching `%SESSION-E-20260831%`: **0**. |

**Interpretation (evidence only):** S10 dispatch contract met; S11 poll endpoint responds but worker did not advance (`STARTED` stall — likely Celery/worker not consuming shipment apply queue in this topology; not diagnosed further this session).

---

## Automation limits (not product defects)

| Item | Reason code | Manual operator check |
|------|-------------|----------------------|
| **S5–S7** steward drawer | **`BROWSER_UNSAFE`** / drawer not opened | Shipment job on `cip_test` or `cip` revisit → **Review…** on a channel-partner row → confirm drawer chrome, evidence body, suggestion cards + override |
| **CDP evaluate** (drawer automation) | **`BROWSER_UNSAFE`** | Same as above without script injection |
| **HL mapping live snapshot** | **`FILE_CHOOSER_UNAUTOMATABLE`** + **`PLAYWRIGHT_FILE_ROOT`** | Upload `session_e_hl_fixture.xlsx` manually; expand **Show / edit**; compare to PM panel checklist above |
| **S11 completion** | **`WORKER_QUEUE_STALL`** (observed `task_state: STARTED`) | Ensure Redis + `pnpm dev:worker` (or `CIP_DEV_CELERY_DISPATCH=in_process_thread`); re-apply job **640**; poll until `loaded` and fact row count > 0 |

---

## 2026-08-31 browser supplement — Shipment steward (job 1159)

**URL:** `http://127.0.0.1:3000/admin/imports?job=1159` → **Back to validate & resolve** (completed job defaults to Apply step 7; button returns to step 6).

**OBSERVED (operator-visible, admin@local):**

- Green banner: *Validation complete. Resolve distributor and channel partner tokens below, then continue to Apply.*
- Plan toolbar: **Refresh plan**, chips **Candidates 15 / Ready 4 / Needs work 11 / On hold 0**, **Apply all ready (4)**, **Resolution plan options**
- Entity tabs: **Distributors (0)** | **Channel partners (15, 15 needs work)** — selected tab shows **Showing 1–15 of 15 candidates**, **Rows per page 100**
- Chip filters: Plan/match (**All**, Needs review, Ready to map, Provisional, No match) + Refine (**Verify name**, Special category, Duplicate review needed); **Clear filters**
- Bulk toolbar: Bulk map…, Bulk provisional…, Select visible ready, Apply selected (0)
- Sample row (Channel partners): token **TB-Ecole Du Centre** / key `ecole du centre`; Rows **2**; Qty/value **55 / 26275**; Suggested **Ecole Du Centre**; Plan chip **Map to customer** + Ready **score 0.95**; Match **Needs review** / Partial Customer Alias Coverage; **Review…** action
- Footer wizard: Re-run import validation (server), Back, Re-run validation, **Continue to apply**

**Not observed in browser:**

- Steward **drawer** open (row Review click not completed; **`browser_cdp` Runtime.evaluate blocked `BROWSER_UNSAFE`**)
- Live **apply/progress** poll on `cip_test` (**`CIP_TEST_NOT_EXECUTED`**)

---

## S1–S14 steward contract matrix

Contract source: `docs/STEWARD_EXPERIENCE_CONTRACT.md` v1.6 slot inventory (**lines 23–38**).

Grading applies primarily to **ShipmentImportJobResolutionSection**. PM and HL have **no steward resolution section** on Import Centre — steward slots **ABSENT** on those surfaces unless noted.

| ID | EXPECTED (contract) | Shipment steward OBSERVED (browser 2026-08-31 where noted) | Code-read grade | Browser grade note |
|----|---------------------|-----------------------------------------------------------|-----------------|-------------------|
| **S1** | Two-column viewport shell; drawer beside list | Step 6 workspace with candidate table + plan toolbar; drawer not opened | PASS-equivalent | Browser: workspace **OBSERVED**; drawer **NOT OPENED** |
| **S2** | Entity tabs + counts; tab switch resets filters to default | Tabs **Distributors (0)** / **Channel partners (15, 15 needs work)** with counts | PARTIAL | Browser **confirms tabs/counts**; filter reset on tab switch **not exercised** |
| **S3** | Chip filters + list search debounced 300ms | Chip filters + Clear filters **OBSERVED**; **no** free-text search field on list | PARTIAL | Browser **confirms chips-only** (matches code-read gap) |
| **S4** | Token, counts, plan_class, confidence band, units/value | Token, Rows, Qty/value, Suggested, Plan chip + **numeric score 0.95** (not band chip) | PARTIAL | Browser **confirms numeric score** on plan column |
| **S5** | Drawer chrome | Drawer not opened | PASS-equivalent | **`AUTOMATION_LIMIT`** **`BROWSER_UNSAFE`** — manual Review… click |
| **S6** | Drawer evidence body | Drawer not opened | PASS-equivalent | **`AUTOMATION_LIMIT`** **`BROWSER_UNSAFE`** |
| **S7** | Suggestion cards + override | Drawer not opened | PASS-equivalent | **`AUTOMATION_LIMIT`** **`BROWSER_UNSAFE`** |
| **S8** | Bulk preview → apply | Bulk map / Bulk provisional / Select visible ready **OBSERVED** (disabled at default selection) | PASS-equivalent | Browser: toolbar **OBSERVED**; preview dialog **not triggered** |
| **S9** | Plan toolbar apply-all-ready | **Apply all ready (4)** + Resolution plan options **OBSERVED** | PASS-equivalent | Browser: plan toolbar **OBSERVED** |
| **S10** | Async dispatch apply | **OBSERVED on cip_test job 640** — async 200 + task_id | PASS-equivalent *(code)* | **Runtime OBSERVED** dispatch; see cip_test supplement |
| **S11** | Progress poll + bell | **PARTIAL on cip_test** — poll 200, phase stuck `STARTED` | PASS-equivalent *(code)* | **Runtime PARTIAL** — no terminal `loaded`; 0 fact rows |
| **S12** | Server pagination | **Showing 1–15 of 15**; Rows per page combobox **OBSERVED** | PASS-equivalent | Browser **OBSERVED** |
| **S13** | Action feedback alerts | No plan-apply or bulk error banner triggered | PASS-equivalent *(code)* | Browser: **not triggered** |
| **S14** | No auto-create; reviewable ambiguity | Match column **Needs review** / alias coverage copy **OBSERVED** | PASS-equivalent | Browser **OBSERVED** on sample row |

---

## Per-row OBSERVED vs EXPECTED notes (shipment steward — retained from code read)

*(2026-08-30 code paths remain authoritative where browser did not exercise the slot. See 2026-08-31 supplement above for live observations on S1–S4, S8–S9, S12, S14.)*

### S10 — Async dispatch

- **OBSERVED (runtime, cip_test job 640):** `POST …/jobs/640/apply` → **200**, `async: true`, `task_id: b6a64ac3-b3fd-4fb4-b258-9cd729cec78a`. SQL after dispatch: `current_database(): cip_test`; job `running` / `apply`.

### S11 — Progress

- **OBSERVED (browser 2026-08-31 AM):** Validation-complete banner on job **1159** revisit; no async validate poll captured that session.
- **OBSERVED (runtime, cip_test job 640):** `GET …/dsi-progress` **200** for ~90s; `phase: processing_rows`, `task_state: STARTED`, `pct: 0`; job never reached `loaded`; **0** `fact_inbound_shipment` rows for SESSION-E stamp. SQL: `current_database(): cip_test`.

---

## PM / HL mapping surfaces — steward slot summary

| Slot | PM | HL |
|------|----|----|
| S1–S13 | **ABSENT** (mapping-only) | **ABSENT** (mapping review only when validated job exists) |
| S14 | API/import governance | Same |
| Rule #4 mapping | **OBSERVED full panel** on job **30** step 4 | **Code CONFIRMED thin mount**; **browser PARTIAL** (upload blocked); job **639** on `cip_test`. Manual: upload + **Show / edit**. |

---

## Browser session log

### 2026-08-30 (prior pass)

1. Playwright → `/admin/imports` redirected to login; guard blocked follow-ups.
2. No authenticated mapping/steward surfaces captured.

### 2026-08-31 (supplement)

1. `cursor-ide-browser` @ `http://127.0.0.1:3000` — admin session active.
2. Shipment job **1159**: Apply step → **Back to validate & resolve** → full steward workspace with 15 channel-partner candidates.
3. PM job **30**: revisit wizard → **Back** to column mapping → full `CanonicalColumnMappingPanel` with samples and dispositions.
4. PM job **95** with `?template=product_master`: read-only revisit — **`PM_REVISIT_READONLY`**.
5. `?template=historical_lineup`: no HL jobs on `cip` — **`HL_NO_JOBS_ON_CIP`**.
6. Drawer open / CDP evaluate: **`BROWSER_UNSAFE`** → **`AUTOMATION_LIMIT`** (S5–S7).

### 2026-08-31 cip_test (runtime + browser partial)

1. Proof gate: `session_d_run_api.py cip_test` → health `"database":"cip_test"`.
2. `session_e_cip_test_walk.py`: HL job **639**, shipment job **640**; S10 dispatch OK; S11 poll stuck `STARTED`.
3. `cursor-ide-browser`: HL wizard to upload — **`FILE_CHOOSER_UNAUTOMATABLE`**.
4. `user-playwright`: HL wizard to upload — **`PLAYWRIGHT_FILE_ROOT`** on drop.
5. Restore: `session_d_run_api.py env` → health `"database":"cip"`.

---

## Apply / progress exercise (`cip_test`)

**Planned:** Stop API; `python scripts/ops/session_d_run_api.py cip_test`; `session_d_poll_health.py` must print `"database":"cip_test"`; exercise steward apply + progress; restore `env` mode; confirm `"database":"cip"`.

**OBSERVED (2026-08-31 ~11:28):** **EXECUTED.** Shipment job **640** on `cip_test`. S10 dispatch **OBSERVED**; S11 poll **PARTIAL** (worker stall). HL job **639** seeded; mapping panel live snapshot **not captured** (automation limits). Post-walk: health → `"database":"cip"`.

**OBSERVED (2026-08-31 AM supplement):** **NOT EXECUTED (`CIP_TEST_NOT_EXECUTED`).** Read-only proof only on `cip`.

---

## Contract / memory discrepancies

| Source | Branch claim |
|--------|--------------|
| Git (2026-08-31 cip_test) | @ `b88657a` |
| Git (2026-08-31 AM) | @ `8f3c10f` |
| Git (2026-08-30) | @ `3f10ae4` |
| `docs/memory/CURRENT.md` (historical) | May lag branch field — pin VERIFY to git |

---

## Summary — evidence gaps (not verdicts)

| Code | Browser 2026-08-31 | cip_test 2026-08-31 | Outstanding |
|------|----------------------|----------------------|-------------|
| S2, S3, S4 PARTIAL | Partial gaps **confirmed** on live shipment steward | — | Tab-filter reset; list search; confidence bands |
| PM mapping PASS-equivalent | **OBSERVED** full panel job **30** | — | — |
| HL mapping thin mount | Upload step only (**FILE_CHOOSER**) | Job **639** seeded; code **CONFIRMED** | Manual **Show / edit** snapshot |
| Steward drawer S5–S7 | **`AUTOMATION_LIMIT`** | **`AUTOMATION_LIMIT`** | Manual Review… |
| S10 apply dispatch | **`CIP_TEST_NOT_EXECUTED`** (AM) | **OBSERVED** job **640** | — |
| S11 progress completion | Not exercised (AM) | **PARTIAL** — worker stall | Worker topology + re-run apply |

**Import mapping (Rule #4):** PM **OBSERVED full**; HL **code CONFIRMED thin mount**; live HL panel **AUTOMATION_LIMIT** (not refuted).

---

*Evidence-only — no VERDICT. For Opus CONSULT.*

---

## 2026-08-31 Unit 11 fix pass — HL mapping parity + S11 stall (main @ ba0d46c)

**Collection timestamp:** 2026-08-31 (Monday), ~14:07–14:35 UTC+2  
**Branch:** `main` @ `ba0d46cc509069a707eb44102ae561cbc47b97ab` (`git rev-parse HEAD`)  
**Fix scope:** Opus CONSULT second-pass FAIL pillars — HL `CanonicalColumnMappingPanel` mount parity + S11 worker/API DB binding proof + re-run apply on `cip_test`.

### Proof gate + restore

| Step | OBSERVED |
|------|----------|
| Pre-write | `session_d_run_api.py cip_test` → `GET /health/ready` → `"database":"cip_test"` |
| All SQL writes | `current_database(): cip_test` printed on every block |
| Post-fix restore | Kill `:8001`; `session_d_run_api.py env` → `session_d_poll_health.py` → **HTTP 200** `{"status":"ready","database":"cip","ok":true}` |

---

### Finding 1 — HL mapping parity (Rule #4)

#### Before mounts (code at FAIL baseline)

**PM reference** (`page.tsx` **3185–3203**):

```tsx
<CanonicalColumnMappingPanel
  testIdPrefix="pm"
  fileHeaders={pmJobState.file_headers}
  draft={pmMapDraft}
  onChange={(next) => setPmColumns((prev) => applyPmTargetDraft(prev, next))}
  targetOptions={pmCanonicalTargetOptions}
  columnSamples={pmColumnSamples}
  columnNotes={pmColumnNotes}
  requiredGroups={pmRequiredGroups}
  dispositionOptions={[ ... ]}
  dispositionDraft={pmDispositionDraft}
  onDispositionChange={(next) => setPmColumns((prev) => applyPmDispositionDraft(prev, next))}
  formatSamples={(samples) => formatPmSamples(samples)}
  dirty={pmMappingDirty}
/>
```

**HL thin mount (FAIL)** — only five props: `testIdPrefix`, `fileHeaders`, `draft`, `targetOptions`, `dirty`.

#### After mounts (fix shipped)

**HL** (`page.tsx` **4503–4515**):

```tsx
<CanonicalColumnMappingPanel
  testIdPrefix="hl"
  fileHeaders={hlSourceColumns}
  draft={hlMapDraft}
  onChange={setHlMapDraft}
  targetOptions={hlCanonicalTargetOptions}
  columnSamples={hlColumnSamples}
  columnNotes={hlColumnNotes}
  requiredGroups={HL_MAPPING_REQUIRED_GROUPS}
  blockingErrors={hlBlockingErrors}
  formatSamples={formatDsiSamples}
  dirty={hlHasEdits}
/>
```

#### Backend data for `columnSamples`

- `historical_lineup.py`: `_collect_column_samples()` → `selected_sheet_details[].column_samples` in `inferred_schema`.
- Job **642** on `cip_test` (`session_e_hl642_samples.py`):

```json
{
  "Customer": ["CUST-HL-01"],
  "Distributor": ["DIST-HL-01"],
  "SKU": ["SKU-HL-01"],
  "Qty": ["12"],
  "MSRP": ["100"],
  "Period": ["2026-04-01"],
  "Channel": ["RET"],
  "Promo Price": ["90"],
  "Disti Margin": ["8"],
  "Notes": ["SESSION E valid row"]
}
```

(`current_database(): cip_test` on query.)

#### Backend gap — disposition props (not faked)

HL apply/validate uses **`mapping_override` only**; there is no PM-style per-column disposition channel (`ignore` / `stage_raw` / `attribute_candidate`) in the HL API payload. **`dispositionOptions` / `dispositionDraft` / `onDispositionChange` intentionally omitted** — document as **backend gap**, not a frontend stub.

#### Automated tests (fix pass)

| Suite | Command | Result |
|-------|---------|--------|
| API HL import | `pytest tests/test_historical_lineup_import.py` (`ALLOW_TESTS_ON_DEV_DB=1`) | **22 passed** |
| HL helpers | `vitest run hlMappingHelpers.test.ts` | **5 passed** |
| HL page mapping panel | `vitest run page.test.tsx -t "mapping review panel"` | **6 passed** (incl. samples + required-group chips + blocking errors) |

#### Browser evidence — job 642 on `cip_test` API

**URL:** `http://127.0.0.1:3000/admin/imports?job=642` → **Column mapping review → Show / edit** (`cursor-ide-browser`, origin `127.0.0.1:3000`).

**OBSERVED (operator-visible):**

- Summary chips: **Mapped: 6**, **Unmapped: 4**, **Product identity: OK** (required-group chip — was absent on thin mount).
- **Customer** row: green `Customer (customer_token)` badge; **Examples: CUST-HL-01** (was em dash); Target **Customer (customer_token)**.
- **Distributor** row: **Examples: DIST-HL-01**.
- No disposition column (expected — backend gap above).

Browser capture filename: `hl-job642-mapping-expanded.png` (cursor-ide-browser screenshot, 2026-08-31 fix pass).

---

### Finding 2 — S11 stall (job 640) — binding proof + re-run

#### Original stall (job 640, pre-fix evidence — retained)

| Field | OBSERVED |
|-------|----------|
| Apply | `POST …/jobs/640/apply` → **200**, `async: true`, `task_id: b6a64ac3-b3fd-4fb4-b258-9cd729cec78a` |
| Progress poll ~90s | `phase: processing_rows`, `task_state: STARTED`, `pct: 0` |
| Terminal | Job stuck `validated`/`running`/`apply`; **`fact_inbound_shipment` count = 0** (`current_database(): cip_test`) |

#### Worker vs API DB binding (`session_e_s11_proof.py` — printed evidence)

```
.env DATABASE_URL_SYNC dbname=cip   (default Celery worker startup)
GET /health/ready → "database":"cip_test"   (API proof gate)
BINDING_MISMATCH: API on cip_test but worker .env default is cip
```

**Ruling (evidence):** Job **640** stall is explained by **topology mismatch** (API dispatching against `cip_test` while worker `.env` defaults to `cip`) — **not a product defect** in apply/progress code when worker is aligned.

#### Re-run with worker on `cip_test` (fix pass)

Worker started via `session_e_run_worker_cip_test.py` (DATABASE_* rewritten to `cip_test`). Apply re-run via `session_e_s11_proof.py`:

| Job | Apply | Phase transitions | Final | `fact_inbound_shipment` |
|-----|-------|-------------------|-------|-------------------------|
| **641** | 200 + task_id | `processing_rows`/STARTED/0% → **`complete`/100%** | `loaded`/`completed` | **1** |
| **643** | 200 + task_id | same pattern | `loaded`/`completed` | **1** |
| **644** (fix-pass script) | 200 + task_id `fa53963d-…` | single poll **`complete`/100%** | `loaded`/`completed` | **1** (`current_database(): cip_test`) |

**Conclusion:** With API + worker both on `cip_test`, S11 reaches terminal **`complete`/100%**, job **`loaded`**, and writes **1** fact row. No product defect observed when binding is correct.

---

### Fix-pass summary table (Opus CONSULT pillars)

| Pillar | Pre-fix FAIL | Post-fix evidence |
|--------|--------------|-------------------|
| HL Rule #4 thin mount | 5 props only; Examples em dash | Full mount + backend `column_samples`; browser **CUST-HL-01** / **DIST-HL-01**; tests green |
| HL disposition parity | N/A | **Backend gap** — disposition channel not in HL API |
| S11 stall | STARTED/0%, 0 facts | **BINDING_MISMATCH** explains job 640; jobs **641/643/644** complete with facts on aligned worker |

*Evidence-only — no VERDICT. For Opus CONSULT re-review.*

---

## Run 2026-08-31 — Unit 11 S2/S3/S4 code fixes + steward browser (main @ 874103b)

**Collection timestamp:** 2026-08-31 (Monday), ~15:30 UTC+2  
**Branch:** `main` @ `874103b`  
**Origin:** `http://127.0.0.1:3000` (cursor-ide-browser + user-playwright, serial)  
**Write target:** `cip_test` (proof gate before shipment walk; API restored to `cip` after)  
**Evidence only — no PASS verdict.**

### Part 1 — S2/S3/S4 fixes (before → after)

| Slot | Before (quoted) | After |
|------|-----------------|-------|
| **S2** | Tab switch kept per-tab chip filters (`filtersByTab`); no reset | `shipmentStewardFiltersAfterTabSwitch()` on tab change + importJob change clears filters and search |
| **S3** | Chip filters only; no list search | `data-testid="shipment-steward-search"` + 300ms debounce (`debouncedSearch`) + `filterShipmentStewardRowsBySearch` |
| **S4** | Plan column raw `score {n}` | `ShipmentPlanConfidenceBandCell` uses shared `confidenceBand.ts` thresholds (high ≥0.90, medium ≥0.70, low &lt;0.70) with band chip + numeric score |

**Band vocabulary source:** `apps/web/src/features/import-steward/confidenceBand.ts` (`confidenceBand`, `confidenceBandLabel`, `confidenceBandColor`).

### Part 1 — automated tests

```text
cd apps/web
pnpm exec vitest run \
  "src/app/(app)/admin/shipment-evidence/shipmentEntityTabs.test.ts" \
  "src/app/(app)/admin/shipment-evidence/shipmentStewardListSearch.test.ts" \
  "src/app/(app)/admin/shipment-evidence/shipmentResolutionWorkspaceTableProps.test.tsx"

Test Files  3 passed (3)
     Tests  6 passed (6)
```

### Part 2 — browser steward walk (`cip_test`, job **641**)

**Proof gate:** `GET /health/ready` → `"database":"cip_test"` (`session_d_run_api.py cip_test`).  
**Route:** `/admin/imports?job=641` (no `?template=` — wizard hydration requires job-only deep link).  
**Flow:** Apply step → **Back to validate & resolve** → steward list.

| Slot | OBSERVED |
|------|----------|
| **S2** | Selected **No match** on Distributors → switched to **Channel partners** → **Clear filters** disabled; **No match** not active (filters reset) |
| **S3** | **Search candidates…** visible; typed `SESSION-E` slowly; row `SESSION-E-20260831-DIST` visible |
| **S4** | Distributor no-match row has no plan score in a11y tree; band chip covered by unit test + `confidenceBand.ts` contract (live band visible when plan carries numeric score) |
| **S5–S7** | **Review…** opened drawer: Close steward drawer, Apply plan, Map/Prov/Special/Reject, Evidence, Suggested masters |

**Screenshots:** `docs/verify/artifacts/session-e-unit11-s2-s3-s4-steward.png`, `session-e-unit11-s5-s7-drawer.png`

**Post-session restore:** `session_d_run_api.py env` → `GET /health/ready` → `"database":"cip"`.
