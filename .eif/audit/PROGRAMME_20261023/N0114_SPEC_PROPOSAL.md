# N-0114 Chart fixes: spec proposal

Status: PROPOSAL (definition moment; lenses: product-interaction-designer, ui-visual-design-specialist, analytics-bi-specialist). Not implementation authority. Written 2026-10-23 from a source read only: no rendered inspection in this pass (UNABLE_TO_RENDER: no browser step run). Every AS-IS claim below is from source.

Operator's words (verbatim): "Chart fixes (shared chart components first, then every dashboard and report chart): axis titles with units on every axis; legend whenever a chart has more than one series, optional on single series. Long names never cut short: wrap or angle, full name on hover; horizontal bars automatically when labels are long or many. Pie legend shows full names. User-set top N (5/10/15/25/all) and sort (value, name, period). Number formatting matches units (R, US$, units, %). Render light/dark at 1280x800 and 390x844."

Constraints: no new chart or UI library (Recharts and MUI only); reuse `features/workbench-ui`; names only in Customer and Distributor; never change a number (only how it is formatted and laid out).

---

## 1. AS-IS against each operator point

All paths are under `apps/web/src/`. `charts.tsx` means `features/workbench-ui/charts.tsx`.

| Component | Axis titles | Legend | Long names | Auto horizontal | Top N / sort | Units |
|---|---|---|---|---|---|---|
| `CategoryBars` (charts.tsx:263-327) | none | none (single series only) | vertical: no truncation, angled -32 deg only when `compact` (297); horizontal: fixed `width={150}` (305) with Recharts' default tick, which wraps into overlapping lines (see comment at 590) | only when the caller passes `horizontal` | none | default `toLocaleString('en-ZA')` (286), a decimal comma ("4,37") that the file itself warns against (41-44) |
| `PairedBars` (329-373) | none | always on (367), Recharts default at the bottom | **cut to 10 chars + ellipsis** (363), no hover title | no horizontal mode at all | none | same en-ZA default (351) |
| `TrendChart` (375-485) | none | `legend` defaults to `true` (383) even for one series | X ticks are periods: fine | n/a (time axis) | n/a | same en-ZA default (403) |
| `RankedBars` (518-644) | none (value axis untitled; `labelHeader`/`valueHeader` go only to the hidden table) | none (single series) | truncated by an estimated char width (556-559), `<title>` holds the full name (595), width capped at 240 px (555) whatever the chart width | always horizontal | internal `sort` and `max=20` (524); rows beyond `max` are dropped silently, with no "Top 20 of 37" caption | caller's `format` |
| Pie / donut: only in `features/dashboards/WidgetChart.tsx:80-121` (raw Recharts, not shared) | n/a | HTML legend, **`noWrap`** (110) cuts long names; `title` attribute gives hover only | as left | n/a | fixed `PIE_SLICES = 6` with the tail folded into "Other (n)" (`widgetModel.ts:30, 98-104`) | `formatValue(v, unit)` -> `formatMeasure(...,'short')` |
| `WidgetChart` column bars (140-156) | none | none | **cut to 11 chars** (145) | the user picks `hbar` or `bar` by hand | fixed `TOP_N = 15` + Other (`widgetModel.ts:29`) | as above |
| `WidgetChart` period x category (160-200) | none | Recharts default (169) | n/a | n/a | `SERIES_MAX = 7` + Other (`widgetModel.ts:31, 140-171`) | as above |
| `WidgetChart` single series (202-234) | none | none | n/a | n/a | n/a | as above |
| `Sparkline`, `ProportionBar`, `StateKey` (647-732) | no axes by design | n/a | n/a | n/a | n/a | n/a |

