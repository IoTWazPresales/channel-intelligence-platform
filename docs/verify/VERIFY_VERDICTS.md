# VERIFY Verdicts — Units 6f, 7, 8, 11, 12, 15B, B4

**Verifier:** Independent CONSULT (did not produce session evidence)  
**Charter:** v1.3 amendment 7 — only `VERDICT: PASS` closes a register row  
**Branch reviewed:** `feat/ns-1a-fx-readiness-chips` @ `0276f50` (verifier HEAD)  
**Evidence inputs:** `docs/VERIFY_DEBT_RUNBOOK.md`, `docs/verify/SESSION_{C,D,E,F}_EVIDENCE.md`, `.tmp_session_a_*` / `.tmp_session_b_*` artifacts, code tree at HEAD  
**Missing inputs (noted):** `docs/verify/SESSION_A_EVIDENCE.md` and `SESSION_B_EVIDENCE.md` **do not exist** in the repo; `docs/verify/WEB_TEST_FAILURE_DIAGNOSIS.md` **does not exist** (CONTEXT references it; diagnosis recovered from CONTEXT + Session B failure log + current vitest re-run)

**Independent re-runs at verdict time (2026-08-31):**

- `pytest` scoped suites: **55 passed** (6f, 7, 12, 15B, B4, shipment steward, PM retired)
- `vitest` scoped (forecasts, promotions, imports page, shipment steward panel): **34 passed**

---

## Summary

| Unit | Verdict | Primary blockers |
|------|---------|------------------|
| **6f** | **FAIL** | Browser operator Accept path not evidenced; register requires browser smoke |
| **7** | **FAIL** | Rendered strip labels + live PvE fill % never captured in browser |
| **8** | **PASS** | A1–A8 + B1–B4 satisfied; A3 closed via documented ops equivalent |
| **11** | **FAIL** | S11 runtime incomplete; S2/S3/S4 contract PARTIAL; HL mapping thin mount vs parity bar |
| **12** | **FAIL** | No browser `/settings` persistence evidence; Unit 11 regression gate fails |
| **15B** | **FAIL** | No browser compute-from-history on `cip_test`; only direct-Python substitute |
| **B4** | **FAIL** | No browser dirty-MAC Refresh journey; create-case proven on `cip_test` only via service layer |

---

## Unit 6f — D-040 distributor attribution propose→confirm

### Contract rows

| ID | Requirement | Evidence | Ruled |
|----|-------------|----------|-------|
| **D-040** | `token_proposed` → `shipment_confirmed` / `steward_set` / `conflict`; Accept ship-corroborated; soft-clear; Phase-1 confirmer exact qty; **no auto-clear on conflict** | Session D `cip_test` HTTP + SQL (case 43, lines 22–24): Accept → `steward_set` + audit `lineup_ship_corroborated_distributor_accept`; soft-clear → `distributor_id` NULL; confirmer ×2 → stays `conflict`, `distributor_id=94` | **Evidenced** (API/`cip_test`, not browser) |
| **D-038 amend** | Dual-write OPEN_CHANNEL + line `distributor_id` on token stamp | Accept audit cites `dim_distributor` 92; not re-proven end-to-end in browser | **Partial** |
| **BACKLOG register** | Browser smoke Proposed (case 1016 or substitute) | Section chrome renders (`SESSION_D`); proposed rows empty when review API 500; **no browser Accept click**; substitute case 7 on `cip` read-only only | **Unevidenced** (browser write path) |

### Automated (Session A artifacts + verifier)

| Check | Evidence | Ruled |
|-------|----------|-------|
| `tests/test_lineup_distributor_attribution.py` | `.tmp_session_a_unit6f.txt`: **10/10 passed**; verifier **10/10 passed** | **PASS** |

### Browser / operator

| Check | Evidence | Ruled |
|-------|----------|-------|
| `/admin/po-management` → Proposed → Accept | Not performed in browser; Session D used `POST .../accept-ship` on `cip_test` after proof gate | **FAIL** — register and runbook require operator Accept smoke |
| Case 1016 | Absent on `cip`; substitute case 7 identified read-only | N/A — substitute acceptable only with exercised Accept |

### Data

| Check | Evidence | Ruled |
|-------|----------|-------|
| Read-only status distribution + audit baseline | Session D pre-action audit through 2026-08-08 | **Evidenced** |
| Post-action on `cip` | No browser write on `cip` (policy-correct) | N/A |

**VERDICT: FAIL** — D-040 transition semantics are proven on disposable `cip_test` via HTTP/SQL, but the VERIFY register and runbook require **browser operator Accept**. Backend proof does not substitute for UI smoke under charter amendment 7 and `smoke-via-browser.mdc`.

---

## Unit 7 — BACKLOG-068 shipping lineup-quarter strip

### Contract rows

| ID | Requirement | Evidence | Ruled |
|----|-------------|----------|-------|
| **BACKLOG-068** | `landed_this_quarter_units` + `shipped_not_landed_units`; PvE fill **unchanged** (shipped-basis) | Service layer `26Q2`: `shipped_not_landed_units=10`, `landed_this_quarter_units=39074` (Session D); fill formula unchanged git blame Session D | **Partial** — service only |
| **SH-01 / SH-02** | Lifecycle cohort semantics (`docs/COMMERCIAL_SEMANTICS.md` §4.2) | `tests/test_inbound_lineup_quarter.py`: **12/12 passed** including `test_accumulate_landed_this_quarter_vs_plan_landed` | **PASS** (automated) |

