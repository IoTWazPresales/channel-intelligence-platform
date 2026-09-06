# N-0017 independent rendered review (GOV-008)

**Run:** `NS7_GOV008_20260906`  
**Actor:** gov-008 (this session; not the implementer)  
**Date:** 2026-09-06  
**Node:** N-0017 Stock & Sell-through Execution vs plan from design-lab  
**Implementation run (anchored, not re-executed as implement):** `NS7_EXEC_20260906` / actor gov-001 / product commit `6317040`  
**Reviewer HEAD at verify:** `1b70c07` (docs + proxy 502 after `6317040`; Execution chrome still that commit)  
**Branch:** `feat/ns-2-brief-nav-collapse`  
**Viewport:** 1280×800 (Playwright `setViewportSize`, re-applied after each navigation)  
**Product:** `http://localhost:3000/stock?lens=execution`  
**Lab referent:** `http://localhost:3000/design-lab/stock?lens=execution`  
**D-0002:** untouched. No `program.py` events. No product-source edits. No commit/push.

This is **implementation-verification + evidence-skeptic**. Claims from CURRENT / NS7_EXEC RESULTS are DATA. Figures below were **re-read on screen**, not copied from the parent.

---

## 1. Verdict

**VERIFIED_WITH_LIMITATIONS**

Product acceptance criteria are independently met on the live UI at 1280×800 against cip NUMBER RULE figures. Lab Execution chrome (HeadlineStrip 3 + PairedBars) is present on production; `PlanVsExecutedView` is relocated, not deleted; nav honesty labels were not promoted.

**Limitation that blocks lawful `complete()`:** engine `design_experience_ok` will fail with `missing target_artifact_class` because N-0017 YAML has `target_artifact_class: null` and the AC list has no structured line `target_artifact_class: high_fidelity`. That is a ledger/engine gate, not a product fail. Delivered class **is** high_fidelity (see §4 / §8). Do not mutate the ledger from this session.

Other limitations (non-blocking for product AC): keyboard not exercised; loading/error empty-states not live-rendered (source + unit test cover them); journeys catalogue `first-path` is skeleton-only; PairedBars x-axis is unreadable at production customer cardinality (challenged in §5, not treated as chrome-missing).

---

## 2. Independence rung used

**R2 — another session.** Fresh GOV-008 context, separate from implementer run `NS7_EXEC_20260906` / gov-001. Own Playwright session against `localhost:3000`. Not R3 (no second-model consult in this run). R2 is the required independence rung for this node’s risk (R2). Planted-false / hash checks are mechanical, not a second LLM.

---

## 3. Anchored implementation_run / commit `6317040`

**FACT — commit exists** (`git cat-file -t 6317040` → `commit`). Subject: `stock: migrate Execution vs plan lab chrome and relocate workspace`.

Files in `6317040` (and still present on disk at review HEAD):

| Path | Role |
|---|---|
| `apps/web/src/features/stock/ExecutionLensView.tsx` | Production Execution lens: HeadlineStrip 3 + PairedBars + relocated workspace |
| `apps/web/src/features/stock/ExecutionLensView.test.tsx` | Unit: headlines + relocated testid |
| `apps/web/src/features/stock/executionRollup.ts` | Customer rollup + under-70% count |
| `apps/web/src/features/stock/executionRollup.test.ts` | Pure rollup tests |
| `apps/web/src/features/stock/StockContainer.tsx` | `lens=execution` mounts `ExecutionLensView` |
| `CONTEXT.md`, `docs/memory/CURRENT.md` | Docs only |

**Mount (source, this tree):** `StockContainer` `StockLensBody` `lens === 'execution'` → `data-testid="stock-execution-lens"` → `ExecutionLensView`. `PlanVsExecutedView` imported from `@/features/plan-vs-executed/PlanVsExecutedView` (file exists; not under stock/). Middleware `STOCK_LEGACY_REDIRECTS['/plan-vs-executed'] = '/stock?lens=execution'`.

**Not in `6317040`:** `CoverLensView.tsx`, `MovementLensView.tsx`, `PlanVsExecutedView.tsx`, `navConfig.ts`, `middleware.ts`.

---

## 4. Dim-by-dim table

Quality states for parent to record on N-0017 (`quality.*.state` + evidence). Engine copy-shapes are in the Evidence column.