Other AS-IS facts that bear on the spec:
- Formatting: `formatNumber` / `formatMeasure` / `unitWord` (charts.tsx:37-117). `MeasureUnit` has **no ZAR kind** (37). `usd` prints `$1 234` in `short`/`long` style (98) and `unitWord('usd')` is `'USD'` (65); the operator asks for `US$`. Percent values are governed ratios (0.86 -> "86.0%", 93-95).
- Three separate compact formatters exist: `formatMeasure` (charts.tsx), `fmtCompact` in `features/stock/SellThroughOverview.tsx:50` ("1.23m", no unit) and `fmtCompact(amount, ccy)` in `features/promotions-funding/format.ts:4` ("R1.2m", "$12k").
- The metric unit table is `metricPresentation` in `features/reports/reportPresentation.ts:156-196`; dashboards read it through `metricUnit` (`widgetModel.ts:174`). Column headers already add units via `headerWithUnit` (reportPresentation.ts:313).
- The hover cursor is `rgba(255,255,255,0.04)` (charts.tsx:309, 366): invisible on a light background.
- Chart margins use `left: -12` (289, 354, 432), which leaves no room for a Y-axis title.
- Theme: `stores/uiStore.ts` holds `colorMode` ('light' | 'dark', default 'dark', persisted in localStorage key `cip-ui`). `app/providers.tsx:18` feeds it to `CipThemeProvider`. The design lab (`app/(design-lab)/design-lab/layout.tsx`, `design-lab/shell/LabShell.tsx`) runs under the same providers, so lab pages follow the same mode. Lab navigation is registered in `design-lab/shell/labNav.ts`.
- The design lab has its own older copy, `design-lab/primitives/charts.tsx`, which is used only by lab surfaces.

## 2. Changes to the shared components (all in `features/workbench-ui/`)

### 2.1 Units and number formatting (`charts.tsx`, extending the existing helpers; no new file)
- Add `'zar'` to `MeasureUnit`. `unitWord`: `zar -> 'R'`, `usd -> 'US$'` (changed from 'USD'; this changes text only, never a number).
- New pure function `formatChartValue(v, unit, style: 'tick' | 'label' | 'full'): string`. Grouping uses `formatNumber` (a space for thousands and a decimal point, per the existing convention at charts.tsx:41-44).

| unit | tick (compact) | label (bar end / last point) | full (tooltip, data table) |
|---|---|---|---|
| zar | `R 1.2 M`, `R 850 k`, `R 9 500` | same as tick | `R 1 234 567` (2 decimals when \|v\| < 100) |
| usd | `US$ 1.2 M` | same as tick | `US$ 1 234 567` (2 decimals when \|v\| < 100) |
| units | `1.2 k` (bare: the axis title carries "units") | `1.2 k` | `1 234 units` |
| count | `1 234` / `12.3 k` | same | `1 234` |
| percent (ratio in) | `86%` (0 decimals; 1 decimal if the tick step is below 1 pp) | `86.0%` | `86.0%` |
| weeks | `5.4` (bare) | `5.4w` | `5.4 weeks` |
| days / quarters | bare | `12d` / `1.5q` | `12 days` / `1.5 quarters` |
| number (unknown) | compact bare | compact bare | `formatNumber(v, 2)` |

  Compact steps: below 10 000, full grouping; 10 000 to 999 999 -> `k` (1 decimal under 100 k); 1e6 and up -> `M` (1 decimal); 1e9 and up -> `bn`. Negative values keep the sign before the symbol (`-R 1.2 M`). Null or non-finite values give `—`.
- `formatMeasure` keeps its signature. Its `usd` short/long prefix changes from `$` to `US$ `, so report tiles say the same thing as the charts (tests updated). Every other branch stays as it is.
- Every shared chart takes `unit?: MeasureUnit`. When `unit` is set it drives ticks, labels, tooltips and the hidden table. The existing `format` / `axisFormat` props stay as overrides for back-compat; callers migrate to `unit` in §3. The default formatter (when neither is passed) becomes `formatChartValue(v, 'number', …)`, which removes the en-ZA decimal-comma default (286, 351, 403).

### 2.2 Axis titles
- New props on `CategoryBars`, `PairedBars`, `TrendChart`, `RankedBars`: `xAxisTitle?: string`, `yAxisTitle?: string`. The string already includes the unit, e.g. "Units sold (units)", "Sales value (R)", "Fill rate (%)". The helper `axisTitle(label, unit)` reuses `unitWord` and skips the bracket when the label already names the unit (same rule as `headerWithUnit`).
- Placement (one rule for all charts, so 390 px never needs rotated text):
  - **Value axis on vertical charts:** an HTML caption above the plot, top-left, `variant="caption"`, `color="text.secondary"`, wrapping. It is not a rotated SVG label.
  - **Category or time axis on vertical charts:** a Recharts `label` with `position: 'insideBottom'`. XAxis height grows by 16 px.
  - **Horizontal bars:** the value-axis title sits under the axis (Recharts label `insideBottom`). The category-axis title is an HTML caption above the label column.
