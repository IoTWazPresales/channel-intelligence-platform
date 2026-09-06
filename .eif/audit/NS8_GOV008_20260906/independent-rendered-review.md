# N-0011 independent rendered review (GOV-008)

**Run:** `NS8_GOV008_20260906`  
**Actor:** gov-008 (this session; not the implementer)  
**Date:** 2026-09-07 (session start 2026-09-06 22:57 UTC)  
**Node:** N-0011 NS-7 Data & Stewardship from design-lab  
**Implementation run (anchored, not re-executed as implement):** `NS8_DATA_20260906` / actor gov-001 / product commit `edef697`  
**Docs pin:** `af483d7`  
**Charter ledger:** `1ccfcfe`  
**Reviewer HEAD at verify:** `af483d7` (`docs: pin N-0011 Data & Stewardship product hash edef697`)  
**Branch:** `feat/ns-2-brief-nav-collapse`  
**Viewports:** 1280×800 and 390×844 via Playwright MCP `browser_resize` → `page.setViewportSize` (not CDP `Emulation.setDeviceMetricsOverride`; not `browser_run_code_unsafe`)  
**Product:** `http://localhost:3000/admin/imports` (+ `/admin/masters`, `/admin/mappings`, `/admin/steward-audit`)  
**Lab referent:** `http://localhost:3000/design-lab/data?tab=imports`  
**D-0002:** untouched (decision not mutated; `/admin/mappings` remains the deferred legacy queue leaf). No product-source edits.

This is **implementation-verification + evidence-skeptic**. Implementer `COVERAGE.md` / `BROWSER.md` are DATA. Figures below were **re-read on screen** and **re-executed in SQL** (`current_database()=cip` printed first).

---

## 1. Verdict

**VERIFIED_WITH_LIMITATIONS**

Product acceptance criteria for N-0011 are independently met on the live UI against cip NUMBER RULE grains. Lab Data & Stewardship chrome (DomainHeader + four LensTabs + HeadlineStrip + Start cards + ScopeBar) is mounted on production; existing Import Center wizard, mappings, master grids and steward-audit table are relocated, not deleted. Coverage map COVERED / PARTIAL / UNCOVERED matches the running surfaces. NUMBER RULE held: production shows 88 / 12 / 0 / 47 / 17, not lab fixture 8 / 1 / 2 / 4 / 19.

**Limitations (non-blocking for complete()):**

- Specialist-contract R3 ladder also wants a second-model consult when available. This run is another session and another programme run/actor than `NS8_DATA_20260906` / gov-001. Engine independence is run/actor (satisfied). No CLI consult was invoked.
- Keyboard path and axe not exercised.
- Loading / unavailable empty-states not live-rendered (source enumerates them; populated path was live).
- Implementer `BROWSER.md` named the 390 bottom-nav third item **Funding**. Observed label is **Promotions** (`navGroups` id `funding`, `short: 'Promotions'` — prior N-0013 IA, not introduced by `edef697`). Domain set is still Overview / Stock / funding-domain / Data / More.

**Engine gate:** `target_artifact_class: high_fidelity` is already a structured AC line and a materialized field. Delivered class is high_fidelity. Lawful `complete()` is available after this run records independent quality/verification.

---

## 2. Independence rung used

**R2 session separation + programme R3 provenance.** Fresh GOV-008 context, run `NS8_GOV008_20260906` / actor `gov-008`, distinct from implementer `NS8_DATA_20260906` / gov-001. Own Playwright session against `localhost:3000`. Own SQL re-exec via `.eif/audit/NS8_GOV008_20260906/sql_reexec.py`. Not a second-LLM consult. Planted-false / hash checks are mechanical (`edef697` exists as commit).

---

## 3. Anchored implementation_run / commit `edef697`

**FACT — commit exists** (`git cat-file -t edef697` → `commit`). Subject: `data: mount D-0008 Data & Stewardship chrome from design-lab`.

Files in `edef697` (still on disk at review HEAD):