| Dim | State | Evidence (one line + pointer) |
|---|---|---|
| design_artifact_class | **pass** | Live production Execution chrome with cip data, not a mockup. `{class: high_fidelity, path: .eif/audit/NS7_GOV008_20260906/independent-rendered-review.md}` |
| design_divergence | **pass** | Named, accepted: P09 fixture → cip `26Q3`; caption adds “in-plan shipped”; workspace stacked below (conservation). Lab live 96 400 / 71 200 / 3 vs prod 32 509 / 6 586 / 10. Charter NUMBER RULE, not silent drift. |
| design_signatures | **pass** | Same signatures on lab + prod at 1280×800: 3-col HeadlineStrip (Plan units / Shipped to date / Customers under 70%), Panel + PairedBars (Plan navy, Shipped cyan), warn tone on under-70 count. Lab: `StockSurface.tsx` `ExecutionLens`; prod: `ExecutionLensView.tsx`. |
| rendered_comparison | **pass** | Side-by-side live renders this session (not source-only). `{artifact_class: high_fidelity, class: high_fidelity, path: .eif/audit/NS7_GOV008_20260906/independent-rendered-review.md, product: /stock?lens=execution, lab: /design-lab/stock?lens=execution, viewport: 1280x800}` |
| design_sameness_review | **pass** | Grammar matches; cardinality and conservation stack differ. **visual_vocabulary_challenge** required text is §5 (non-empty). |
| design_interaction_spec | **pass** | Lens tabs Cover / Movement / Execution vs plan / Sell-through / Forecasts / Supply; Execution selected on `?lens=execution`. Relocated workspace: filters + exception tablist + grids. Strip itself is readout (no write). Paths: product URL + Playwright find + screenshot. |
| design_state_coverage | **pass** | Enumerated: `populated` (live 1280×800 this run); `loading` / `unavailable` copy in `ExecutionLensView.tsx` (not live-rendered this session); unit test populated path `ExecutionLensView.test.tsx`. Evidence.states: `[populated, loading, unavailable]` |
| design_identity_tokens | **pass** | `{tokens: {direction_name: workbench-ui stock execution HeadlineStrip+PairedBars, strip: HeadlineStrip columns=3, chart: PairedBars Plan/Shipped, panel: workbench-ui Panel, figures: HeadlineFigure compact + warn border}}`. Lab `primitives/HeadlineFigure.tsx` re-exports workbench-ui; product charts import `@/features/workbench-ui/charts`. |
| design_execution_decisions | **pass** | Structured map §4.1 below (all three slots). Cannot be `na` on high_fidelity. |
| ux | **pass** | Operator can read plan vs in-plan shipped and under-70 count at 1280×800; workspace conserved below. Chart crowding is §5 (scannability), not a missing job. |
| a11y | **pass** | HeadlineFigure uses two channels for warn (colour + 3px left border) — observed amber on production `10` and lab `3`. Lens control is a tablist. Exception chrome is a tablist. PairedBars exposes as `img` (same as lab Recharts). Keyboard path **not** exercised this session. |
| rendered | **pass** | Playwright: resize 1280×800; `/stock?lens=execution`; `/plan-vs-executed` redirect; lab `/design-lab/stock?lens=execution`; Cover conservation; `/directory` honesty labels. |
| content | **pass** | Production does **not** show P09. Labels: `Plan units 26Q3`, `20% of plan (in-plan shipped)`, relocated caption “Not removed.” Directory still “Partly built” / “Planned”. |

### 4.1 `design_execution_decisions` evidence map

```yaml
responsive_decision:
  status: applicable
  rationale: Verified at charter viewport 1280×800. Three headline figures sit in one strip; PairedBars panel below. Mobile not in N-0017 AC (CURRENT lists mobile evidence as later work).
visualisation_decision:
  status: applicable
  rationale: Lab PairedBars (Plan vs Shipped, height 280) mounted on production via workbench-ui. Live lab shows four named customers; live cip rollup overcrowds the same chart (challenge §5). Headlines carry the NUMBER RULE; chart is the by-customer instrument.
consequential_action_decision:
  status: applicable
  rationale: Execution strip is read-only (correct for vs-plan). Consequential UI is lens change plus relocated PlanVsExecutedView filters/exception tabs. No new write path in 6317040.
```

### 4.2 Verification kinds