- Margins: `left: -12` becomes `0` wherever a title is present.
- Dev guard: in development, `console.warn` once when a chart with axes renders without both titles. The guard has no runtime effect in production.

### 2.3 Legend
- New shared `ChartLegend({ items: {label, color, value?, share?}[] })`. It is HTML and sits above the plot. It uses flex-wrap, shows full names, never uses `noWrap`, and its swatches use the series colour. It reuses the `StateKey` styling (charts.tsx:647).
- Rule: the legend shows when there is more than one series. For one series it shows only when the caller passes `legend`.
  - `TrendChart`: the default for `legend` becomes `series.length > 1` (from `true`).
  - `PairedBars`: always shows (2 series).
  - `CategoryBars` / `RankedBars`: none, unless `legend` is passed explicitly.
- Recharts' `<Legend>` is removed from the shared charts in favour of `ChartLegend`, so wrapping and full names behave the same everywhere.

### 2.4 Long category names (pure helpers in charts.tsx plus one tick component)
- `chooseCategoryLayout(labels: string[], { timeAxis?: boolean, force?: 'vertical' | 'horizontal' }) -> 'vertical' | 'horizontal'`: returns horizontal when `labels.length > 8` or the longest label is over 14 characters. A time axis is never flipped. `force` wins over the rule.
  - Applies to `CategoryBars` (new prop `layout?: 'auto' | 'vertical' | 'horizontal'`, default `'auto'`; the existing `horizontal` prop maps to `force`).
  - Applies to `PairedBars` (gains a horizontal mode, grouped bars along the category axis).
  - Applies to `WidgetChart` `bar` with a category grain.
- `wrapLabel(text, maxCharsPerLine, maxLines = 2) -> string[]`: breaks at word boundaries, then hard-breaks words that are too long. The last line ends with `…` when text is left over.
- `CategoryTick` (a custom SVG tick):
  - Vertical layout: up to 2 `<tspan>` lines from `wrapLabel`, with `maxCharsPerLine` derived from the band width (`bandPx / 6.4`).
  - Fallback: if the band is under 40 px even after the 2-line wrap (many bars at 390 px), the tick angles -35 deg on one line with ellipsis. At that point the auto rule normally flips the chart to horizontal anyway.
  - Every tick carries `<title>{full}</title>`.
  - The tooltip's `labelFormatter` always shows the full name. This is the touch path, because `<title>` does not show on touch.
  - Tooltip `contentStyle` gets `maxWidth: 280, whiteSpace: 'normal'`.
- `horizontalLabelWidth(labels, chartWidth) = clamp(longestChars * 6.4 + 12, 64, 0.45 * chartWidth)`.
  - Labels longer than the width get an ellipsis, and the full name stays available on hover and tap.
  - Replaces RankedBars' fixed 240 cap (555) and CategoryBars' fixed 150 (305).
  - `labelWidth` stays as an explicit override.
  - `chartWidth` comes from a small `useElementWidth(ref)` hook (ResizeObserver) on `ChartFrame`'s Box. This adds no library.
- Row height for horizontal layout: `max(26, lines * 14 + 10)`, so wrapped labels never overlap.

### 2.5 Pie and donut: `ShareChart` (new export in charts.tsx, moved out of WidgetChart)
- Props: `{ data: {label, value}[], unit, variant: 'pie' | 'donut', summary, total? }`.
- Legend rows show a swatch, the **full name (wrapping, no noWrap)**, the value (`full` style) and the share (`12.3%`).
- Shares are computed against the full total of every category, not only the slices shown. When slices are hidden by top N, the caption reads "Top 5 of 12 shown · shares are of the full total". No synthetic slice is drawn.
- Layout: at 1280, pie and legend side by side (pie 40%). Below the `sm` breakpoint, the legend stacks under the pie (`direction={{ xs: 'column', sm: 'row' }}`).
- The hidden data table lists every slice (name, value, share).

