# Reports, dashboards and KPI visuals vs the design lab (Audit Mode, 2026-10-09)

Warren 2026-10-08: "check why the report graphs, tables, and KPIs look like shit and don't match the design lab style".
Lenses: ui-visual-design-specialist, design-system-specialist, frontend-engineer, accessibility-specialist (render run cut off by a usage limit before writing; this report is written by GOV-001 from its saved evidence plus code reads).

**Evidence.** `.eif/audit/PROGRAMME_20261008/reports/`: lab and production screenshots, 1440x900, light and dark, rendered with Playwright (`render.cjs`). Signed-in production pages were rendered with the API mocked in the browser (fixture identity `audit@example.test`, fixture numbers): no account, no credential, no cip access. The screenshots therefore show the real production components drawing fixture data. Proposed direction: `mockup-report-system.html` (+ PNGs at 1440 and 390, light and dark). Not product source.

## Root cause (FACT, code)

The lab's chart primitives were ported to production as `apps/web/src/features/workbench-ui/charts.tsx` (`ChartFrame`, `CategoryBars`, `PairedBars`, `TrendChart`, `ProportionBar`, same exports as `design-lab/primitives/charts.tsx`). The containers that were migrated from the lab use them: Stock Cover/Movement/Execution, Supply overview, Planning overview, Case book, Market listings.

The report and dashboard surfaces never moved onto them:

| Surface | Draws charts with | KPI | Lab primitive used? |
|---|---|---|---|
| Reports builder `features/reports/ReportBuilderView.tsx` | raw `recharts` (line 40) | bare number under "VALUE" | **No** |
| Dashboard widgets `features/dashboards/WidgetChart.tsx` | **ECharts** (a second chart library, lines 5-8) | own | **No** |
| Shipping commercial summary `app/(app)/shipping/ShippingCommercialSummary.tsx` | raw `recharts` (line 17) | own | **No** |
| Channel ops overview `app/(app)/sell-out/ChannelOpsOverviewTab.tsx` | raw `recharts` (line 18) | `ChannelOpsKpiCards` | **No** |
| Plan vs executed `features/plan-vs-executed/PlanVsExecutedView.tsx` | raw `recharts` (line 38) | own | **No** |
| Stock, Supply, Planning, Case book, Market | `workbench-ui/charts` | `HeadlineFigure` | Yes |

Two KPI components also exist side by side: `components/KpiCard.tsx` (old) and `features/workbench-ui/HeadlineFigure.tsx` (lab-derived).

## Findings, ranked by user impact (AS-IS, screenshots)

1. **KPI result is a bare number.** Reports KPI shows `4.37` under the label "VALUE": no metric name, no unit (weeks), no comparison period or delta, no target, no trend (`prod-reports-kpi-*.png`). Lab and mockup: metric, value + unit, delta vs last period, target, sparkline, state.
2. **Bar charts cannot be read.** No category labels on the axis (you cannot tell which bar is which distributor), unsorted, no value labels, no threshold, one colour for every bar (`prod-reports-bar-*.png`). Lab/mockup: horizontal bars with names, sorted low-to-high, direct value labels, 4-week threshold line, colour by state (stop < 2w, warn < 4w).
3. **Engineering vocabulary on screen** (`ReportBuilderView.tsx` 375 "Allowed: {...}", 384 "Formula: soh / avg_weekly_sell_out", 411 free-text "Distributor id (optional)", 532-534 `invariants_applied` chips "tenant_scope", "latest_snapshot"; raw metric keys such as `weeks_of_cover` in the result header). Same "Formula:" line in `WidgetEditorDialog.tsx` 106. Breaks the naming rule (names, not codes/keys) and the N-0066 polish pass.
4. **Wrong page identity.** The Reports page renders the heading "Overview" and the Overview description (`prod-reports-*.png`), under breadcrumb "Overview / Reports".
5. **Buttons wrap to two lines** ("Run / report", "Export / Excel", "Export / PDF", "Send to / inbox", "Schedule / delivery") with mismatched heights; two disabled buttons with no reason shown.
6. **Saved reports panel is a bare list** with a large empty area; the lab shows summary tiles (saved, scheduled, runs this week, runnable metrics), pinned badges and recent runs.
7. **Layout bug:** in `prod-reports-bar-light.png` the top bar is drawn partway down the page over the content (sticky header / scroll container).
8. **Tables:** report result tables lack right-aligned numerics, units in headers, a totals row and state chips; the mockup shows the target (totals recomputed, not averaged ratios; names first, codes in their own column).
9. **Two chart libraries** (recharts + ECharts) mean two palettes, two tooltip styles and two font stacks; dashboard widgets will never match the lab while they use ECharts.
10. Light/dark: lab primitives read tokens from `cipTheme`; the raw recharts/ECharts surfaces use hard-coded colours and default axis/grid styling, so dark mode parity is inconsistent (`*-dark.png`).

## SHOULD-BE

- **One chart system:** every surface uses `features/workbench-ui/charts.tsx` (recharts, lab tokens). Retire ECharts from dashboard widgets. Add what reports need to the shared set: horizontal sorted bars with direct labels and threshold, line/trend with last-point label, state colouring from tokens, number/unit formatting helpers, accessible names and data tables for charts.
- **One KPI tile:** `HeadlineFigure` (extended to the mockup: label, value + unit, delta with direction and period, target, sparkline, loading/empty/stale states); retire `components/KpiCard.tsx`.
- **One result table style:** existing grid wrapper with right-aligned numerics, units in headers, totals row recomputed from sums, status chips, names first and codes in their own column.
- **Reports page in the lab layout:** correct heading; metric catalog grouped by family; question-first chips (Metric · Grain · Scope) in plain words; no formula/allowed-grain/invariant text (move to an "About this figure" disclosure for admins); pickers instead of free-text ids; single-line buttons; Saved reports with pinned and recent runs.

## Proposed node

"Reports, dashboards and KPI tiles on the lab design system" — R2, facets ui, design_experience. Scope: `ReportBuilderView.tsx`, `features/dashboards/**` (WidgetChart off ECharts), `ShippingCommercialSummary.tsx`, `ChannelOpsOverviewTab.tsx`/`ChannelOpsKpiCards.tsx`, `PlanVsExecutedView.tsx`, `workbench-ui/charts.tsx` + `HeadlineFigure.tsx` extensions, `KpiCard.tsx` retirement, dependency removal of ECharts (dependency_change). Size L (split per surface). Acceptance: rendered light and dark at 1440 and 390 for every listed surface compared against the lab and mockup; no engineering vocabulary visible to non-admins; numbers identical before/after (same API responses); a11y contrast and chart text alternatives; tests and tsc/eslint green.

## Taste calls for Warren

1. Adopt the mockup direction (`mockup-report-system-light.png`) as the target for reports and dashboards.
2. State colours on bars (red < 2 weeks, amber < 4 weeks) — or neutral bars with a threshold line only.
3. Keep "About this figure" (formula and scope) visible to admins only, or to everyone behind a disclosure.