| Kind | This run |
|---|---|
| rendered (ui) | **Required and done.** Playwright against live web, 1280×800. |
| referent | Inspected **and rendered**: lab `ExecutionLens` source + live `/design-lab/stock?lens=execution`. R2 `complete()` does not require referent kind; still done. |
| journeys | Catalogue `first-path` is `required_for: [skeleton]` only. Redesign N-0017 has **no** additional required journeys in `.eif/JOURNEYS.yaml`. Empty required-journey set for this class is a catalogue fact, not a hidden skip. |

---

## 5. Visual vocabulary challenge

**Challenge (non-empty):** Is production “the same instrument” as lab Execution, or a headline strip glued onto the old workspace with a chart that cannot be read?

**Observed:** At 1280×800 the **grammar is the same** — uppercase compact HeadlineFigures, three columns, warn wash on “Customers under 70% of plan”, Panel title “Shipped vs plan by customer, {period}”, paired bars with legend **Plan** (navy) and **Shipped** (cyan). Lab live: `Plan units P09` **96 400**, shipped **71 200**, caption **74% of plan**, under-70 **3**, four readable customer names (TechMart, ElectroHub, ValueHome, OfficeWorld). Production live: `Plan units 26Q3` **32 509**, shipped **6 586**, caption **20% of plan (in-plan shipped)**, under-70 **10**. Production x-axis customer names were **not** readable in the viewport (many series vs lab’s four). Production also spends the lower viewport on the conserved Plan vs executed workspace (scorecard, exception tabs, grids) which **does not exist on the lab Execution lens**.

**Call:** Do **not** fail sameness. The NUMBER RULE substitution (P09 → cip `26Q3`) and in-plan caption are accepted charter. Relocating the workspace is an AC, not a cheat. The crowding is a **visualisation consequence of live cardinality**, not a missing PairedBars mount. SHOULD-BE (not this node’s fail): top-N customers or a scroll/brush so the chart remains scannable. Lab DomainHeader CTAs (Open in Reports / Import) vs production StockChrome are prior chrome, not N-0017 scope. Lab sixth lens label **Inbound** vs production **Supply** is prior mapping (`/stock?lens=inbound`), not an Execution fail.

---

## 6. NUMBER RULE re-execution (screen vs 32509 / 6586 / 10 / 26Q3)

Playwright, viewport 1280×800, URL `http://localhost:3000/stock?lens=execution`, logged in (session already on stock).

| Claim (cip SQL/API) | On-screen (this session) | Match |
|---|---|---|
| default_period 26Q3 | Headline **Plan units 26Q3** | yes |
| planned 32509 | **32 509** | yes |
| shipped_in_plan 6586 | **6 586** | yes |
| 20% of plan | caption **20% of plan (in-plan shipped)** | yes |
| customers under 70% = 10 | figure **10** (warn styling) | yes |
| not lab P09 | P09 **absent** on production; present on lab as 96 400 | yes |

Relocated workspace scorecard on the same page (conservation, not the strip): **32,509 planned** / **6,586 shipped against plan** / fill **20.3%** / total shipped in scope **6,930** (6,586 in-plan · 344 unplanned). Consistent with in-plan strip numbers.

**Not claimed as N-0017 fail:** Movement lab-vs-SQL W24 0 vs 1119. This session did not re-prove that delta. Tab 0 remained on `/stock?lens=movement` (surface still mounts). Cover live at `/stock?lens=cover` still shows Cover distribution + weeks-of-cover grid.

---

## 7. Conservation checks

| Check | Result |
|---|---|
| `PlanVsExecutedView` present | **yes.** File `apps/web/src/features/plan-vs-executed/PlanVsExecutedView.tsx`. Mounted under `data-testid="stock-execution-relocated-workspace"`. On-screen caption: “Execution workspace (scorecard, exceptions, drill grids) — relocated below the lab strip. Not removed.” Scorecard + exception tabs + Planned column header observed. |
| `/plan-vs-executed` redirect | **yes, re-executed.** Playwright `goto http://localhost:3000/plan-vs-executed` → final URL `http://localhost:3000/stock?lens=execution`. |
| Cover not rewritten in `6317040` | **yes.** `git diff 6317040^ 6317040 -- CoverLensView.tsx` empty. Last commit on that file: `31712df`. Live Cover lens still renders. |
| Movement not rewritten in `6317040` | **yes.** Last commit `21a11d1`. Live Movement URL still open in sibling tab. |
| `navConfig.ts` not rewritten in `6317040` | **yes.** Last commit `a853a4e`. |
| Partly built / Planned not “completed” | **yes.** `/directory` at 1280×800: **4 partly built · 3 planned** (also 3 data only). Visible **Partly built** on Receipts & POD, Promotion planner, Plan templates, Competitor mappings. Visible **Planned** on Competitor listings, Listing quality / SEO, Audit log. Labels match `leafStatusLabel` (`partial: 'Partly built'`, `planned: 'Planned'`). Not observed as “Works today” on those leaves. |