### Browser

| Check | Evidence | Ruled |
|-------|----------|-------|
| `/shipping` strip labels **"Shipped (awaiting POD)"**, **"Landed this quarter"** | Session D: API 500 / no quarter selected; labels in TSX source only (`ShippingLineupQuarterSummary.tsx`); **no rendered snapshot** | **FAIL** |
| `/plan-vs-executed` fill % unchanged | Session D: scorecard API 500; fill **not visible** in browser; Session D analysis: today `6352/32509=19.5%` vs gate **13.2%** = **data moved**, not formula regression | **Partial** — analysis only, not live UI |
| `GET /api/v1/shipping/lineup-quarter-summary?plan_quarter=26Q3` | Not collected live (Session D browser degraded) | **Unevidenced** (HTTP) |

### Fill-rate discrepancy (Session D Task 1)

Git shows `plan_vs_executed.py` fill formula unchanged since before 2026-08-14 pin. **Not a Unit 7 calculation regression.** Gate stored percentage without numerator/denominator; today’s components produce 19.5%. Does not satisfy browser strip requirement.

**VERDICT: FAIL** — Automated SH-01/SH-02 logic passes; **mandatory browser strip labels and live PvE fill display are unevidenced** across Sessions D and C.

---

## Unit 8 — Demo / P2 gate (P2-3 Auth + RBAC, P2-5 Backup/DR)

### Contract rows

| ID | Requirement | Evidence | Ruled |
|----|-------------|----------|-------|
| **P2-3 / gate A1–A8** | Login, RBAC, second-user landing, default-deny admin | Session C 2026-08-31 browser supplement | See A-table |
| **P2-5 / gate B1–B4** | Backup → restore `cip_alembic_smoke`; live `cip` unchanged | `RESTORE_SMOKE_OK`; `dim_product=18177`; live `cip` unchanged | **PASS** |

### Gate A1–A8 (Session C 2026-08-31)

| Step | Evidence | Ruled |
|------|----------|-------|
| A1 Create-user form | Observed admin `/admin/users` | **PASS** |
| A2 viewer@local exists | Table row Smoke Viewer / viewer / yes | **PASS** |
| A3 Reset password ≥8 chars | **`AUTOMATION_LIMIT` `PROMPT_DIALOG_UNAUTOMATABLE`** — `window.prompt`; ops stdin reset on `cip` documented; viewer login succeeds in A5 with `changeme1` | **PASS via ops equivalent** (see Automation Limits) |
| A4 Logout → `/login` | Observed | **PASS** |
| A5 Viewer `/dashboard` | Control tower + Welcome + freshness stale copy; **`NS-2_GATE_REWRITE` flag** (run as written per runbook) | **PASS** |
| A6 Viewer data grid | `/shipping` **1–50 of 14724** (not loading-only); flag NS-2 route | **PASS** |
| A7 Viewer `/admin/users` forbidden | Alert Admin role required | **PASS** |
| A8 Forgot-password copy | Verbatim admin Reset password pointer | **PASS** |

### Gate B1–B4

| Step | Evidence | Ruled |
|------|----------|-------|
| B1 backup | `.tmp/backups/cip_20260831_103216.dump` 119737682 bytes | **PASS** |
| B2–B3 restore smoke | `RESTORE_SMOKE_OK database=cip_alembic_smoke ... alembic=20260818_0019` | **PASS** |
| B4 live `cip` unchanged | `current_database(): cip`; `dim_product=18177` before/after | **PASS** |

**VERDICT: PASS**

---

## Unit 11 — Import parity (BACKLOG-026 / 027 / 044 + S1–S14)

**Contract version:** `docs/STEWARD_EXPERIENCE_CONTRACT.md` **v1.6** — matches seed template.  
**Waiver lines in unit prompt:** none — all S-rows in scope.

### Backlog / Rule #4 mapping rows

| ID | Requirement | Evidence | Ruled |
|----|-------------|----------|-------|
| **BACKLOG-026** | Generic PM pipeline retired | `tests/test_product_master_pipeline_retired.py` green; verifier included in 55-pass run | **PASS** |
| **BACKLOG-027** | PM + HL → `CanonicalColumnMappingPanel` | PM: browser job **30** full panel (Session E); HL: `page.tsx` **4481–4488** thin props only | **PM PASS; HL FAIL** (see parity ruling) |
| **BACKLOG-044** | Shipment steward parity vs DSI/shipment bar | `ShipmentImportJobResolutionSection` mounts shared engine; S-row gaps below | **FAIL** |

### HL vs PM `CanonicalColumnMappingPanel` parity (confirmed finding)

**Code at HEAD (`page.tsx`):**

- PM **3163–3181:** `columnSamples`, `columnNotes`, `requiredGroups`, `dispositionOptions`, `dispositionDraft`, `onDispositionChange`, `formatSamples`
- HL **4481–4488:** `testIdPrefix`, `fileHeaders`, `draft`, `targetOptions`, `dirty` only
- Reference DSI/shipment mounts pass `columnSamples`, `requiredGroups`, `blockingErrors`, `formatSamples` (**3985–4020**, **3505–3518**)

