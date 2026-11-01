# Dashboard polish — report (1 Nov 2026)

Presentation only: no number changes. Code from `8ee34283` ("before") to this branch ("after"); first Part 1 commit `4be3698c`.

## How it was rendered

Real "Polish board" (six v2 widgets: KPI, line, bar, multi-series line, table, customer × product table) seeded on `cip_test` inside one transaction that is rolled back; an isolated loopback API; an ephemeral bearer. Sequential: one Next dev server and one browser at a time, closed between runs. Widths 1920 / 1280 / 390, dark and light, reduced motion on, the series drawn before every shot.

- After: this tree, `:3106`, `metrics-after.json`, `renders/after-*`.
- Before: a `HEAD` (`8ee34283`) worktree, `:3107`, `metrics-before.json`, `renders/before-*`.
- Per run: the page, each widget, each scrolling widget at the end of its scroll (`-end`), the Overview page (`-brief`) and its dashboard zone (`-brief-zone`).
- Harness: `apps/api/tests/test_dashboard_polish_render.py` (opt-in, `CIP_RUN_POLISH_RENDER=1`), `CIP_POLISH_ONLY=after|before`, `apps/web/e2e/dashboard-polish-render.spec.ts`.

## Numbers (all six width × theme runs, each side)

| Measure | Before | After |
|---|---|---|
| Page errors | 0 | 0 |
| Pages with horizontal overflow | 0 | 0 |
| Clipped x or value ticks | **6** (every run, "Units by customer": last value tick) | **0** |
| Colliding ticks | 0 | 0 |
| Line chart fill of its card ("Units by week") | 0.41 | **0.72** |
| Bar chart fill ("Units by customer") | 0.96 (axis below the fold) | 0.96 (axis reachable, scrolls) |
| Multi-series line fill | 0.41 | 0.52 (1920), 0.57 (1280), 0.37 (390) |
| Overview page: widgets loaded | **0 of 6 runs** (skeletons for ever) | **6 of 6** |

Multi-series fill is lower at 390 px because the legend wraps over four lines and the controls take a row; the body scrolls, nothing is clipped.

## Per issue (ISSUES.md)

