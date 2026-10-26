# N-0114 and shared Unit C chart/UX review — 25 October 2026

Status: **VERIFIED_WITH_LIMITATIONS; acceptance remains pending.** This is an independent bounded source review and inspection of persisted rendered artifacts, not a live browser rerun or operator acceptance. No product, ledger, service, database, migration or Git mutation was performed by this seat. The only output is this report. The coordinating agent established HEAD `d069f86c9232a735b87c64bb8f3fe3c7b5916b08` on `feat/ns-2-brief-nav-collapse`; this seat relies on that coordinated Git check.

Applied lenses/contracts: ui-visual-design-specialist (UX-003), ux-research-journey-specialist (UX-001), accessibility-specialist (UX-005). Read OVERNIGHT, ASTRA_HANDOFF, memory index/CURRENT, CONTEXT, AGENTS, project rules, cloud handoff, EIF core, PROJECT_MANIFEST, WORK_ITEM and the three specialist contracts. `.cursor/rules/engineering-rules.mdc` is absent; no substitute was invented. Read-only scope permits proceeding with the audit, not implementation.

## Evidence boundaries and independence

- Original chart intent: `PROGRAMME_20261023/N0114_SPEC_PROPOSAL.md`, including the verbatim operator request, caller inventory and render checklist. The proposal's choices and reductions are not approval records.
- Current source inspected: shared `charts.tsx`, `ChartControls.tsx`, `chartRows.ts`; Unit C `V2WidgetBody.tsx`, `V2WidgetCard.tsx`, `ComparisonChart.tsx`, `advancedShape.ts`, `fit.ts`, `shape.ts`, `PivotTable.tsx`, `ViewRowsDrawer.tsx`, editor top-N/sort wiring; `EnterpriseDataGrid.tsx`, `DashboardGrid.tsx`; relevant shipping and sell-through callers; fixture/authenticated browser specs.
- Historical tests were inspected, not rerun by this seat. The earlier full web 1,139 pass predates the last focus correction. Final-source Unit C 121 and fixture browser 6 pass cover that correction. This does not mean every chart, keyboard path, label or production caller was retested.
- Independently opened persisted images with `view_image`: `renders/original-scope/comparison-columns-keyboard.png`, `comparison-fixed-area.png`, `dual-axis-export.png`, `authenticated-fixed-widget.png`, and `visuals-light-390.png`. The full-page mobile capture is too tall for detailed inspection at the displayed scale; it supports the existence/stacking of surfaces, not a pixel-level legibility verdict.
- **UNABLE_TO_RENDER_LIVE in this seat:** no browser/service was started, and the coordinator owns any fresh isolated host/test run. No production request was made. Screenshot inspection is valid static visual evidence, not an observed live journey or screen-reader test.
- Independence achieved here: fresh-context specialist source/artifact review with independent visual inspection of persisted pixels. No tests re-executed by this seat, no attested different-model separation, no R3 verification claim. A separate session or agent does not establish R3.

## Original N-0114 acceptance matrix

Classification numbers follow the operator's six classes: 1 independently verified; 2 implemented with verification limitations; 3 partial; 4 absent; 5 genuine decision blocked; 6 originally excluded. Whole requirements receive the weakest material status; source mechanisms do not establish full runtime acceptance.