### 2.6 `ChartControls` toolbar (new file `features/workbench-ui/ChartControls.tsx`, plus pure helpers in `features/workbench-ui/chartRows.ts`)
- `applyTopN<T>(rows: T[], n: 5 | 10 | 15 | 25 | 'all') -> { shown: T[]; total: number }`. A pure slice of already-sorted rows. **It never adds an "Other" row and never alters a value.**
- `sortRows<T>(rows, { by: 'value' | 'name' | 'period', dir?: 'desc' | 'asc' }, accessors)`:
  - `value`: numeric, desc by default, nulls last, ties broken by name.
  - `name`: `localeCompare(…, 'en', { sensitivity: 'base', numeric: true })`.
  - `period`: restores the input order. Callers already supply rows chronologically, so period strings are never re-parsed.
- `topNCaption(shown, total)`: "Top 10 of 37" when truncated, else null.
- UI:
  - An MUI `ToggleButtonGroup` (size small) for top N: 5 / 10 / 15 / 25 / All.
  - An MUI `Select` for sort: "Highest first", "Lowest first", "Name A–Z", plus "Period" only when `timeAxis`.
  - The caption sits at the right of the toolbar.
  - At 390 px the toolbar wraps to two rows, the toggle group scrolls inside its own box (`overflowX: auto`), and the page never scrolls sideways.
- Where it shows:
  - On category-axis charts only: `CategoryBars` (non-time), `PairedBars` (non-time), `RankedBars`, `ShareChart`, and WidgetChart category bars and pies.
  - Hidden on time-axis charts (`TrendChart`, period columns): there, top N and sort have no meaning.
- Defaults:
  - RankedBars and category bars: 10, Highest first.
  - Pie: 5 (with 9 or fewer slices: All).
  - Existing explicit `max` / `sort` props become initial values.
- State is component-local (`useState`). An optional `controls={{ topN, sort, onChange }}` prop lets a container own it. Reports already have a sort and cap, so they pass their state in.
- `RankedBars` keeps `rankBars` (tested and used by reports). It gains the caption whenever `shown.length < total`, whether or not controls are shown.

### 2.7 Small fixes carried with the pass
- Tooltip cursor: `theme.palette.action.hover` instead of white at 4% opacity (charts.tsx:309, 366).
- `TrendChart` gets `stack?: boolean` (a `stackId` per series kind), so `WidgetChart` period x category can use the shared chart instead of raw Recharts.
- Colours: move WidgetChart's validated `SERIES_LIGHT` / `SERIES_DARK` slots (WidgetChart.tsx:37-38) into `useChartTheme` as `series[]`. Multi-series shared charts use them when no `tone` is given, so dashboards and pages share one categorical palette.

## 3. Per-caller change list

A unit marked "?" is not determinable from source. The caller passes the title without a unit until it is confirmed (see §6).

