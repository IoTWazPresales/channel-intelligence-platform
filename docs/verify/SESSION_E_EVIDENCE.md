# SESSION E Evidence — Unit 11 import parity

**Collection timestamp:** 2026-08-30 (Sunday), ~20:38 UTC+2 — **supplemented 2026-08-31 ~10:45 UTC+2**  
**Collector:** Cursor agent (VERIFY run + SESSION E continuation)  
**Branch (verified):** `feat/ns-1a-fx-readiness-chips` @ `8f3c10f` (`git rev-parse --short HEAD` on 2026-08-31)  
**Contract version (file):** **1.6 · 2026-07-27 · Owner: Warren** — matches seed expectation  
**Environment:** local Windows; web `:3000`, API `:8001`; `session_d_poll_health.py` → `"database":"cip"`  
**Database policy:** read-only queries on `cip` with `current_database()` printed; apply/progress on `cip_test` **not executed**  
**Waiver lines from unit prompt:** *(none supplied — all S1–S14 in scope)*

**Surfaces in scope (operator):**

1. `/admin/imports` — Product Master (`product_master`) `CanonicalColumnMappingPanel`
2. `/admin/imports` — Historical Lineup (`historical_lineup`) `CanonicalColumnMappingPanel`
3. `ShipmentImportJobResolutionSection` — full steward flow (Import Centre step 6 revisit for job **1159**)

**Evidence-only artifact for Opus CONSULT.** No `VERDICT:` line in this file.

---

## Collection methods

| Method | Result (2026-08-30) | Result (2026-08-31 supplement) |
|--------|---------------------|--------------------------------|
| Code read (`Read` / `Grep`) | **Succeeded** | **Succeeded** (unchanged) |
| `git rev-parse` / branch | **Succeeded** @ `3f10ae4` | **Succeeded** @ `8f3c10f` |
| Playwright MCP | **Partial** — login redirect; guard blocked follow-ups | Not used |
| `cursor-ide-browser` MCP | **Blocked** by EIF guard | **Succeeded** — admin authenticated at `http://127.0.0.1:3000` |
| Apply/progress on `cip_test` | **Not executed** | **Not executed** — see **`CIP_TEST_NOT_EXECUTED`** |
| Read-only DB (`SessionLocal`) | Not run | **`current_database(): cip`**; **`historical_lineup` import_job rows: (none)** |

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
| **S5** | Drawer chrome | Drawer not opened | PASS-equivalent | Browser: **NOT OPENED** |
| **S6** | Drawer evidence body | Drawer not opened | PASS-equivalent | Browser: **NOT OPENED** |
| **S7** | Suggestion cards + override | Drawer not opened | PASS-equivalent | Browser: **NOT OPENED** |
| **S8** | Bulk preview → apply | Bulk map / Bulk provisional / Select visible ready **OBSERVED** (disabled at default selection) | PASS-equivalent | Browser: toolbar **OBSERVED**; preview dialog **not triggered** |
| **S9** | Plan toolbar apply-all-ready | **Apply all ready (4)** + Resolution plan options **OBSERVED** | PASS-equivalent | Browser: plan toolbar **OBSERVED** |
| **S10** | Async dispatch apply | Not exercised | PASS-equivalent *(code)* | **`CIP_TEST_NOT_EXECUTED`** |
| **S11** | Progress poll + bell | Validation-complete state on revisit; no live poll captured | PASS-equivalent *(code)* | Progress poll **not exercised** |
| **S12** | Server pagination | **Showing 1–15 of 15**; Rows per page combobox **OBSERVED** | PASS-equivalent | Browser **OBSERVED** |
| **S13** | Action feedback alerts | No plan-apply or bulk error banner triggered | PASS-equivalent *(code)* | Browser: **not triggered** |
| **S14** | No auto-create; reviewable ambiguity | Match column **Needs review** / alias coverage copy **OBSERVED** | PASS-equivalent | Browser **OBSERVED** on sample row |

---

## Per-row OBSERVED vs EXPECTED notes (shipment steward — retained from code read)

*(2026-08-30 code paths remain authoritative where browser did not exercise the slot. See 2026-08-31 supplement above for live observations on S1–S4, S8–S9, S12, S14.)*

### S10 — Async dispatch

- **OBSERVED (runtime):** Apply/progress exercise **NOT EXECUTED** on `cip_test`. Pre-write proof gate requires `/health/ready` → `"database":"cip_test"` with all three `DATABASE_URL*` vars rewritten (`docs/VERIFY_DEBT_RUNBOOK.md`). Live API at collection: `"database":"cip"` only.

### S11 — Progress

- **OBSERVED (browser):** Validation-complete banner on job **1159** revisit; no async validate poll captured this session.

---

## PM / HL mapping surfaces — steward slot summary

| Slot | PM | HL |
|------|----|----|
| S1–S13 | **ABSENT** (mapping-only) | **ABSENT** (mapping review only when validated job exists) |
| S14 | API/import governance | Same |
| Rule #4 mapping | **OBSERVED full panel** on job **30** step 4 | **Code PARTIAL**; **browser UNABLE_TO_RENDER** — **`HL_NO_JOBS_ON_CIP`** |

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
6. Drawer open / CDP evaluate: **`BROWSER_UNSAFE`**.

---

## Apply / progress exercise (`cip_test`)

**Planned:** Stop API; `python scripts/ops/session_d_run_api.py cip_test`; `session_d_poll_health.py` must print `"database":"cip_test"`; exercise steward apply + progress; restore `env` mode; confirm `"database":"cip"`.

**OBSERVED:** **NOT EXECUTED (`CIP_TEST_NOT_EXECUTED`).** Read-only proof only: `session_d_poll_health.py` on running stack → `{"status":"ready","database":"cip","ok":true}`. No HTTP write against `cip_test`.

---

## Contract / memory discrepancies

| Source | Branch claim |
|--------|--------------|
| Git (2026-08-31) | `feat/ns-1a-fx-readiness-chips` @ `8f3c10f` |
| Git (2026-08-30) | @ `3f10ae4` |
| `docs/memory/CURRENT.md` (historical) | May lag branch field — pin VERIFY to git |

---

## Summary — evidence gaps (not verdicts)

| Code | Browser 2026-08-31 | Outstanding |
|------|----------------------|-------------|
| S2, S3, S4 PARTIAL | Partial gaps **confirmed** on live shipment steward | Tab-filter reset behavior; list search; confidence bands |
| PM mapping PASS-equivalent | **OBSERVED** full panel job **30** | — |
| HL mapping PARTIAL | **UNABLE_TO_RENDER** — no HL jobs | Seed validated HL job or use env with HL data |
| Steward drawer S5–S7 | **NOT OPENED** | Manual Review… click or unblocked drawer automation |
| S10–S11 apply/progress | **`CIP_TEST_NOT_EXECUTED`** | Full proof gate + apply on disposable DB |

**Import mapping (Rule #4):** PM **OBSERVED full**; HL **code PARTIAL**, **browser blocked by data**.

---

*Evidence-only — no VERDICT. For Opus CONSULT.*