| # | Before → after | Evidence | Status |
|---|---|---|---|
| 1 | Line chart used 41 % of its card, now 72 %. | `before/after-1920-dark-w1.png`, metrics `fill` | FIX done |
| 2 | Panel and canvas beside each other, titles intact at 1920, 1280, 390 (`after-*-brief.png`). The clip Warren saw at about 1900 px did **not** reproduce on the "before" build: its Overview showed skeletons, so the grid never had real widgets in it. The grid now has `minmax(240px, 312px)` for the panel and `min-width: 0` on children, and every card has a definite height. | `after-1920-dark-brief.png`, `after-1280-light-brief.png` | FIX done (guard in place; original symptom not reproduced) |
| 3 | The number is sized to its box (container-query font, 22 % of box height, 22–64 px). The default size of a *new* KPI is set in the grid layout, which this change does not touch. | `after-1920-dark-w0.png` | FIX done for sizing; default size BLOCKED: I did not find where a new KPI's cell size is chosen; needs a decision on the default size |
| 4 | Bar chart labels wrap ("Yellowwood Computer Warehouse and Home Office Centre"), the full name is the tick's title; the table truncates with an ellipsis and the grid tooltip shows the full name on hover. "AMAZON" → "IAZON" did not reproduce at any tested width on the "before" build, so the E5 regression cause is not established. Keyboard-focus tooltips on table cells are not verified. | `before/after-1920-dark-w2-end.png`, `-w4.png` | FIX done (wrap and hover); regression cause BLOCKED: not reproduced, needs the screen size and data where it showed |
| 5 | KPI "566 k" → "565 985 units" with "All time" and the data date. | `before/after-1920-dark-w0.png` | FIX done |
| 6 | Generated titles name every breakdown, no doubled brackets, "period" only with a period breakdown (`autoWidgetTitle`, `autoTitleV2`; `WidgetEditorDialog.test.tsx:186`). The render board uses explicit titles, so it is unit-tested, not rendered. | unit tests | FIX done (not rendered) |
| 7 | "AMAZON COMMERCIAL SERVICES (SOUTH AFRICA)" → "Amazon Commercial Services (South Africa)" in bars, tables, series legend. | `before/after-1920-dark-w2-end.png`, `-w3.png`, `-w5.png` | FIX done |
| 8 | One precision per axis. Before: "28 k, 21 k, 14 k, 7 000, 0". After: "28.0 k … 0.0 k". A 100 k–1 M axis mixed "0.0 k, 50.0 k" with "100 k, 150 k"; `axisBand` now has a 100 k band: "0 k, 50 k, 100 k, 150 k, 200 k". | `before/after-1920-dark-w1.png`, `after-1920-dark-w2-end.png`, `charts.test.tsx` | FIX done |
| 9 | Column filter buttons are hidden in widget tables (the top-N control and header sort remain) and numbers are right-aligned under their right-aligned header, so no header cell shows an icon on its own. | `before/after-1920-dark-w4.png`, `-w5.png` | FIX done |
| 10 | Value column header was already the measure name on the "before" build ("Sell-out units (units)"). The repeated "(units)" is the deliberate unit-in-header rule pinned by `table.test.ts:31`. | `before-1920-dark-w4.png` | CORRECT AS IS (the header names the measure; the unit suffix is a recorded decision, not changed here) |
| 11 | Subtitle "Polish board · 6 widgets over governed metrics · live query, not lab fixtures" → "Polish board · data as of 2026-11-01". The API returns a full timestamp; it is cut to the date. The date range of each widget is on the widget (12). | `before/after-1280-*-brief.png` | FIX done |
| 12 | Every widget footer shows its range ("All time" or the dates) beside "Data to …". Before: only "Data to …". | `after-1920-dark-w*.png` | FIX done |
| 13 | "Charts per row" label beside the 1 / 2 / 3 control, `aria-labelledby` on the group. | `after-1280-dark-brief.png` | FIX done |
| 14 | Multi-series: default 5 series, a Top 5/10/15/25/All control (new), the series left out are stated ("5 categories shown; 7 not shown. Show more with the buttons above."), no "Other"; colours differ in lightness and hue. | `before/after-1920-dark-w3.png`, `V2WidgetBody.test.tsx` | FIX done |
| 15 | Tables sort by the measure, highest first, with the same top-N control as bars (before: unsorted, no control). | `before/after-1920-dark-w4.png` | FIX done |

## Found while rendering, and fixed

1. **The Overview page never loaded v2 widgets.** `OverviewHub` did not give `DashboardWidgetCard` the v2 catalog, and a v2 card waits for it, so all six widgets were skeletons (no `/query/` request was ever made). Now passed (`semantics-v2-catalog`), with a test.
2. **A fit-to-box loop on that page.** With the widgets loading, each card grew with its chart without end (`dashboard-zone` never settled for 15 minutes). Cause: `useBoxHeight` sizes the plot from the box, and on the Overview the box had no fixed height. Each card now has a height from its saved grid rows (rows of 36 px, gaps of 8, 220–520 px), and the plot is capped at 900 px.
3. Stale `OverviewHub` copy assertion updated; the widget-filter editor test takes about 9 s alone and now has a 60 s limit so it passes under a loaded run.

## Checks on the final tree

- `tsc --noEmit`: clean. `next lint`: 0 errors, the same 50 warnings as before.
- Full web suite (`vitest`, two forks): **219 files, 1 173 tests, all pass** (`full-web-vitest.log`, kept locally: `*.log` is ignored by git).
- `next build` into its own dist dir (so the running `:3000` build is untouched): compiled, 76 static pages.
- Render runs: 0 page errors, 0 horizontal overflow, 0 clipped or colliding ticks, Overview widgets loaded in 6 of 6 runs.

## Not done / limits

- The "before" Overview could not show real widgets (finding 1), so item 2's original symptom stays unreproduced.
- `panelClipped` in the Overview metrics counts any descendant past the viewport edge, including content inside `overflow: hidden` areas, so it is not a clip signal. After: 96 / 119 / 182 for 1920 / 1280 / 390 with no page overflow; before: 0 only because nothing had rendered. Judged from the pictures.
- Same session, not independent. Rendered on `cip_test` fixture data, never on `cip`.