| Original requirement | Class | Current evidence and remaining acceptance gap |
|---|---:|---|
| Shared chart components first, then every dashboard/report chart | 3 | Shared grammar is present in `charts.tsx`; legacy WidgetChart uses it. Unit C adds non-period categorical paths through TrendChart that bypass category wrapping/orientation/controls (F-UX-01). All named production caller screens have not been authenticated/rendered. |
| Every axis titled with units | 3 / 5 for unresolved measure semantics | Shared HTML axis captions and dual-axis captions exist. Shipping still plots `quantity ?? count` and uses untitled units (`ShippingCommercialSummary.tsx:152,233-234`); SellThrough sales value stays `number` / `Sales value` (`SellThroughOverview.tsx:142-143`). Those cannot honestly receive a currency/unit without authoritative domain resolution. Comparison capture hides the lower axis until inner scrolling (O-UX-01). |
| Legend for multiple series; optional for one | 2 | `ChartLegend`, PairedBars and TrendChart support wrapping legends; the captured comparison/area/dual-axis visuals show legends. Full caller/browser and screen-reader proof remains absent. Comparison builds separate sparse series per category; long legends increase the scroll problem. |
| Long labels wrap/angle; full name on hover | 3 | `categoryTick` wraps to two lines and retains SVG title; tooltip retains full label. Plain CategoryBars/PairedBars/RankedBars implement this. Comparison and two-measure category TrendChart use plain SVG X-axis ticks, no category wrapping/orientation grammar. Touch and keyboard access to all full names is unproven. |
| Automatic horizontal bars for long/many labels | 3 | `chooseCategoryLayout` implements >8 labels or >14 characters, used by CategoryBars/PairedBars. Unit C comparison columns and two-measure category columns bypass it (F-UX-01). |
| Pie legend shows full names | 2 | ShareChart uses wrapping full labels, values and full-total percentages; no `noWrap` in this legend. Fixture screenshots/tests exist. Authenticated long-name/mobile interaction is not proven. |
| User top-N 5/10/15/25/all | 3 | Shared ChartControls supplies those options and non-mutating slicing. Editor-saved top-N for `bar` is ignored in the renderer; comparison/two-measure category columns have no viewer top-N (F-UX-02). Viewer choices remain local; not all persistence was promised by N-0114. |
| User sorting by value, name, period | 3 | `sortRows` provides numeric/name/input-period ordering. Toolbar is hidden below six rows even though sorting still matters; period charts suppress controls. A PairedBars user who changes away from As listed loses that menu choice (F-UX-03). Saved query sort is overridden by single-measure bar defaults (F-UX-02). |
| Unit-aware R, US$, units and % formatting; do not change values | 2 / 5 for unresolved semantics | `formatChartValue` formats all styles; pure sort/slice helpers preserve row values; hidden-table integrity tests are historical evidence. Actual tick/tooltip/full-value caller coverage is narrower. Decimal-point and removal-of-Other proposals require their actual decision status to be checked, not inferred from implementation. No financial number was changed in this review. |
| Desktop 1280x800, mobile 390x844 | 2 | N0114_RENDER documents fixtures and a historical horizontal-overflow fix; Unit C Playwright checks actual 1280/390 viewport and document width. Authenticated test uses default desktop only. No complete authenticated caller matrix, zoom/reflow or mobile touch proof. |
| Light and dark | 2 | Final fixture tests assert computed card background and capture all current visuals/starters in both modes. Inspected dark widget/export captures are readable at their native scale. No measured contrast audit or authenticated dual-theme matrix. |
| Accessibility / keyboard / equivalent data access | 3 | ChartFigure supplies a named figure and hidden semantic table; legends use buttons; scatter/dual-axis have explicit keyboard category controls; pivot has Enter handling. Plain categorical bar/ranked-bar and table filtering have pointer-only wiring (F-UX-04). Screen-reader, contrast and zoom acceptance remain unproven. |
| Shared-chart regression safety after Unit C | 3 | Later focused 121 and fixture 6 evidence includes focus correction and shared rendering; it does not cover the category grammar regressions or editor top-N mismatch identified here. Full web 1,139 is pre-focus-fix evidence, not final-source full-suite proof. |
| Authenticated application rather than fixtures alone | 3 | `builder-auth.spec.ts` exercises real isolated cip_test auth/API for one DSI product bar, fixed dates, edit/reopen, duplicate/reload, CSV and promotion. Persisted screenshot is an actual **horizontal bar**, not a visible AG Grid table; the spec's `getByRole('table')` reads the chart's hidden accessible table. It does not verify every original page, visual or theme. |
| No new UI/chart library; preserve MUI/Recharts/AG Grid/workbench architecture | 2 | Inspected implementation uses the prescribed components. No unrelated redesign or replacement is proposed. |

N-0114 therefore stays open. The shared foundation is substantial; acceptance is not justified by fixture coverage alone and Unit C introduces concrete integration gaps.

## Confirmed source defects / bounded execution targets

### F-UX-01 — category grammar regresses on Unit C comparison and two-measure columns

Severity: **moderate**, affecting N-0114 long-label/orientation/top-N requirements and N-0116 S9/S16.

`ComparisonChart.tsx:44-51` always renders TrendChart, including a non-period category bar. `V2WidgetBody.tsx:507-529` does the same for two-measure category columns/combo. `charts.tsx:1133` uses plain XAxis ticks in TrendChart; it has no category layout helper or ChartControls. Thus adding comparison or a second measure removes the automatic-horizontal/wrapped-label/top-N experience that the normal category bar gets. This is a source-verifiable path difference; exact visual failure with long labels needs a new targeted browser case.