Session E documents expected HL render: Examples em dash, no required-group chips, no disposition column, no blocking alert.

**Ruling:** Unit 11 **FAIL** on BACKLOG-027 / import-parity Rule #4 for HL. Mounting the shared component name is not parity with the DSI/shipment reference bar. BACKLOG-027 “what the work is” explicitly includes **samples** for HL; shipped tree omits them. PM full panel does not excuse HL gap.

### Shipment steward S1–S14 (contract v1.6)

Grading: PASS = behavior evidenced at path:line or live browser; PARTIAL/ABSENT without waiver → unit STOP.

| ID | EXPECTED | Evidence | Grade | Notes |
|----|----------|----------|-------|-------|
| **S1** | Viewport shell | `StewardWorkspaceViewportShell` **446–450**; browser workspace job 1159 Session E | **PASS** | |
| **S2** | Tabs + counts; tab switch resets filters/selection | Tabs/counts browser **OBSERVED**; `onChange={setActiveTab}` **487** — per-tab filter state, **no selection reset on tab change** | **PARTIAL** | No waiver |
| **S3** | Chip filters + **300ms debounced list search** | Chips Session E **OBSERVED**; `StewardCandidateFilters` has **no search field**; debounce only in drawer override (`shipmentStewardRowActions.tsx` **109–114**) | **PARTIAL** | No waiver |
| **S4** | Confidence **band** on list | List column `score {n}` (`shipmentResolutionWorkspaceTableProps.tsx` **68**); band chips in drawer panel only (`ShipmentMappingStewardPanel.tsx` **389–394**); browser shows numeric 0.95 | **PARTIAL** | No waiver |
| **S5** | Drawer chrome | `StewardCandidateDrawer` **607–627** wired; drawer not opened browser | **PASS** (code) | See Automation Limits |
| **S6** | Drawer evidence body | `ShipmentMappingStewardPanel` body inside drawer; not opened browser | **PASS** (code) | See Automation Limits |
| **S7** | Suggestion cards + override | Same panel; drawer override search debounced; not opened browser | **PASS** (code) | See Automation Limits |
| **S8** | Bulk preview → apply | Bulk toolbar Session E **OBSERVED**; preview dialog not triggered | **PASS** (code + partial browser) | |
| **S9** | Plan toolbar apply-all-ready | **Apply all ready (4)** Session E **OBSERVED** | **PASS** | |
| **S10** | Async dispatch `{async, task_id}` | `cip_test` job **640**: POST apply **200**, `async: true`, `task_id` set; `_dispatch_shipment_apply` in `shipment_evidence.py` **95+** | **PASS** | |
| **S11** | Progress poll → terminal loaded + facts | Job **640**: poll **200** ~90s, `phase: processing_rows`, `task_state: STARTED`, `pct: 0`; **0** fact rows; job stuck `running`/`apply` | **FAIL** | See S11 ruling |
| **S12** | Server pagination | **Showing 1–15 of 15** Session E | **PASS** | |
| **S13** | Error surfaces | Not triggered browser | **PASS** (code paths present) | |
| **S14** | No auto-create; reviewable ambiguity | Needs review / alias coverage Session E **OBSERVED** | **PASS** | |

**REQUIRED rows PARTIAL without waiver:** S2, S3, S4 → **`VERDICT: STOP`** per seed template.  
**S11 FAIL** alone is sufficient to fail Unit 11 regardless of automation limits.

### S11 — apply 200 + task_id but progress stall

**Observed (Session E `cip_test` job 640):**

- S10 dispatch contract met (200, async, task_id, job `running`)
- S11 poll responds but **never advances** past `STARTED` / 0%; **zero** `fact_inbound_shipment` rows
- Session attributes stall to worker binding (Celery on `cip` while API on `cip_test`) — **hypothesis only**, not proven (no worker log, no `GET /health/ready` on worker process, no retarget proof)

**Ruling:** Hypothesis is **not sufficient to close S11**. S11 requires terminal progress and fact write (or explicit failed terminal state rendered). **Must re-run** with **proven** worker/dispatch topology (`pnpm dev:worker` on same DB as API, or `CIP_DEV_CELERY_DISPATCH=in_process_thread` with proof gate) until poll reaches terminal `loaded` and fact count > 0, or documented failed terminal — before S11 can PASS.

**VERDICT: FAIL**

---

## Unit 12 — P6 polish (BACKLOG-026 regression + Settings export)

### Contract rows

| ID | Requirement | Evidence | Ruled |
|----|-------------|----------|-------|
| **BACKLOG-026** | No PM pipeline regression | `test_product_master_pipeline_retired.py` **2/2**; Session B + verifier | **PASS** |
| **P6** | Settings lineup export sheet titles + column map persist | `test_commercial_tenant_profile_p6_persistence.py` + `test_lineup_export_apply.py` **13/13**; Session B | **PASS** (automated) |
| **Unit 11 non-regression** | S-rows still PASS | Unit 11 **FAIL** | **FAIL** (dependency) |

### Browser (mandatory per runbook)