| Path | Role |
|---|---|
| `apps/web/src/features/data-stewardship/DataChrome.tsx` | Production DomainHeader + four lenses |
| `apps/web/src/features/data-stewardship/ImportCenterOverview.tsx` | HeadlineStrip 5 + start cards + ScopeBar |
| `apps/web/src/features/data-stewardship/ImportJobCards.tsx` | 390 job cards |
| `apps/web/src/features/data-stewardship/MastersLanding.tsx` | Four-card masters landing |
| `apps/web/src/features/data-stewardship/StewardQueueOverview.tsx` | Legacy-queue headlines |
| `apps/web/src/features/data-stewardship/types.ts` | StewardshipSummary |
| `apps/api/app/services/imports/stewardship_summary.py` | Read-only grains; prints `current_database()` |
| `apps/api/app/api/v1/endpoints/imports.py` | `GET /api/v1/imports/stewardship-summary` |
| wrapped admin pages | imports / mappings / masters / steward-audit / products / customers / distributors / duplicates / gaps / channels-regions / cst-steward |
| `apps/web/src/features/shell/navConfig.ts` | **+1 leaf:** Master data → `/admin/masters`. Steward queue copy still names D-0002 deferred. |

**Not in `edef697`:** `apps/web/src/design-lab/surfaces/DataSurface.tsx` (last commit `85c111e`). Lab SOURCE is unchanged. D-0002 decision record not in the product commit.

---

## 4. Lab files read (SOURCE primary)

| File | Role |
|---|---|
| `apps/web/src/design-lab/surfaces/DataSurface.tsx` | Governing design input D-0008 as implemented (ImportsTab, StewardTab, MastersTab, audit PanelRows) |
| `apps/web/src/features/data-stewardship/*` | Production chrome |
| `apps/web/src/app/(app)/admin/imports/page.tsx` | DataChrome wrap; wizard Box `guided-import-wizard`; job cards sibling after wizard close |
| `apps/web/src/app/(app)/admin/masters/page.tsx` | MastersLanding |
| `apps/web/src/app/(app)/admin/mappings/page.tsx` | StewardQueueOverview + legacy queue |
| `apps/web/src/app/(app)/admin/steward-audit/page.tsx` | Production table |
| `apps/api/app/services/imports/stewardship_summary.py` | SQL grains |
| `.eif/audit/NS8_DATA_20260906/COVERAGE.md` | Claimed coverage map |
| `.eif/audit/NS8_DATA_20260906/BROWSER.md` | Claimed browser results |

Live lab at 1280×800 `/design-lab/data?tab=imports`:

- Title **Data & Stewardship**; four lenses **Import Center 3 / Steward queue 7 / Master data / Steward audit**
- Headlines **Jobs this week 8 / Failed 1 / Stewarding 2 / Applied 4 / Import types 19** (fixtures)
- Six start cards: Distributor sell-out & SOH, Retailer sell-through, Inbound shipments, Lineup (unified), Claim evidence, Product master
- ScopeBar Failed · 1 / Stewarding · 2 / Validated · 1 / Applied · 4; job grid

---

## 5. Coverage-map verdict

Implementer table is **confirmed** against running routes. Classes are correct. COVERED and PARTIAL were migrated; UNCOVERED stores is on-screen, not silently dropped.

| Lab lens / route | Production | Class | Independent check |
|---|---|---|---|
| Import Center | `/admin/imports` | COVERED | Chrome + headlines + 6 start cards + ScopeBar + relocated wizard. 390 cards after ScopeBar. |
| Steward queue | `/admin/mappings` | PARTIAL | Chrome wrap. Legacy queue 0. Candidates 2797 in caption, not the grid. No lab Accept/Reject bulk. D-0002 copy present. |
| Master data | `/admin/masters` + grids | COVERED (grids) | 4-card landing. Open grid links. Products 18177 / customers 5196 / distributors 101. |
| Stores card | none | UNCOVERED | Card present; Records **0**; “No grid”; alert **UNCOVERED — recorded, not migrated.** |
| Steward audit | `/admin/steward-audit` | COVERED | Production table, “Append-only log”. Lab fixture “KZN CHANNEL” **absent**. |
| CST shortcut | `/admin/imports?template=customer_sell_through` | PARTIAL | Still Import Center leaf (rail + start card). |
| Catalogue gaps / duplicates / channels / CST steward | existing admin leaves | PARTIAL extra | Wrapped in DataChrome; Masters copy “Relocated, not deleted”. |

---

## 6. Differences (lab vs production) — accepted NUMBER RULE / conservation

