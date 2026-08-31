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