| Caller (file:line) | Component | xAxisTitle | yAxisTitle / value axis | unit | Notes |
|---|---|---|---|---|---|
| `app/(app)/shipping/ShippingCommercialSummary.tsx:227` | CategoryBars, horizontal | value: "Arriving this week (units)" | category: "Distributor" | `units` | **The caller pre-truncates names to 14 chars at :150.** Pass the full `d.label` as `name` and drop `fullName`. The value is `d.quantity ?? d.count` (:152), which mixes units and line counts (F13). Until that is fixed, the title is "Arriving this week" with no unit. Keep the forced horizontal layout. |
| `features/market-listings/MarketSurface.tsx:847`, `:1527` | TrendChart (2 series) | "Date" | "Price (R)" | `zar` | `fmtMoney(v)` defaults to ZAR (promotions-funding/format.ts:19). Legend auto (2 series). |
| `features/plan-vs-executed/PlanVsExecutedView.tsx:778` | TrendChart (2 series) | "Period" | "Rate (%)" | `percent` | `fmtPct` takes ratios (PlanVsExecutedView.tsx:213-216), so `unit='percent'` gives the same numbers. |
| `features/planning/PlanningOverview.tsx:117` | PairedBars | "Customer" | "Units, plan and shipped (units)" | `units` | Drop `compact`; auto layout flips to horizontal for long customer names; ChartControls on. |
| `features/stock/ExecutionLensView.tsx:88` | PairedBars | "Customer" | "Units, plan and shipped (units)" | `units` | Same as above. |
| `features/promotions-funding/CaseBookSurface.tsx:623` | CategoryBars | "Age since claim sale date (days)" or "Age since window end (days)" (follow `hasClaimAge`) | "Outstanding (R)" or "(US$)" | `ccy === 'ZAR' ? 'zar' : ccy === 'USD' ? 'usd' : 'number'` | Other currencies: title "Outstanding (EUR)" etc. with `number` ticks; finding. Buckets are ordered, so sort is fixed and controls are off. |
| `features/reports/ReportBuilderView.tsx:996` | TrendChart | grain label ("Week", "Month", "Quarter") | `headerWithUnit(label, p.unit)` | `p.unit` | Keep `legend={false}` (single series). |
| `features/reports/ReportBuilderView.tsx:1040` | RankedBars | category: the dimension label (Customer / Distributor / Product…), not "Row" | value: `headerWithUnit(label, p.unit)` | `p.unit` | Wire the report's existing sort/cap state into `controls`. |
| `features/stock/CoverLensView.tsx:362` | CategoryBars | "Weeks of cover" | "Distributor × product pairs" | `count` | Ordered buckets: controls off. |
| `features/stock/CoverLensView.tsx:386` | TrendChart (2 series) | "Week" | "Units per week (units)" | `units` | |
| `features/stock/MovementLensView.tsx:96` | TrendChart (1 series) | "Week" | "Sell-out (units)" | `units` | Legend off. |
| `features/stock/MovementLensView.tsx:107` | CategoryBars, horizontal | value: "Units (units)" | category: "Product family" | `units` | Controls on. |
| `features/stock/SellThroughOverview.tsx:365` | TrendChart | grain label | metric=units: "Units sold (units)"; value: "Sales value (R)" (?) | `units` / `zar` (?) | Confirm the sales-value currency. Replace local `fmtCompact` with `unit`. |
| `features/stock/SellThroughOverview.tsx:380` | PairedBars (quarters) | "Quarter" | same as :365 | same | Time axis: no flip, no controls. |
| `features/stock/SellThroughOverview.tsx:401` | RankedBars | value: "Units sold (units)" | category: "Product" | `units` | Label embeds change % (`▲12%`); finding. Keep `labelWidth={260}` only as an upper bound or drop it for the auto width. |
| `features/stock/SellThroughOverview.tsx:423` | RankedBars | value: "Units sold (units)" | category: "Customer" | `units` | Name only (rule holds). |
| `features/supply-inbound/SupplyOverview.tsx:100` | CategoryBars, horizontal | value: "Shipments" | category: "Lifecycle state" | `count` | Ordered states: controls off. |
| `app/(app)/sell-out/ChannelOpsOverviewTab.tsx:87` | TrendChart (2–3 series) | "Period" | "Sell-out (units)" | `units` | The same key `units` is drawn as bar and as line "Trend"; finding. |
| `app/(app)/sell-out/ChannelOpsOverviewTab.tsx:100` | CategoryBars | "Week starting" | "Sell-out (units)" | `units` | `label` is `week_start.slice(5)` (:49), a time axis. Pass `timeAxis`: no flip, no controls. |
| `features/dashboards/WidgetChart.tsx` (all branches) via `WidgetBody.tsx:60` | rewrite onto CategoryBars / RankedBars / ShareChart / TrendChart (`stack`) | category: grain label (Customer, Distributor, Product, Business unit, …; "Period" for time) | metric label + unit via `axisTitle(metricLabel, unit)` | `unit` (already passed) | WidgetBody passes `metricLabel`. Replace `topWithOther` on category bars and pies with ChartControls (`applyTopN`, no Other). Keep `periodByCategory`'s series cap (colour limit); finding. Remove the 11-char cut (145) and pie `noWrap` (110). |
| `features/workbench-ui/HeadlineFigure.tsx`, `features/stock/SellThroughProductPanel.tsx`, `features/stock/SellThroughProblemsTable.tsx` | Sparkline | none | none | n/a | Exempt: no axes by design. Their `label` already carries the unit. |

## 4. Tests