Fix direction: extend/reuse the shared category-series renderer for grouped current/prior and two-measure categories; retain chronological TrendChart for real time axes. Acceptance: 12 distinct long customer labels, both modes and both widths, full names accessible, automatic orientation, top-N/sort usable, comparisons aligned and totals unchanged.

### F-UX-02 — saved bar top-N and query sort do not govern the rendered bar

Severity: **moderate**, S8/S9 configuration fidelity.

`BuilderEditorDialog.tsx:242,742-754` retains and exposes `display.top_n` for `bar`/`hbar`. `V2WidgetBody.tsx:443-454` supplies CategoryBars without the configured top-N/controls, so it starts at the shared default 10 (`charts.tsx:750`). `hbar` receives top-N but hard-codes `sort="desc"` (`V2WidgetBody.tsx:430`); CategoryBars likewise defaults to value-desc even when the editor's query sort is name or value-ascending. Comparison and two-measure bar paths ignore top-N altogether. For a bar with >10 returned categories, save Start with top 5: the renderer starts with 10. The data is not changed, but the user's saved presentation intent is ignored.

Fix direction: carry the saved presentation controls into the canonical renderer and define explicitly whether query sorting or viewer controls own initial order. Acceptance: editor preview, save/reload, duplicate and full screen all start with the chosen top-N/order; viewer changes remain coherent.

### F-UX-03 — chart sort menu drops the original ordering option

Severity: **moderate** for preserving meaningful order; small bounded fix.

`ChartControls.tsx:77` computes `showInputOrder = timeAxis || current === 'period'`. PairedBars starts with `period`/As listed; after selecting Name or Highest first, current is no longer period and the option disappears. A user cannot return to the original order within the same mounted chart. Also `CONTROLS_MIN_ROWS=6` hides sort for <=5 rows based only on top-N utility; the original user sorting requirement did not exclude small sets.

Acceptance: switch As listed -> Name -> As listed without remounting; sort a four-category chart where sorting is meaningful; ordered time/bucket callers remain deliberately fixed where appropriate. No business-rule approval is needed for restoring an existing option.

### F-UX-04 — keyboard activation is incomplete for plain chart/table filtering

Severity: **serious accessibility gap** pending rendered reproduction; S10 explicitly requires keyboard activation.

CategoryBars uses Bar `onClick` only (`charts.tsx:831-841`); RankedBars uses Bar `onClick` only (`charts.tsx:1426-1443`). Their Unit C paths add no keyboard alternative. Table filtering is only `onRowClicked` (`V2WidgetBody.tsx:300-307`), and EnterpriseDataGrid forwards that callback without adding Enter activation (`EnterpriseDataGrid.tsx:68,135`). ChartFigure's hidden table contains read-only th/td, with no buttons or callbacks (`charts.tsx:499-550`): the proposal's claim that it already provides Enter filtering is false. Period-only TrendChart's point filter also lacks a category/period button alternative. Library default arrow-key chart navigation is not evidence that it dispatches the domain filter.

Positive exceptions: ShareChart legend buttons, comparison category legend buttons, scatter/dual-axis details/buttons (`V2WidgetBody.tsx:350-362`), and pivot `onCellKeyDown` already implement keyboard paths. Do not regress them or re-open the corrected full-screen focus defect.

Fix direction: reuse a labelled keyboard selection path at the shared renderer boundary or accessible datum controls, and add a table Enter handler. Acceptance: keyboard-only user can focus/apply/clear the same category/date filters, including multi-select where supported; full name/value is discoverable; no pointer required. Test plain bar, hbar, table and period-only chart, not just the existing comparison legend case.

### O-UX-01 — comparison legends push axes below the card's inner viewport

Observation, **moderate usability concern**, not evidence that content is permanently lost.

`comparison-columns-keyboard.png` shows an eight-entry legend followed by only the top of the plot: lower bars, category ticks and axis title are absent at scroll position zero. `V2WidgetBody.tsx:323-334` deliberately uses a 240px frame with vertical scrolling; the plot alone is 176px before legend/captions, so the content can be reached by inner scrolling. The fixture asserts axes/notes attached, not that the complete chart is simultaneously visible. A dashboard card with unused space below its fixed inner frame makes that affordance particularly unclear.

Proposal: size the plot from measured available card content, reserve measured legend/caption space, or make overflow/expand discoverable. Add viewport-intersection checks for axis titles and meaningful chart marks at standard saved sizes, including long comparison legends. Do not count mere DOM presence as visible readability.

## Other Unit C visual and journey conclusions