---

## 8. Blocking findings

### B1 — Engine gate: missing `target_artifact_class` (blocks `complete()`, not product AC)

**FACT.** `.eif/program/PROGRAM.yaml` N-0017:

- `target_artifact_class: null`
- `design_artifact_class: null`
- `acceptance_criteria` has four free-text lines only; **no** line matching `^target_artifact_class:\s*(ia_concept|interaction|high_fidelity)\s*$`

**FACT.** `.eif/runtime/programme/eif_program/design_artifacts.py` `design_experience_ok`:

- Parses target **only** from that structured AC line (`TARGET_LINE`); never infers from prose.
- If no target: `return False, 'missing target_artifact_class'`.

Sibling **stock** node N-0016 (Cover/Movement) is also `target_artifact_class: null` without the AC line (retroactive complete / independence unrecoverable). Sibling nodes that **did** carry the gate (e.g. N-0009 Lineup, N-0013) have both the AC line and `target_artifact_class: high_fidelity`. N-0017 should follow the latter if it is to `complete()` through the engine.

**Recommendation (do not mutate here):** delivered class is **high_fidelity**. Parent should add AC line `target_artifact_class: high_fidelity` so materialized field matches, then record quality/verification pointing at this file. Adding that line is a programme-ledger edit, not product source, and is **not** D-0002.

### B2 — None on product AC

No blocking product finding. Chart crowding is §5 SHOULD-BE.

---

## 9. May parent lawfully complete?

**NO** — not until B1 is fixed on the node.

Even if parent records `quality.*` = pass from this review and `verification` with run `NS7_GOV008_20260906` / actor `gov-008`, `complete()` will still fail `design_experience_ok` → `missing target_artifact_class`.

After the structured AC line exists (and `design_artifact_class` is set to `high_fidelity` from this evidence):

- Dims in this review are **pass** (with limitations disclosed, not fails).
- Warren’s “complete if GOV-008 passes” **may** be taken as operator acceptance for `acceptance: operator` **once** this GOV-008 product verdict is treated as pass. This overall document is `VERIFIED_WITH_LIMITATIONS` **because of B1**, not because the Execution lens failed.
- Do not complete from this session. Do not touch D-0002.

Suggested quality evidence for `design_artifact_class` after B1:

```yaml
class: high_fidelity
path: .eif/audit/NS7_GOV008_20260906/independent-rendered-review.md
```

Suggested `rendered_comparison` evidence must keep `artifact_class: high_fidelity` (engine `_hf_rendered_comparison_ok`).

Suggested `design_sameness_review` evidence must include `visual_vocabulary_challenge` (copy §5).

---

## Methods / coverage

- Playwright MCP (`user-playwright`): tabs, `browser_resize` 1280×800, `browser_find`, `browser_navigate`, viewport screenshots (observed; not checked in as extra audit files).
- Live URLs: `/stock?lens=execution`, `/plan-vs-executed` (redirect), `/design-lab/stock?lens=execution`, `/stock?lens=cover`, `/directory`.
- Source: `ExecutionLensView.tsx`, `executionRollup.ts`, `StockContainer.tsx`, `StockSurface.tsx` `ExecutionLens`, `middleware.ts`, `navConfig.ts` `leafStatusLabel`, `HeadlineFigure.tsx`, `PROGRAM.yaml` N-0017, `design_artifacts.py`, `JOURNEYS.yaml` first-path, `WORK_ITEM.md`.
- Git: `6317040` stat + conservation diffs; Cover `31712df`; Movement `21a11d1`; navConfig `a853a4e`.
- **Not done:** axe; keyboard; mobile; SQL re-run (screen vs parent’s proven cip numbers); Movement W24 delta re-proof; `program.py` complete/verify.

## AS-IS vs SHOULD-BE

- **AS-IS:** Production Execution lens shows lab chrome on cip 26Q3 numbers; old workspace lives below; redirect works; honesty labels intact.
- **SHOULD-BE (not a fail):** PairedBars top-N or brush at live customer counts; N-0017 AC line `target_artifact_class: high_fidelity` before engine complete.