| Step | Evidence | Ruled |
|------|----------|-------|
| `/settings` Lineup export — save custom titles, reload | **No session evidence** (Sessions B/F auto-only) | **FAIL** |
| `/admin/imports` PM still via Import Centre | Not browser-evidenced in Session B/F | **Unevidenced** |

### WEB_TEST_FAILURE_DIAGNOSIS (Session B context)

File **missing** from tree. CONTEXT states Session B `pnpm test:web` had **20 failures** in `page.test.tsx` historical_lineup cases due to missing `authHeaders` mock (RBAC commit `5b2a6a4`). Fix landed on branch (`importOriginal` partial mock in `page.test.tsx` **156+**). Verifier scoped vitest: **34/34 passed** including all 19 historical_lineup cases from failure log.

**VERDICT: FAIL** — Automated suites pass on HEAD; **browser Settings persistence never evidenced**; Unit 11 regression gate fails.

---

## Unit 15B — B1 forecast compute-from-history

### Contract rows

| ID | Requirement | Evidence | Ruled |
|----|-------------|----------|-------|
| **B1-07** | Forecast never merged into actuals | Session F: `fact_sales_sellout` count **31** unchanged after compute | **PASS** (`cip_test` direct) |
| **B1-04 / Charter B1** | Compute-from-history CTA; `tenant_id` never NULL; velocity + analogue provenance | Pytest **3/3**; Vitest **1/1**; Session F `null_tenant=0`; `velocity_basis` populated; **`provenance_json` column does not exist** (runbook corrected to `velocity_basis` / `analogue_basis`) | **Partial** |
| **Browser on `cip_test`** | Primary CTA click → confirm → grid refresh | Session F: **not captured**; bundle testid present; compute via **direct Python** on `cip_test` session only | **FAIL** |

### Automated (Session A + F + verifier)

| Suite | Result |
|-------|--------|
| `test_demand_forecast_compute.py` | **3/3** |
| `forecasts/page.test.tsx` | **1/1** |

### Alembic (Session F 15B.1)

`cip_test` **20260818_0018 → 20260819_0019** — **PASS**

**VERDICT: FAIL** — Service-layer and automated tests pass; **mandatory browser compute-from-history on `cip_test` is unevidenced**.

---

## Unit B4 (15C) — Promo planner (D-051–D-056, BACKLOG-094 criteria)

### Contract rows

| ID | Requirement | Evidence | Ruled |
|----|-------------|----------|-------|
| **D-051** | Per-line draft JSON rows | `test_build_promo_plan_draft_emits_per_line_mac_and_units` **PASS** | **PASS** |
| **D-052** | Dirty MAC/units survive Refresh | Vitest `promoPlanDraftMerge` **3/3**; Session F client merge sim on **cip** API | **PASS** (unit); browser **FAIL** |
| **D-053** | `create_case_from_promo_draft` `lines[]`; `cost_source` manual vs intake_weighted | Session F `cip_test`: case **2**, lines manual + intake_weighted; pytest **4/4** | **PASS** (`cip_test` service) |
| **D-054** | Cover override session-only | `test_create_case_from_promo_draft_carries_edits_and_skips_cover_persist` | **PASS** |
| **D-055** | Editable vs display-only split | Not browser-evidenced | **Unevidenced** (UI) |
| **D-056** | Tenant `lineup_export_columns` for export | Session F: 17 field/header pairs from resolver + embedded in draft | **PASS** |
| **BACKLOG-094** | Prior Opus PASS claim | Charter amendment 7 register still lists B4 — **re-verify required** | N/A |

### Browser (mandatory on `cip_test` for create-case journey)

| Step | Evidence | Ruled |
|------|----------|-------|
| `/promotions` dirty MAC + Refresh | **Not run** (Session F MCP blocked) | **FAIL** |
| Create case | Service layer `cip_test` only | **Partial** |

### Contamination (exclude from evidence)

Session F live API on **`cip`** created CPOR case **#313** — fixture contamination per runbook; **not B4 verify evidence**.

**VERDICT: FAIL** — D-051–D-054/D-056 proven in tests and `cip_test` service calls; **browser dirty-cell Refresh journey and D-055 display split never evidenced**.

---

## Automation limits — explicit rulings

Charter question: does the row close on **code + documented manual path**, or **require a human click** before PASS?