Unit tests, added to `features/workbench-ui/charts.test.tsx` plus a new `chartRows.test.ts`:
- `formatChartValue`: every unit x style from the §2.1 table, including negatives, null, 9 999 / 10 000 / 999 999 / 1 000 000 boundaries, and ratio percent.
- `formatMeasure` usd prefix: update to `US$`. `unitWord('zar') === 'R'`, `unitWord('usd') === 'US$'`.
- `chooseCategoryLayout`: 8 short gives vertical, 9 gives horizontal; a 14-char label gives vertical, 15 gives horizontal; `timeAxis` never flips; `force` wins.
- `wrapLabel`: word break, hard break of one long word, 2-line cap with ellipsis, short text unchanged.
- `horizontalLabelWidth`: floor 64, cap at 45% of 390 and of 1280.
- `applyTopN`: 5/10/15/25/all; n > length; never adds rows; values identical by reference.
- `sortRows`: value desc/asc with nulls last and name tie-break; name case-insensitive with numeric order ("Store 2" < "Store 10"); period keeps input order.
- `topNCaption`: "Top 10 of 37" when truncated; null otherwise.

Render tests (RTL, existing setup):
- Axis titles render as text for each chart.
- `TrendChart` with 1 series has no legend by default; with 2 series it has one.
- `PairedBars` no longer contains "…" for a 40-char customer.
- `CategoryTick` renders `<title>` with the full name.
- `RankedBars` shows "Top 10 of 37".
- `ShareChart` legend shows the full 60-char name and a share computed on the full total.
- `ChartControls` changes the shown count and order.
- WidgetChart no longer emits "Other (n)" for bar and pie.
- **Number-integrity test:** for each chart, the hidden data table's values equal `formatChartValue(input, unit, 'full')` for every input row shown. Formatting changes; numbers do not.

Existing tests to keep green: `charts.test.tsx`, `dashboards/widgetModel.test.ts`, `DashboardWidgetCard.test.tsx`, report tests that assert `$` text (update to `US$`). The tsc gate is no NEW errors.

Render checklist. Run on `/design-lab/charts` first, then on each page in §3, in light and dark, at 1280x800 and 390x844. Mode is switched with the fixture page's toggle (`uiStore.setColorMode`) or the app shell control.
- [ ] Every axis has a title with a unit (or a recorded finding).
- [ ] No category name is cut without hover or tap access to the full name. Two-line wraps do not collide.
- [ ] More than 8 categories, or a label over 14 characters, renders horizontal. Time axes stay vertical.
- [ ] Horizontal label column is at most 45% of the width at 390.
- [ ] Legend present with more than one series, wraps at 390, shows full names.
- [ ] Pie legend shows the full name, value and %, stacks under the pie at 390.
- [ ] ChartControls: top N and sort work; caption is correct; the toolbar wraps at 390 with no page-level horizontal scroll.
- [ ] Ticks: `R 1.2 M`, `US$ 1.2 M`, `86%`, bare units/weeks. Tooltip shows full values with units.
- [ ] Axis text, grid, tooltip and hover cursor are legible in both modes (cursor visible in light).
- [ ] Tooltip wraps long names within 280 px and stays inside the viewport at 390.

## 5. Fixture page plan

- New files:
  - `app/(design-lab)/design-lab/charts/page.tsx` (client component). It imports the **real** components from `@/features/workbench-ui/charts` and `@/features/workbench-ui/ChartControls`, not `design-lab/primitives/charts.tsx`.
  - `design-lab/fixtures/charts.ts`: deterministic fixture data, no randomness, so screenshots stay stable.
- Add a `labNav.ts` entry: "Charts: shared chart grammar fixtures".
- Header: a light/dark toggle (`useUiStore().setColorMode`) and a note of the viewport to check.
- Sections, each in a workbench `Panel` with a title naming what it proves:
  1. **Long customer names, 37 categories.** `RankedBars` and `CategoryBars` (auto, which goes horizontal) with ChartControls. Names are fictional and 6 to 62 characters long (e.g. "Northern Cape Consolidated Retail Holdings (Pty) Ltd — Kimberley Distribution Centre"). Unit `zar`, values from 4 200 to 18 400 000.
  2. **Few short categories.** `CategoryBars` with 6 categories, vertical, unit `count`.
  3. **Vertical wrap case.** 7 categories with labels of 15 to 24 characters and `layout="vertical"` forced, showing the 2-line wrap and ellipsis.
  4. **Three series.** `TrendChart` with 26 weeks, 3 series (bar, line, area), unit `units`, legend auto.
  5. **Paired.** `PairedBars` "Plan vs shipped" over 12 customers with long names (auto horizontal), unit `units`. Plus a quarters version (time axis, vertical, no controls).
  6. **Pie with 9 slices.** `ShareChart` as pie and as donut, long names, unit `usd`, top N demo (5 shown of 9, shares of the full total).
  7. **Each unit kind.** A small `TrendChart` or `RankedBars` per unit: zar, usd, units, percent (ratios 0.42–0.97, `yScale="fit"`), count, weeks (with threshold line), days.
  8. **Single-series time series.** `TrendChart`, 52 weeks, `lastPointLabel`, no legend.
  9. **Empty and one-row edge cases.** One category; all nulls ("—").