| Topic | Lab (live) | Production (live) | Call |
|---|---|---|---|
| Jobs headline | “this week” **8** | “last 7 days” **88**; caption ISO week-to-date **0** | NUMBER RULE (i) label |
| Failed | **1** (fixture set) | 7d **12** / ScopeBar all **38** | (i)/(iii) |
| Stewarding / pending | Stewarding **2** | Pending mapping 7d **0** / all **64** | (i) production has no `stewarding` status |
| Applied / completed | Applied **4** | Completed 7d **47** / ScopeBar all **211** | (i) no `applied` status |
| Import types | **19** fixture | Enabled **17** (caption 7 non-admin) | (i) |
| Import Center tab count | failed+stewarding **3** | failed_all+pending_all **102** (=38+64) | (iii) |
| Masters counts | 18204 / 1412 / 4 / 388 | 18177 / 5196 / 101 / **0** | NUMBER RULE; stores UNCOVERED |
| Duplicate counts | fixture integers | **—** “no stored cluster count” | CORRECT, not a fail |
| Steward queue body | Cross-job Accept/Reject | Legacy EntityMappingQueue; D-0002 deferred | PARTIAL, recorded |
| Audit body | Fixture PanelRows | Live steward_audit_event table | CORRECT |
| Wizard | none on lab | Relocated below at md+; `display:none` when idle at xs | Conservation AC |

---

## 7. NUMBER RULE re-execution

SQL: `apps/api/.venv/Scripts/python.exe .eif/audit/NS8_GOV008_20260906/sql_reexec.py`  
**Printed first:** `current_database()=cip`. Tenant `default`. Did **not** change any figure to match lab fixtures.

| Grain | SQL | On-screen (this session) | Match |
|---|---|---|---|
| jobs last 7d | 88 | Header + headline **88** | yes |
| ISO week-to-date | 0 | caption “ISO week-to-date is 0…” | yes |
| failed 7d / all | 12 / 38 | headline **12**; ScopeBar **Failed · 38** | yes |
| pending 7d / all | 0 / 64 | headline **0**; ScopeBar **Pending mapping · 64** | yes |
| completed 7d | 47 | headline **47** | yes |
| templates enabled | 17 | **Enabled import types 17** | yes |
| Import Center tab | 38+64=102 | tab **Import Center 102** | yes |
| products | 18177 | Masters Records **18177**; meta “18177 products” | yes |
| customers | 5196 | Records **5196**; Unverified **56** | yes |
| distributors | 101 | Records **101**; Unverified **12** | yes |
| stores | 0 | Records **0** | yes |
| legacy queue | 0 | **Legacy queue rows 0**; tab Steward queue **0** | yes |
| candidates needs_review | 2797 | caption **2797** (1349+1396+52) | yes |

---

## 8. Viewports

### 1280×800

Playwright `setViewportSize({ width: 1280, height: 800 })` re-applied after each navigation.

- Lab `/design-lab/data?tab=imports` — four lenses, fixture headlines, six start cards, ScopeBar, job grid.
- Prod `/admin/imports` — same chrome grammar; cip headlines; wizard **visible** (relocated, not deleted); job grid below.
- Prod `/admin/masters` — four panels; stores UNCOVERED.
- Prod `/admin/mappings` — four headline figures; legacy empty; D-0002 copy; no “Accept best candidates”.
- Prod `/admin/steward-audit` — append-only table; lab tokens absent.
- Prod `/directory` — **4 partly built · 3 planned** still labelled (Receipts & POD, Promotion planner, Plan templates, Competitor mappings / Competitor listings, Listing quality, Audit log). Markers not promoted.

### 390×844 (named workflow: import status)

`setViewportSize({ width: 390, height: 844 })`. Confirmed `window.innerWidth===390`.

| Check | Result |
|---|---|
| Bottom nav | Overview, Stock, **Promotions**, Data, More (`data-testid=mobile-bottom-nav`). Funding domain, Promotions short-label. |
| Headlines | 88 / 12 / 0 / 47 / 17 — same SQL grains as 1280 |
| Start cards | 2-col six: DSI, CST, inbound, lineup, claim evidence, product master |
| ScopeBar | Failed 38, Pending mapping 64, Validated, Completed 211 |
| Job cards | `data-testid=import-job-cards` **sibling after** wizard Box close (`page.tsx` ~4844–4846). After idle hide, cards sit under ScopeBar + “Import jobs” heading. 100 cards (latest 100). |
| Idle wizard | `guided-import-wizard` `getComputedStyle.display === 'none'`; a11y find “Guided import” empty once CSS settled |
| Open on desktop | **absent** (idle and `?template=product_master`) |
| `?template=` | wizard `display:block`; stepper present; still desktop-first mapping, not a card rewrite |

