# SESSION E Evidence — Unit 11 import parity

**Collection timestamp:** 2026-08-30 (Sunday), ~20:38 UTC+2  
**Collector:** Cursor agent (subagent under parent VERIFY run)  
**Branch (verified):** `feat/ns-1a-fx-readiness-chips` @ `3f10ae4` (`git rev-parse --short HEAD`)  
**Contract version (file):** **1.6 · 2026-07-27 · Owner: Warren** — matches seed expectation  
**Environment:** local Windows; web `:3000`, API `:8001` (operator-declared; web responded)  
**Database policy:** no writes to `cip`; apply/progress exercise on `cip_test` **not executed** in this session  
**Waiver lines from unit prompt:** *(none supplied — all S1–S14 in scope)*

**Surfaces in scope (operator):**

1. `/admin/imports` — Product Master (`product_master`) `CanonicalColumnMappingPanel`
2. `/admin/imports` — Historical Lineup (`historical_lineup`) `CanonicalColumnMappingPanel`
3. `ShipmentImportJobResolutionSection` — full steward flow (mounted as `ShipmentEntityStewardPanel` on Import Centre after shipment validation)

**Evidence-only artifact for Opus CONSULT.** No `VERDICT:` line in this file.

---

## Collection methods

| Method | Result |
|--------|--------|
| Code read (`Read` / `Grep`) | **Succeeded** for contract, steward engine, imports page, shipment-evidence modules |
| `git rev-parse` / branch | **Succeeded** — branch and SHA match operator declaration |
| Playwright MCP (`user-playwright`) | **Partial** — initial `/admin/imports` load redirected to `/login`; sign-in click attempted; subsequent MCP calls blocked by EIF guard |
| `cursor-ide-browser` MCP | **Blocked** by EIF guard |
| Apply/progress on `cip_test` | **Not executed** — no `current_database()` print; no steward apply/progress exercise |

---

## Supplementary — Import parity Rule #4 (Column mapping)

Shared component: `apps/web/src/features/import-mapping/CanonicalColumnMappingPanel.tsx` (export **122**).

| Surface | Mount path:line | Props observed in tree | OBSERVED vs shipment/DSI reference |
|---------|-----------------|--------------------------|-----------------------------------|
| **PM** | `apps/web/src/app/(app)/admin/imports/page.tsx` **3163–3181** | `testIdPrefix="pm"`, `columnSamples`, `columnNotes`, `requiredGroups` (**2616–2629**), `dispositionOptions`, `dispositionDraft`, `dirty` | **PASS-equivalent** — full mapping panel parity with shipment reference (**3505–3518**) |
| **HL** | `page.tsx` **4481–4488** (post-validate mapping review when `historicalValidatedJobId != null`) | `testIdPrefix="hl"`, `fileHeaders`, `draft`, `targetOptions`, `dirty` only | **PARTIAL** — thin mount: no `requiredGroups`, `columnSamples`, `blockingErrors`, `adjustmentNotices`, or disposition column (PM-only feature per component doc **32–33**) |
| **Shipment (reference)** | `page.tsx` **3505–3518** | `requiredGroups`, `columnSamples`, `blockingErrors`, `adjustmentNotices`, `dirty` | Reference bar for Rule #4 |

**Browser (PM/HL mapping):** **UNABLE_TO_RENDER** mapping panels — session ended on `/login` before authenticated navigation to wizard steps / HL validate review. Code paths above are the shipped evidence.

---

## S1–S14 steward contract matrix

Contract source: `docs/STEWARD_EXPERIENCE_CONTRACT.md` v1.6 slot inventory (**lines 23–38**).