## 6. Findings and deferred items

Findings (FACT from source unless marked):
1. F1: `MeasureUnit` has no ZAR kind (charts.tsx:37), so rand values on charts are formatted by caller-local helpers or not at all. The spec adds `'zar'`.
2. F2: three divergent compact formatters (charts.tsx `formatMeasure`; SellThroughOverview.tsx:50; promotions-funding/format.ts:4). The spec consolidates chart use on `formatChartValue`. The other two stay for non-chart text (deferred cleanup).
3. F3: the shared default formatter uses `toLocaleString('en-ZA')` (decimal comma) against the file's own convention (charts.tsx:41-44 vs 286/351/403).
4. F4: the brief's example "R 1,2 M" uses a decimal comma. The existing governed convention is a decimal point with a space for thousands. The spec uses `R 1.2 M`. **Operator to confirm** (DECISION, reversible: one function).
5. F5: `usd` -> `US$` also changes report tiles and table headers ("Support spend (US$)"). It is in scope as text-only. Report tests asserting `$` need updating.
6. F6 (DECISION for operator): dashboards fold the tail into "Other (n)" (`widgetModel.ts:98-104`, 140-171). The spec replaces this with user-set top N and no Other on bars and pies. Pie shares use the full total, so no share is overstated. Options:
   - (a) as spec;
   - (b) keep the Other fold when top N is not All;
   - (c) offer Other as a toggle.
   Reversible. Series charts keep the 7 + Other colour cap (deferred).
7. F7: unit still unconfirmed for SellThrough sales value (currency of the listing-price estimates). The title is "Sales value" with no currency until confirmed. Resolved from source:
   - MarketSurface is ZAR;
   - PlanVsExecuted `fmtPct` takes ratios;
   - ChannelOps:100 is a week axis;
   - Shipping arriving is by distributor (see F13).
8. F13: `ShippingCommercialSummary.tsx:150-152` cuts distributor names to 14 chars before the chart (against "long names never cut short"). It also plots `quantity ?? count`, so a distributor without a quantity is drawn as a line count on a units scale. Fixing the name is in scope. Choosing a single measure is a product/data question: never change a number, only label it truthfully.
8. F8: `ChannelOpsOverviewTab.tsx:92-93` draws the same key `units` as a bar and a line "Trend". With the legend rule this shows two entries for one number. Product question: keep, rename, or drop. Not changed here.
9. F9: `SellThroughOverview.tsx:404` puts the change % inside the product label (`▲12%`), which lengthens labels and mixes a value into a name. Proposal (deferred): a secondary label column.
10. F10: `ReportBuilderView.tsx:1048` uses `labelHeader="Row"`, which is not a meaningful axis title. The spec uses the dimension label.
11. F11: the hover cursor is invisible in light mode (charts.tsx:309, 366).
12. F12: dashboard top N / sort state is component-local, so it resets on reload. Persisting it in the widget definition is a schema/API change (deferred, separate node).

Deferred:
- `design-lab/primitives/charts.tsx` and the lab surfaces that use it (StockSurface etc.) are not production. They are left alone. Retire them later in favour of the real components.
- Consolidating `fmtCompact` helpers outside charts.
- Persisting ChartControls choices per widget or report.
- Non-ZAR/USD currencies on CaseBook (EUR etc.) get `number` ticks with the currency in the title only.
- Rendered verification: this pass is source-only. Rendered review is owed at validate (§4 checklist), recorded as a separate run.