An early 390 screenshot still showed the Guided import alert before MUI breakpoint CSS settled; settled DOM is display:none. Treat the computed style + later a11y find as the idle proof.

---

## 9. Dim-by-dim table

| Dim | State | Evidence |
|---|---|---|
| design_artifact_class | **pass** | Live production Data & Stewardship chrome on cip, not a mockup. `{class: high_fidelity, path: .eif/audit/NS8_GOV008_20260906/independent-rendered-review.md}` |
| design_divergence | **pass** | Named, accepted: lab fixture week/19 types/18204 products → cip last-7d/17/18177. Steward PARTIAL. Stores UNCOVERED. |
| design_signatures | **pass** | DomainHeader, LensTabs×4, HeadlineStrip 5 (imports) / 4 (steward) / 3 dense (masters), Start an import 6-card grid, ScopeBar, StatusChip job cards at 390. |
| rendered_comparison | **pass** | Side-by-side live renders. `{artifact_class: high_fidelity, class: high_fidelity, product: /admin/imports, lab: /design-lab/data?tab=imports, viewport: 1280x800}` |
| design_sameness_review | **pass** | Grammar matches; numbers and steward body differ by charter. **visual_vocabulary_challenge** is §10. |
| design_interaction_spec | **pass** | Four lens tabs navigate to four production routes. Start cards deep-link templates. ScopeBar filters `jobStatus`. 390 cards link `?job=`. Relocated wizard. |
| design_state_coverage | **pass** | Enumerated: `populated` (live); `uncovered_stores`; `legacy_queue_empty`; `wizard_idle_hidden_xs`; `wizard_engaged_template`. Loading/error not live this session. |
| design_identity_tokens | **pass** | `{tokens: {direction_name: workbench-ui Data & Stewardship DomainHeader+LensTabs+HeadlineStrip, strip: HeadlineStrip columns=5, start: six import-type cards, scope: ScopeBar, mobile: import-job-cards}}` |
| design_execution_decisions | **pass** | Structured map §9.1. |
| ux | **pass** | Operator can read import status at 1280 and 390 without a desktop wall; four lenses reachable. |
| a11y | **pass** | Lens tablist; warn/bad HeadlineFigure severity; StatusChip on cards. Keyboard not exercised. |
| rendered | **pass** | Playwright 1280 and 390 as above. |
| content | **pass** | “Jobs in last 7 days” not “this week”; Partly built / Planned retained; D-0002 copy; UNCOVERED stores. |

### 9.1 `design_execution_decisions` evidence map

```yaml
responsive_decision:
  status: applicable
  rationale: Verified 1280×800 vs lab and 390×844 import status (named DIRECTION workflow). Idle wizard CSS-hidden at xs; job cards remain. Viewport via Playwright setViewportSize, not CDP device metrics.
visualisation_decision:
  status: applicable
  rationale: Lab HeadlineStrip + start-card grid + ScopeBar mounted. Live cardinality uses cip grains; lab fixtures not copied. Masters duplicate figure is em-dash (no cluster table) rather than a fake count.
consequential_action_decision:
  status: applicable
  rationale: Strip/scope are filters and navigation. Writes remain the relocated guided wizard and per-job steward. Cross-job accept/reject is not on this leaf (PARTIAL + deferred finding STEWARD_QUEUE_APPROVE_REJECT). D-0002 untouched.
```

### 9.2 Verification kinds

| Kind | This run |
|---|---|
| rendered (ui) | **Required and done.** Playwright 1280×800 and 390×844. |
| referent | **Required (R3) and done.** Lab `DataSurface.tsx` + live `/design-lab/data?tab=imports`. |
| journeys | Catalogue `first-path` is `required_for: [skeleton]` only. Redesign N-0011 has an empty required-journey set. |

---

## 10. Visual vocabulary challenge