Grading applies primarily to **ShipmentImportJobResolutionSection** (canonical steward consumer for Unit 11 surface #3). PM and HL surfaces have **no steward resolution section** on Import Centre (PM is mapping-only; HL is mapping review post-validate only) — steward slots **ABSENT** on those surfaces unless noted.

| ID | EXPECTED (contract behavior) | Implementation path:line | PM / HL surface | Shipment steward OBSERVED | Grade |
|----|------------------------------|--------------------------|-----------------|---------------------------|-------|
| **S1** | Two-column viewport shell; list scrolls inside viewport on md+; drawer sticky beside list | Engine: `StewardWorkspaceViewportShell.tsx` **25–70** · Shipment mount: `ShipmentImportJobResolutionSection.tsx` **446–630** (`bordered`, `rootTestId="shipment-steward-workspace-viewport-shell"`) | **ABSENT** — no steward workspace on PM/HL routes | Two-column shell with left workspace + optional drawer; md+ `maxHeight: calc(100vh - 120px)` and overflow hidden on left column | **PASS-equivalent** |
| **S2** | Per-entity tabs with total + needs-work counts; **tab switch resets filters/selection to tab default** | `StewardEntityTabsBar.tsx` **77+** · `useShipmentEntityTabCounts.ts` **18–44** · Shipment: **484–493**, tab-change reset **307–311** | **ABSENT** | Tabs + API tab-counts render. Tab change clears drawer, selection, bulk prov names (**307–311**) but **does not reset** `filtersByTab[activeTab]` to tab default — filters persist per tab | **PARTIAL** |
| **S3** | Chip filters + **free-text search debounced 300ms**; clear-to-default; at-default detection | `StewardCandidateFilters.tsx` **12–224** (chips only) · Shipment wiring **496–507** · Drawer override debounce: `shipmentStewardRowActions.tsx` **108–116** | **ABSENT** | Chip filters + clear-to-default + tab-aware `isAtDefault` present. **No** steward-list free-text search field (contrast CST: `CstImportJobResolutionSection.tsx` **182–197**, **623–625**). 300ms debounce exists only on drawer master override search, not candidate list | **PARTIAL** |
| **S4** | Key/token, row count, plan_class, top suggestion + **confidence band**; units/value where domain has them | Columns: `inboundEvidenceMappingCandidateWorkspaceColumns.tsx` **180–266** · Plan-aware builder: `shipmentResolutionWorkspaceTableProps.tsx` **31–81** · Shipment wire-up **329–341**, **462** | **ABSENT** | Token/key, Rows, Qty/value, Suggested name columns present. Plan column shows `formatPlanActionLabel` chip + Ready + **numeric score** (**66–69**), not shared `confidenceBand` chips (drawer plan header uses bands **389–395**). Base `plan` column in inbound builder also uses raw score (**260–263**) | **PARTIAL** |
| **S5** | Shared drawer chrome, close affordance, a11y label, testids | `StewardCandidateDrawer.tsx` **8–33** · `StewardDrawerChrome.tsx` **20–64** · Shipment **607–627** | **ABSENT** | `StewardCandidateDrawer` with config testids (`SHIPMENT_ENGINE_CONFIG.drawerTestIds`) | **PASS-equivalent** |
| **S6** | Drawer evidence: sample raw values, affected rows/cases, value at stake | `StewardEvidenceSummary.tsx` **15+** · `ShipmentMappingStewardPanel.tsx` **265–277** | **ABSENT** | Evidence summary with `sample_raw_values`, `row_count`, `total_units`, `total_reported_value`, testid `shipment-drawer-evidence` | **PASS-equivalent** |
| **S7** | Ranked suggestion cards (band/score/reason), one-click map, override search; never auto-create | `StewardSuggestionCards.tsx` **29+** · `ShipmentMappingStewardPanel.tsx` **400–411** (emptyMessage: “never auto-created”) · Override: `shipmentStewardRowActions.tsx` | **ABSENT** | Shared cards + override slot with debounced master search; explicit never-auto-create copy | **PASS-equivalent** |
| **S8** | Selection + select-all-visible; bulk **preview → apply** two-step with per-row error summary | `useStewardBulkSteward.ts` **174–206** (preview), **209+** (apply) · `StewardBulkSection.tsx` **27–205** · Shipment inline preview toolbar **526–530**, `StewardBulkSection` **632–639** | **ABSENT** | `BulkSelectionToolbar` preview-danger → `bulkPreview.mutateAsync`; `StewardBulkSection` preview dialog; apply gated on preview token match (**362** in hook) | **PASS-equivalent** |
| **S9** | Compute plan (async) → preview → apply-all-ready (each row own target) → async apply + progress; apply-all on **plan toolbar** (D-016) | `useStewardResolutionPlan.ts` **24+** · `StewardResolutionPlanToolbar.tsx` **59+** · Shipment plan toolbar **414–439**, apply-all dialog **661–681**, workspace “Apply selected” **561–568** · Engine async paths `shipmentSteward.engineConfig.ts` **75–78** | **ABSENT** | Full plan toolbar with `onApplyAllReady` (**422**), confirm dialog, async compute/apply paths wired. Contract known gap **D-012**: no DSI global-suspicious checkbox on plan toolbar (documented waiver in contract §Known gaps, not unit-prompt waiver line) | **PASS-equivalent** *(D-012 sub-feature absent by design)* |
| **S10** | Validate/apply: running + `pipeline_queued_at`, dispatch-claim, task slot, `{async, task_id}`; no long sync write in request path | API: `shipment_evidence.py` `_dispatch_shipment_apply` **95–105** · Apply endpoint **1354–1385** (`persist_pipeline_queued_at` **1362**, `{async: True, task_id}` **1376–1385**) · Web slot: `set_task_slot_on_job` **1371** | N/A on PM/HL mapping UI | Async dispatch pattern present on shipment apply path; revalidate uses `revalidatePath` in engine config **79** | **PASS-equivalent** *(code; apply not exercised on `cip_test`)* |
| **S11** | Fire-and-poll progress phase/pct; bell registration; terminal/failed states | `ImportJobValidateProgressPanel.tsx` **73+** · Shipment validate UI `page.tsx` **3563–3569** · Poll: `useImportJobProgressQuery` **2115–2118** · Bell: `registerClientBackgroundTask` `shipmentSteward.engineConfig.ts` **44–49** | PM/HL: generic import progress elsewhere on page, not steward-specific | Validate progress panel + background task registration on async pipeline start | **PASS-equivalent** *(validate progress observed in code; live poll not browser-verified)* |
| **S12** | Server pagination when volume can exceed ~500 | `StewardCandidatesPagination.tsx` **8+** · `useShipmentCandidatesPage.ts` **19–96** (server skip/limit) · Shipment **576–585** | **ABSENT** | Server-paginated candidate list with client full-load fallback for queue filters (`clientQueueFilterActive`) | **PASS-equivalent** |
| **S13** | Action feedback alert w/ dismiss; partial-success after bulk/plan; load-error distinct from empty | Shipment: plan apply summary **408–411** · effective plan error **440–443** · revalidate error **657–659** · bulk summary in `StewardBulkSection` **95–98** | **ABSENT** | Dismissible plan apply alerts; error alerts for plan refresh and revalidate; bulk partial-success pattern in shared section | **PASS-equivalent** |
| **S14** | Never auto-create dims; FLAG ≠ BLOCK; ambiguous reviewable; stable real IDs | Drawer copy **403** · Provisional actions steward-initiated (**547–548** bulk provisional) · Candidates use numeric `id` from API (`ImportEntityMappingCandidate`) | PM/HL: governed at API/import rules (no steward UI) | Real candidate IDs in grid selection; never-auto-create messaging; verify-name / duplicate flows keep rows reviewable (**471–476**, **290–373**) | **PASS-equivalent** |

---

## Per-row OBSERVED vs EXPECTED notes (shipment steward — surface #3)

### S1 — Viewport shell

- **EXPECTED:** Two-column workspace; sticky drawer; list scroll inside viewport on md+.
- **OBSERVED (code):** `StewardWorkspaceViewportShell` flex row, left column `maxHeight: { md: 'calc(100vh - 120px)' }`, `overflow: { md: 'hidden' }` (**StewardWorkspaceViewportShell.tsx:51–63**). Shipment mounts bordered shell with drawer slot (**ShipmentImportJobResolutionSection.tsx:446–630**).
- **OBSERVED (browser):** **UNABLE_TO_RENDER** steward workspace — not authenticated to a validated shipment job in this session.

### S2 — Entity tabs + counts

- **EXPECTED:** Tabs with total/needs-work counts; tab switch resets filters **and** selection to tab default.
- **OBSERVED (code):** `StewardEntityTabsBar` + `useShipmentEntityTabCounts` API **`/mapping-candidates/tab-counts`**. Selection/detail reset on tab change (**307–311**); filters stored per-tab (**119–121**, **496–507**) without forced reset to `defaultShipmentStewardFiltersForTab` on tab switch.
- **OBSERVED (browser):** **UNABLE_TO_RENDER**.

### S3 — Filters

- **EXPECTED:** Chip filters + free-text search with 300ms debounce on steward candidate list.
- **OBSERVED (code):** Chips-only `StewardCandidateFilters` on shipment section. No `searchInput` / debounced list filter (unlike CST import steward). Drawer override search debounced 300ms (**shipmentStewardRowActions.tsx:108–116**).
- **OBSERVED (browser):** **UNABLE_TO_RENDER**.

### S4 — Row columns — evidence density

- **EXPECTED:** Token, counts, plan_class, top suggestion with **confidence band**; units/value columns.
- **OBSERVED (code):** `buildInboundEvidenceMappingCandidateWorkspaceColumns` provides token, rows, qty/value, suggested (**inboundEvidenceMappingCandidateWorkspaceColumns.tsx:180–251**). Plan column uses action chip + numeric score, not `confidenceBand` helper (**shipmentResolutionWorkspaceTableProps.tsx:60–71**).
- **OBSERVED (browser):** **UNABLE_TO_RENDER**.

### S5 — Drawer chrome

- **EXPECTED:** Shared chrome, close, a11y, testids.
- **OBSERVED (code):** `StewardCandidateDrawer` wrapper with config testids (**607–627**).
- **OBSERVED (browser):** **UNABLE_TO_RENDER**.

### S6 — Drawer evidence body

- **EXPECTED:** Sample raw values, affected rows, value at stake.
- **OBSERVED (code):** `StewardEvidenceSummary` with row_count, units, reported value (**ShipmentMappingStewardPanel.tsx:265–277**).
- **OBSERVED (browser):** **UNABLE_TO_RENDER**.

### S7 — Drawer suggestions + override

- **EXPECTED:** Ranked cards, one-click map, override search, never auto-create.
- **OBSERVED (code):** `StewardSuggestionCards` + `ShipmentCandidateDrawerActions` override slot (**400–411**).
- **OBSERVED (browser):** **UNABLE_TO_RENDER**.

### S8 — Selection + bulk

- **EXPECTED:** Preview → apply two-step with per-row errors.
- **OBSERVED (code):** `useStewardBulkSteward` preview mutation opens dialog before apply (**174–206**); `BulkSelectionToolbar` “Preview bulk steward” (**526–530**).
- **OBSERVED (browser):** **UNABLE_TO_RENDER**.

### S9 — Resolution plan

- **EXPECTED:** Async compute → preview → apply-all-ready on plan toolbar; apply selected on workspace toolbar only (D-016).
- **OBSERVED (code):** `StewardResolutionPlanToolbar` `onApplyAllReady` (**422**); workspace “Apply selected” separate (**561–568**); confirm dialog (**661–681**). D-012 suspicious checkbox omitted per contract known gaps.
- **OBSERVED (browser):** **UNABLE_TO_RENDER**.

### S10 — Async dispatch

- **EXPECTED:** running + `pipeline_queued_at`, task slot, immediate `{async, task_id}`.
- **OBSERVED (code):** Apply endpoint sets status running, `persist_pipeline_queued_at`, dispatches `_dispatch_shipment_apply`, returns async payload (**shipment_evidence.py:1354–1385**).
- **OBSERVED (runtime):** Apply/progress exercise **NOT EXECUTED** on `cip_test` (no `current_database()` captured).

### S11 — Progress

- **EXPECTED:** Phase/pct poll; bell registration; terminal states.
- **OBSERVED (code):** `ImportJobValidateProgressPanel` during shipment validate (**page.tsx:3563–3569**); `registerClientBackgroundTask` on pipeline start (**shipmentSteward.engineConfig.ts:44–49**).
- **OBSERVED (browser):** **UNABLE_TO_RENDER** progress rail on live job.

### S12 — Pagination

- **EXPECTED:** Server pagination when volume can exceed ~500.
- **OBSERVED (code):** `useShipmentCandidatesPage` server skip/limit (**19–96**); UI pagination control (**576–585**).
- **OBSERVED (browser):** **UNABLE_TO_RENDER**.

### S13 — Error surfaces

- **EXPECTED:** Dismissible action feedback; partial-success summaries; load errors distinct from empty.
- **OBSERVED (code):** Plan apply `Alert` with onClose (**408–411**); effective-plan and revalidate error alerts (**440–443**, **657–659**).
- **OBSERVED (browser):** **UNABLE_TO_RENDER**.

### S14 — Domain invariants

- **EXPECTED:** No auto-create dims; ambiguous stays reviewable; stable real IDs.
- **OBSERVED (code):** Numeric candidate `id` throughout selection/grid; drawer emptyMessage and provisional bulk require explicit steward action (**403**, **547–548**).
- **OBSERVED (browser):** **UNABLE_TO_RENDER**.

---

## PM / HL mapping surfaces — steward slot summary

| Slot | PM (`product_master` mapping step) | HL (`historical_lineup` mapping review) |
|------|-------------------------------------|----------------------------------------|
| S1–S13 | **ABSENT** — no `*ImportJobResolutionSection` on Import Centre for PM | **ABSENT** — mapping review panel only (**4481–4488**); no HL steward resolution section |
| S14 | Enforced at API/import governance (out of UI scope here) | Same |
| Rule #4 mapping | **PASS-equivalent** (full `CanonicalColumnMappingPanel` props) | **PARTIAL** (thin mount vs PM/shipment) |

---

## Browser session log (verbatim-ish)

1. `user-playwright` `browser_navigate` → `http://localhost:3000/admin/imports` — initial navigation reported Import Centre title, then redirect to login on snapshot refresh.
2. Login page snapshot: email prefilled `admin@local`, password prefilled `changeme`, Sign in button present.
3. Sign-in click attempted (`browser_click` on login submit) — page remained on `/login`; no steward/mapping panels captured.
4. Subsequent Playwright snapshot **blocked** by EIF guard fail-closed.

**Consequence:** No operator-visible confirmation of PM mapping step, HL mapping review, or shipment steward grid/drawer in this SESSION E file. Code-path evidence is primary.

---

## Apply / progress exercise (`cip_test`)

**Planned:** Override `DATABASE_URL_SYNC` and `DATABASE_URL_SYNC_MIGRATE` to `cip_test`; print `current_database()` before any write; exercise shipment steward apply/progress poll.

**OBSERVED:** **NOT EXECUTED.** No database connection, no apply mutation, no progress poll output collected.

**EXPECTED:** `current_database()` = `cip_test` before writes; async apply returns `{async, task_id}`; progress phases visible in UI and/or poll endpoint.

---

## Contract / memory discrepancies

| Source | Branch claim |
|--------|--------------|
| Operator / `git rev-parse` | `feat/ns-1a-fx-readiness-chips` @ `3f10ae4` |
| `docs/memory/CURRENT.md` (read via grep) | `design-language-v1` — **stale vs working tree** |

Pin VERIFY to git evidence (`3f10ae4`), not CURRENT.md branch field.

---

## Summary counts (shipment steward grades)

| Grade | Rows |
|-------|------|
| PASS-equivalent | S1, S5, S6, S7, S8, S9, S10, S11, S12, S13, S14 |
| PARTIAL | S2, S3, S4 |
| ABSENT | *(none on shipment surface — all slots have shipped implementation)* |
| WAIVED | *(none — no unit-prompt waiver lines)* |

**Import mapping (Rule #4):** PM **PASS-equivalent**; HL **PARTIAL**.

**Outstanding for complete VERIFY:** Authenticated browser pass on all three surfaces; `cip_test` apply/progress exercise with `current_database()` transcript; optional re-run after EIF guard unblocks MCP consistently.

---

*Evidence-only — no VERDICT. For Opus CONSULT.*