| Item | Code / manual evidence | Human click required for PASS? | Ruling |
|------|------------------------|-------------------------------|--------|
| **A3 — `window.prompt` reset password (Unit 8)** | UI uses prompt (code); Session C documents ops stdin reset on `cip` + viewer login in A5 | **No** — ops equivalent + downstream A5 login closes A3 | **Closes without browser click** |
| **HL mapping panel snapshot (Unit 11 Rule #4)** | Thin mount proven at `page.tsx` **4481–4488**; Session E expected-render table from component defaults; job **639** seeded on `cip_test` | **No** for proving **thin mount defect** (code sufficient). **Yes** if ever claiming HL **full parity** PASS in live UI | **FAIL on parity without click**; defect confirmed by code |
| **Steward drawer S5–S7 (Unit 11)** | `StewardCandidateDrawer` **607–627** + `ShipmentMappingStewardPanel` with `confidenceBand` / evidence widgets; manual path documented | **No** for slot **wiring** PASS at path:line. **Yes** for operator-journey smoke claiming drawer UX verified | **Code closes S5–S7 wiring**; does not cure S2/S3/S4/S11 failures |
| **CDP evaluate / `browser_run_code_unsafe` (drawer open automation)** | Blocked `BROWSER_UNSAFE` | **Yes** for any verdict that depends on **opened drawer screenshots** | Automation limit acknowledged; **not** a product defect; **does not** block code-based S5–S7 PASS |

---

## SUPERSEDED

**None.** No unit evidence is provably gone; North Star NS-2/NS-3/NS-6/NS-7 flags note future gate rewrites but do not supersede current VERIFY debt per runbook.

---

## Evidence integrity notes

1. **SESSION A/B markdown files absent** — Session A/B claims rest on `.tmp_session_a_*` / `.tmp_session_b_*` only; acceptable as data but weaker chain of custody than committed evidence files.
2. **`WEB_TEST_FAILURE_DIAGNOSIS.md` absent** — Session B web failure analysis reconstructed from CONTEXT + `.tmp_session_b_failures.txt`; HEAD vitest confirms fix.
3. **Session D Unit 6f browser blocked run** superseded for **API semantics** by later `cip_test` write block in same file — not superseded for **browser Accept**.
4. **CPOR #313 on `cip`** — exclude from B4 PASS consideration.

---

## Register actions

| Unit | Action |
|------|--------|
| 6f, 7, 11, 12, 15B, B4 | Remain open in `docs/BACKLOG.md` VERIFY-debt register |
| 8 | Clear row on Warren acceptance of this PASS (date + SHA `0276f50`) |

**VERDICT: PASS** — **Unit 8 only**

---

# Second pass — 2026-08-31

**Verifier:** Independent CONSULT (did not produce session evidence)  
**Charter:** v1.3 amendment 7 — only `VERDICT: PASS` closes a register row  
**Branch reviewed:** `main` @ `2a9c668` (evidence consolidated); verifier re-run at `a0875d6`  
**Evidence inputs (full set on branch):** `docs/verify/SESSION_{A,B,C,D,E,F}_EVIDENCE.md`, `docs/verify/WEB_TEST_FAILURE_DIAGNOSIS.md`, `docs/VERIFY_DEBT_RUNBOOK.md`, code tree at HEAD  
**First-pass deltas:** Prior pass listed `SESSION_A_EVIDENCE.md`, `SESSION_B_EVIDENCE.md`, and `WEB_TEST_FAILURE_DIAGNOSIS.md` as missing — all three are now committed on `main`. Session D browser strip evidence and Session D `cip_test` write block were under-weighted in pass 1.

**Unit 8:** PASS from first pass **stands** — not re-ruled below.  
**Unit 11:** HL thin-mount FAIL and S11 stall **re-confirmed** unless new evidence explicitly overturns (it does not).

---

## Summary (second pass)

| Unit | First pass | Second pass | Change |
|------|------------|-------------|--------|
| **6f** | FAIL | **FAIL** | No change — browser Accept still unevidenced |
| **7** | FAIL | **PASS** | Session D browser strip + HTTP + PvE formula unchanged |
| **8** | PASS | **PASS** | Stands (not re-ruled) |
| **11** | FAIL | **FAIL** | HL thin mount + S11 stall stand; S2/S3/S4 PARTIAL |
| **12** | FAIL | **FAIL** | Unit 11 gate + no `/settings` browser; web diagnosis clarifies harness only |
| **15B** | FAIL | **FAIL** | No browser compute on `cip_test` |
| **B4** | FAIL | **FAIL** | No browser dirty-MAC Refresh journey |

**VERDICT: PASS** — **Units 7 and 8 only** (Unit 8 carried forward from first pass)

---

## Unit 6f — D-040 distributor attribution propose→confirm

### Contract rows

| ID | Requirement | Evidence | Ruled |
|----|-------------|----------|-------|
| **D-040** | `token_proposed` → `steward_set` / `conflict`; Accept ship-corroborated; soft-clear; Phase-1 confirmer exact qty; **no auto-clear on conflict** | `SESSION_D_EVIDENCE.md` §Task 2 `cip_test`: Accept → `steward_set` + audit `lineup_ship_corroborated_distributor_accept`; soft-clear → `distributor_id` NULL; confirmer ×2 → stays `conflict`, `distributor_id=94` | **Evidenced** (`cip_test` HTTP/SQL) |
| **D-038 amend** | Dual-write OPEN_CHANNEL + line `distributor_id` on token stamp | Accept audit cites `dim_distributor` 92 (`SESSION_D_EVIDENCE.md`) | **Partial** — not re-proven end-to-end in browser |
| **D-040 pytest** | Phase-1/2 confirmer logic | `SESSION_A_EVIDENCE.md`: **10/10** `test_lineup_distributor_attribution.py` | **PASS** |
| **BACKLOG register** | Browser smoke: `/admin/po-management` → Proposed → Accept | `SESSION_D_EVIDENCE.md` §~21:50: section chrome + 1035 proposed rows **OBSERVED**; **no** button matching `/Accept/i`; ship-corroborated Accept is on Customer-token stamp when `ship_corroboration_offer` present — not exercised; soft-clear enabled, **not clicked** | **Unevidenced** (browser write path) |
| **Case 1016** | Historical smoke target | Absent on `cip`; substitute case 7 / 146 identified read-only (`SESSION_D_EVIDENCE.md`) | N/A — substitute acceptable only with exercised Accept |

### Automation limits

| Row | Code + documented path closes? | Human click required? |
|-----|-------------------------------|----------------------|
| D-040 transition semantics | **Yes** — `cip_test` HTTP + pytest (`SESSION_A`, `SESSION_D`) | **No** for backend semantics |
| Register browser Accept smoke | **No** | **Yes** — operator must click Accept (or documented ship-corroborated Accept on token-stamp section) in browser |

**VERDICT: FAIL** — D-040 semantics are proven on disposable `cip_test` and in pytest (`SESSION_A_EVIDENCE.md`, `SESSION_D_EVIDENCE.md`). Charter amendment 7 and `smoke-via-browser.mdc` require **browser operator Accept** on the attribution review surface. HTTP on `cip_test` does not substitute. Committed Session A strengthens the pytest chain but does not close the browser row.

---

## Unit 7 — BACKLOG-068 shipping lineup-quarter strip

### Contract rows

| ID | Requirement | Evidence | Ruled |
|----|-------------|----------|-------|
| **BACKLOG-068** | `landed_this_quarter_units` + `shipped_not_landed_units`; PvE fill **unchanged** (shipped-basis formula) | Service: 26Q2 `shipped_not_landed_units=10`, `landed_this_quarter_units=39074` (`SESSION_D_EVIDENCE.md`); git blame: `plan_vs_executed.py` fill formula unchanged since before 2026-08-14 pin (`SESSION_D_EVIDENCE.md` §Task 1) | **PASS** |
| **SH-01 / SH-02** | Lifecycle cohort semantics | `SESSION_A_EVIDENCE.md`: **12/12** `test_inbound_lineup_quarter.py` including `test_accumulate_landed_this_quarter_vs_plan_landed` | **PASS** |
| **Strip labels** | **"Shipped (awaiting POD)"**, **"Landed this quarter"** rendered | `SESSION_D_EVIDENCE.md` §~21:50 browser innerText verbatim: `Shipped (awaiting POD)` **10**; `Landed this quarter` **39,074** (plan quarter 26Q2) | **PASS** |
| **HTTP summary** | `GET /api/v1/shipping/lineup-quarter-summary?plan_quarter=26Q2` | `SESSION_D_EVIDENCE.md`: **200**; JSON keys match rendered strip (`landed_this_quarter_units=39074.0`, `shipped_not_landed_units=10.0`) | **PASS** |
| **PvE fill % unchanged** | Shipped-basis formula not regressed; fill visible in browser | Browser: **Fill rate (headline) 19.5%** 26Q3 (`SESSION_D_EVIDENCE.md`); git: formula `sum_min / sum_p` unchanged (`SESSION_D_EVIDENCE.md` §Task 1); today `6352/32509=19.5%` — **data moved**, not calculation regression | **PASS** |

### Automation limits

| Row | Code + documented path closes? | Human click required? |
|-----|-------------------------------|----------------------|
| Strip labels | **Yes** — browser snapshot in `SESSION_D_EVIDENCE.md` | **No** |
| PvE fill unchanged | **Yes** — formula git-unchanged + live tile shows expected % from current data | **No** — 13.2% → 19.5% is data drift, not Unit 7 regression |

**VERDICT: PASS** — First pass FAIL was driven by missing/incorrect weighting of Session D's successful browser run (~21:50 UTC+2). With full evidence on branch, automated SH-01/SH-02, rendered strip labels, HTTP spot-check, and PvE formula non-regression are all evidenced.

---

## Unit 11 — Import parity (unchanged FAIL pillars)

**Contract version:** `docs/STEWARD_EXPERIENCE_CONTRACT.md` v1.6  
**Pass-1 HL thin-mount FAIL and S11 stall:** **stand** — new Session A/B evidence does not overturn.

### Backlog / Rule #4 mapping rows

| ID | Requirement | Evidence | Ruled |
|----|-------------|----------|-------|
| **BACKLOG-026** | Generic PM pipeline retired | `SESSION_B_EVIDENCE.md` + `SESSION_E_EVIDENCE.md`; pytest green | **PASS** |
| **BACKLOG-027** | PM + HL → `CanonicalColumnMappingPanel` | PM: `SESSION_E_EVIDENCE.md` job **30** full panel **OBSERVED**; HL: `page.tsx` **4481–4488** + `SESSION_E_EVIDENCE.md` expected-render table (no `columnSamples`, `requiredGroups`, dispositions) | **PM PASS; HL FAIL** |
| **BACKLOG-044** | Shipment steward parity | S2/S3/S4 PARTIAL; S11 FAIL below | **FAIL** |

### HL thin-mount (re-confirmed FAIL)

`SESSION_E_EVIDENCE.md` job **639** on `cip_test` seeded; live HL mapping snapshot blocked by `FILE_CHOOSER_UNAUTOMATABLE` / `PLAYWRIGHT_FILE_ROOT`. Code mount at `page.tsx` **4481–4488** passes only `testIdPrefix`, `fileHeaders`, `draft`, `targetOptions`, `dirty`. Expected operator render documented in Session E (Examples em dash, no required-group chips, no disposition column). **Code evidence closes the thin-mount defect** — no human click required to prove **FAIL on parity**. Human click would be required only to claim HL **full parity PASS**.

### Shipment steward S-rows (material to unit verdict)

| ID | EXPECTED | Evidence | Grade | Unit impact |
|----|----------|----------|-------|-------------|
| **S1** | Viewport shell | Browser job **1159** workspace **OBSERVED** (`SESSION_E_EVIDENCE.md`) | **PASS** | — |
| **S2** | Tabs + counts; tab switch resets filters/selection | Tabs/counts **OBSERVED**; no selection reset on tab change (code **487**) | **PARTIAL** | STOP |
| **S3** | Chip filters + **300ms debounced list search** | Chips **OBSERVED**; no list search field (`SESSION_E_EVIDENCE.md`) | **PARTIAL** | STOP |
| **S4** | Confidence **band** on list | Numeric `score 0.95` in browser; band chips drawer-only | **PARTIAL** | STOP |
| **S5–S7** | Drawer chrome / evidence / override | Code wired; drawer not opened (`BROWSER_UNSAFE`) | **PASS** (code wiring) | Does not cure S2–S4/S11 |
| **S8–S9, S12, S14** | Bulk, plan toolbar, pagination, ambiguity | Browser **OBSERVED** (`SESSION_E_EVIDENCE.md`) | **PASS** | — |
| **S10** | Async dispatch | Job **640** `cip_test`: 200, `async: true`, `task_id` (`SESSION_E_EVIDENCE.md`) | **PASS** | — |
| **S11** | Progress poll → terminal `loaded` + facts | Job **640**: poll **200** ~90s, `task_state: STARTED`, `pct: 0`; **0** fact rows (`SESSION_E_EVIDENCE.md`) | **FAIL** | Sufficient alone to fail unit |
| **S13** | Error surfaces | Not triggered | **PASS** (code) | — |

**S11 ruling (unchanged):** Worker-topology hypothesis in Session E is not proof. S11 requires terminal progress and fact write (or explicit failed terminal). **FAIL** stands.

**VERDICT: FAIL** — HL Rule #4 thin mount; S2/S3/S4 PARTIAL without waiver; S11 runtime incomplete.

---

## Unit 12 — P6 polish

### Contract rows

| ID | Requirement | Evidence | Ruled |
|----|-------------|----------|-------|
| **BACKLOG-026** | No PM pipeline regression | `SESSION_B_EVIDENCE.md`: **2/2** `test_product_master_pipeline_retired.py` | **PASS** |
| **P6 automated** | Settings export sheet titles + column map persist | `SESSION_B_EVIDENCE.md`: **13/13** pytest across `test_commercial_tenant_profile_p6_persistence.py`, `test_lineup_export_apply.py`, retired PM | **PASS** (automated) |
| **Unit 11 non-regression** | S-rows still PASS | Unit 11 **FAIL** (above) | **FAIL** (dependency) |
| **pnpm test:web** | No import UX regression signal | Session B: **20 failed**; `WEB_TEST_FAILURE_DIAGNOSIS.md`: **19/20 STALE TEST** (`authHeaders` mock gap since `5b2a6a4`); HEAD `page.test.tsx` uses `importOriginal` partial mock spreading real `authHeaders` (**156–188**) | **PASS** (harness fixed on HEAD; not product regression) |
| **Browser `/settings`** | Save custom sheet titles, reload | **No session evidence** in Sessions B/F or A | **FAIL** |
| **Browser PM Import Centre** | PM still via Import Centre | Not browser-evidenced in Session B | **Unevidenced** |

### Automation limits

| Row | Code + documented path closes? | Human click required? |
|-----|-------------------------------|----------------------|
| P6 file-based persistence | **Yes** — pytest roundtrip (`SESSION_B_EVIDENCE.md`) | **No** for file logic |
| `/settings` UI persist | **No** | **Yes** — operator must save/reload in browser |

**VERDICT: FAIL** — Session B + `WEB_TEST_FAILURE_DIAGNOSIS.md` clarify vitest failures were test-harness stale, not product removal of Apply. That does **not** close mandatory browser Settings persistence or Unit 11 regression gate.

---

## Unit 15B — B1 forecast compute-from-history

### Contract rows

| ID | Requirement | Evidence | Ruled |
|----|-------------|----------|-------|
| **B1-07** | Forecast never merged into actuals | `SESSION_F_EVIDENCE.md`: `fact_sales_sellout` **31** unchanged after compute on `cip_test` | **PASS** (`cip_test` direct) |
| **B1-04 / tenant_id** | Compute-from-history; `tenant_id` never NULL | `SESSION_A_EVIDENCE.md`: pytest **3/3**; `SESSION_F_EVIDENCE.md`: `null_tenant=0` on `cip_test` | **PASS** (service) |
| **Provenance** | Velocity + analogue on persisted rows | `SESSION_F_EVIDENCE.md`: `velocity_basis` populated; no `provenance_json` column (runbook-corrected) | **PASS** (schema-aligned) |
| **pytest / vitest** | Automated CTA + POST shape | `SESSION_A_EVIDENCE.md`: **3/3** pytest + **1/1** vitest | **PASS** |
| **Alembic** | `cip_test` migrate head | `SESSION_F_EVIDENCE.md`: **20260818_0018 → 20260819_0019** | **PASS** |
| **Browser on `cip_test`** | Primary CTA click → confirm → grid refresh | `SESSION_F_EVIDENCE.md`: **not captured**; bundle `forecast-compute-from-history` present; compute via direct Python on `cip_test` only | **FAIL** |

### Automation limits

| Row | Code + documented path closes? | Human click required? |
|-----|-------------------------------|----------------------|
| Service compute + tenant guard | **Yes** — `SESSION_F_EVIDENCE.md` direct `compute_from_history` | **No** for service layer |
| Charter browser row | **No** | **Yes** — operator must click Compute from history on `/forecasts` against `cip_test` API |

**VERDICT: FAIL** — `SESSION_A_EVIDENCE.md` and `SESSION_F_EVIDENCE.md` strengthen automated and `cip_test` service proof. Mandatory browser compute-from-history on `cip_test` remains unevidenced.

---

## Unit B4 (15C) — Promo planner

### Contract rows

| ID | Requirement | Evidence | Ruled |
|----|-------------|----------|-------|
| **D-051** | Per-line draft JSON rows | `SESSION_B_EVIDENCE.md`: **4/4** `test_promo_plan_builder.py` | **PASS** |
| **D-052** | Dirty MAC/units survive Refresh | `SESSION_B_EVIDENCE.md`: vitest **3/3** `promoPlanDraftMerge.test.ts`; `SESSION_F_EVIDENCE.md` client merge sim | **PASS** (unit); browser **FAIL** |
| **D-053** | `create_case_from_promo_draft` `lines[]`; `cost_source` manual vs intake_weighted | `SESSION_F_EVIDENCE.md`: case **2** on `cip_test`, manual + intake_weighted lines | **PASS** (`cip_test` service) |
| **D-054** | Cover override session-only | `SESSION_B_EVIDENCE.md`: `test_create_case_from_promo_draft_carries_edits_and_skips_cover_persist` | **PASS** |
| **D-055** | Editable vs display-only split | `display_only_fields` in build draft test only; no MAC popover UI browser | **Unevidenced** (UI) |
| **D-056** | Tenant `lineup_export_columns` for export | `SESSION_F_EVIDENCE.md`: 17 field/header pairs from resolver | **PASS** |
| **Browser dirty MAC + Refresh** | `/promotions` AG Grid journey | `SESSION_F_EVIDENCE.md`: **not run** (MCP blocked) | **FAIL** |
| **Browser create-case** | End-to-end from planner UI | Service layer `cip_test` only | **Partial** |

### Contamination

`SESSION_F_EVIDENCE.md`: CPOR case **#313** on **`cip`** — exclude from B4 verify evidence.

### Automation limits

| Row | Code + documented path closes? | Human click required? |
|-----|-------------------------------|----------------------|
| D-052 merge logic | **Yes** — vitest (`SESSION_B_EVIDENCE.md`) | **No** for client merge |
| Dirty-cell Refresh browser journey | **No** | **Yes** |
| D-055 popover split | **No** | **Yes** |

**VERDICT: FAIL** — `SESSION_B_EVIDENCE.md` commits the automated chain Session B captured. Browser dirty-MAC Refresh and D-055 display split remain unevidenced.

---

## SUPERSEDED (second pass)

| Item | Ruling |
|------|--------|
| Pass-1 note "SESSION A/B absent" | **SUPERSEDED** — files now on `main` |
| Pass-1 note "WEB_TEST_FAILURE_DIAGNOSIS absent" | **SUPERSEDED** — file now on `main` |
| Pass-1 Unit 7 browser strip "unevidenced" | **SUPERSEDED** — Session D browser evidence closes row |
| NS-2/NS-3/NS-6/NS-7 future gate rewrites | Not SUPERSEDED — active VERIFY debt remains on current routes |

---

## Evidence integrity notes (second pass)

1. **SESSION_A_EVIDENCE.md** and **SESSION_B_EVIDENCE.md** are committed on `main` — chain of custody improved vs pass 1 `.tmp_*` reliance.
2. **WEB_TEST_FAILURE_DIAGNOSIS.md** documents Session B `pnpm test:web` failures as **STALE TEST**; HEAD `importOriginal` mock at `page.test.tsx` **156–188** is the fix owner evidence — not re-run by verifier this pass.
3. **Session D** contains two runs: early API-500 blocked run is superseded for strip labels by later ~21:50 browser success; `cip_test` write block is authoritative for D-040 HTTP semantics.
4. **CPOR #313 on `cip`** — still exclude from B4 PASS.

---

## Register actions (second pass)

| Unit | Action |
|------|--------|
| 6f, 11, 12, 15B, B4 | Remain open in `docs/BACKLOG.md` VERIFY-debt register |
| 7 | Clear row on Warren acceptance of this PASS (date + SHA `a0875d6` or successor) |
| 8 | Clear row on Warren acceptance of first-pass PASS (date + SHA `2a9c668` / evidence `SESSION_C_EVIDENCE.md`) |

**VERDICT: PASS** — **Units 7 and 8 only**