**Challenge (non-empty):** Is production the same Data & Stewardship instrument as `DataSurface.tsx`, or a header/tab strip glued onto the old Import Center wizard with a mapping-queue leaf pretending to be the lab cross-job steward?

**Observed:** At 1280×800 the **chrome grammar matches** — uppercase compact HeadlineFigures, five import columns, six start cards in one Panel, ScopeBar chips, four lenses. Lab live uses fixture 8/1/2/4/19 and “Stewarding/Applied”. Production live uses cip 88/12/0/47/17 and honest labels. The lower viewport on production Import Center is the conserved guided wizard (absent from lab). That is an AC (relocate, do not delete), not a missing mount. Steward queue is **not** the lab Accept/Reject instrument; it is the legacy queue with candidate counts as captions — PARTIAL, already on the coverage map, with D-0002 left deferred. Audit is a real table, not three fixture PanelRows. Masters stores card tells the operator the grid is UNCOVERED instead of linking to a fake 388.

**Call:** Do **not** fail sameness. NUMBER RULE substitution and conservation stack are charter. PARTIAL steward is recorded, not disguised as COVERED. SHOULD-BE (not this node’s fail): Design Language v2 disposition of D-0002 / cross-job queue; a stores master if `customer_location` ever has store rows.

---

## 11. Conservation / D-0002

| Check | Result |
|---|---|
| Wizard not deleted | **yes.** `data-testid=guided-import-wizard` still wraps the stepper; visible at 1280 idle; hidden at 390 idle. |
| Mappings page not deleted | **yes.** Legacy EntityMappingQueue UI remains under Steward queue lens. |
| Master grids not deleted | **yes.** Open grid → `/admin/products`, `/admin/customers`, `/admin/distributors`. DataChrome wrap. |
| Steward audit not deleted | **yes.** Production table wrapped. |
| Extra leaves not deleted | **yes.** On-screen “Relocated, not deleted…” plus wrapped gaps/duplicates/CST/channels. |
| Column mapping not card-transformed | **yes.** `?template=product_master` at 390 still shows the desktop-first wizard, not mapping cards. |
| D-0002 untouched | **yes.** `edef697` only adds Master data nav leaf; steward queue what-text still “disposition deferred, D-0002”. No Accept/Reject lab control added. Decision D-0002 not scoped by this review. |
| Partly built / Planned | **yes.** Directory 4 partly built · 3 planned. |

---

## 12. Blocking findings

**None on product AC.**

Process note (not a fail): implementer lease `NS8_DATA_20260906` may still be live at record time (`expires_at` 2026-09-07T02:51:15Z). GOV-008 must reclaim or the holding run must release before quality events. That is lease mechanics, not an AC miss.

---

## 13. May this run lawfully complete N-0011?

**YES** — product ACs pass, `target_artifact_class: high_fidelity` is already declared, independence can be satisfied by recording quality/verification on run `NS8_GOV008_20260906` / actor `gov-008` while leaving `implementation_run: NS8_DATA_20260906`.

Do not complete if lease handoff fails or `design_experience_ok` rejects evidence shape. Do not touch D-0002. Do not edit product source.

Acceptance is `auto` / `not_required` — no operator `node.accept` required.

---

## Methods / coverage

- Playwright MCP (`user-playwright`): tabs, `browser_resize` 1280×800 and 390×844, `browser_find`, `browser_navigate`, `browser_evaluate` for computed display/viewport only, viewport screenshots (observed; not required as ledger blobs).
- Live URLs: lab imports; prod imports / masters / mappings / steward-audit / directory; prod imports `?template=product_master` at 390.
- SQL: `sql_reexec.py` → `current_database()=cip` then `stewardship_summary`.
- Git: `edef697` stat; `DataSurface.tsx` last commit `85c111e`; navConfig +1 Master data leaf.
- **Not done:** axe; keyboard; second-model consult; mutating D-0002; product-source edits.

## AS-IS vs SHOULD-BE

- **AS-IS:** Production Data & Stewardship mounts lab chrome on cip numbers; wizard/grids/audit conserved; stores UNCOVERED; steward PARTIAL; 390 import status works without a desktop wall.
- **SHOULD-BE (not a fail):** D-0002 / cross-job queue in Design Language v2; stores grid if store rows exist; bottom-nav short “Promotions” vs the word “Funding” is prior IA.