| Area | Current status and limits |
|---|---|
| Mixed units | `fit.ts` rejects mixed units on a shared axis; dual-axis uses separate units/titles. The inspected PNG shows US$ left and % right correctly. No new source defect found in this bounded review. |
| Scatter | Real ScatterPlot, omits rows missing either value with a caption, plus keyboard category buttons. Fixture pointer click exists. Authenticated scatter and keyboard-control browser coverage remain missing. |
| Pivot | Client reshapes two breakdowns, refuses duplicate cells and >24 categories, keeps nulls, sums only additive complete rows, shows server grand totals and Enter filtering. Refusal wording says columns but the limit counts categories: two measures can create >24 value columns; clarify/test original intended limit before calling it fully accepted. |
| Table conditional colour | Rules exist and expose aria text plus a dot; a same-shape dot differentiated only by colour does not give a sighted colour-blind user the semantic good/warn/bad distinction. Native title is hover-dependent. Need rendered contrast and non-colour visual/keyboard checks. This is an evidence/design gap; no threshold should be invented. |
| Dashboard drag/resize | V2 drag span has role=button without tabIndex/keyboard handler; DashboardGrid uses pointer drag/resize. No keyboard layout alternative is evidenced. Report as incomplete full accessibility, not a failure of the already-fixed dialog focus path. |
| View rows | Honest grouped-row drawer and `Total at this grouping`, no equality claim for non-additive totals; current-period-only caption when comparison. Source-line drill is an explicit S20 exclusion. Actual authenticated drawer / mobile focus coverage is absent. |
| CSV | Real authenticated browser inspects downloaded CSV for seeded values and fixed-window exclusion. This is narrower than arbitrary visual/compare export parity. |
| PNG | Fixture downloads an actual SVG-rendered PNG; inspected dual-axis export has title, filters, units, legend and chart. Only charts are enabled; KPI/table/pivot explain CSV alternative. No authenticated arbitrary-visual PNG proof. |
| PDF/XLSX | Existing server/report export evidence belongs to the coordinating backend review; this seat did not execute exports. Widget menu itself offers CSV/PNG, promotion hands off to reports. Do not mislabel all four formats as freshly authenticated browser verified. |
| Full screen | Final Playwright spec explicitly checks initial Close focus, reverse-Tab containment, Escape and return to trigger. Historical final result passes; this seat did not rerun. Earlier failures are superseded for the pinned corrected source. |
| Error/empty/refused/loading/truncated | Components and fixture coverage exist; authenticated error/recovery journeys are not established by the single successful DSI workflow. |
| Starter dashboards | Captures/fixture spec render 8+6+8 widgets. This does not establish completeness of the original commercial starter requirements or real model semantics. Those remain the product/model review's responsibility. |

## Next bounded verification/implementation frontier

1. **Preserve and independently reproduce F-UX-02 and F-UX-04** on final source with focused tests. Specific reason for new tests: current test suite passes while these configuration/keyboard branches are untested. No full-suite repetition is needed before a fix exists.
2. **One canonical category rendering unit** for F-UX-01/F-UX-02: extend shared category controls/series support and wire Unit C into it. No new chart library or duplicate writer/render system. Preserve nulls, identity keys, server totals, mixed-unit refusal and comparison gaps.
3. **Keyboard parity unit** for chart/table filtering; include period selection and grid layout alternative if the node's full-accessibility bar includes layout editing. Keep corrected full-screen focus test.
4. **Small controls unit** for F-UX-03; explicit existing-order capability independent of current selected option, with small-set sorting where meaningful.
5. **Targeted isolated rendered pass**: long category/current-prior/multi-measure bars at 1280x800 and 390x844, light/dark; real keyboard selection, long-name touch/hover, axes visible in card and full screen, tooltip viewport containment, conditional-colour contrast, 200/400% zoom and accessibility tree. Existing rolled-back cip_test browser harness is the approved path; no production restart or migration.
6. **Authenticated original caller coverage**: reuse approved fixtures/harness to check N-0114's named shipping, market, planning, execution, stock, supply, report and dashboard caller classes. Any caller requiring unapproved production access remains explicitly unproven.

Ownership: coordinating agent must use supported EIF verification/ownership workflow before recording node evidence or implementation events. This seat acquired no implementation lease. Proposed numerical style/top-N-tail and ambiguous shipping/sales-value decisions must remain pending until the actual D-0116–D-0130 event status/authority is checked by the coordinator. Current source semantics, passing fixtures and this review grant no acceptance.
