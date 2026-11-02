# Batch 3 report: the N-0114 chart items from the GOV-008 review of 2 November 2026

Branch `feat/ns-2-brief-nav-collapse`, one agent session (Sonnet 5.5). Same-session self-verification only: the writer also wrote the tests and looked at the renders. **No acceptance is claimed.** No node, no ledger event.

**Boundaries kept.** Nothing was written to `cip`, no migration applied to it, no restart, no deploy. Every database run was on `cip_test` (the full API suite and the On the water render harness, which seeds `cip_test` inside one rolled-back transaction). I did not open a connection to `cip`.

## Gate

| Gate | Result |
|---|---|
| Full API pytest on `cip_test` (`apps/api/.venv`), run alone | **3,645 passed, 25 skipped, 0 failed**, 26 min 12 s (`batch3/api_full_pytest_cip_test.log`). No API code changed in batch 3; the same figure as batch 2 |
| Web `tsc --noEmit` | exit 0 (`batch3/web_tsc.log`) |
| Web vitest, full | **225 files, 1,247 tests passed** (`batch3/web_vitest.log`). Batch 2: 223 / 1,215, so +2 files and +32 tests |
| Web lint (`ESLINT_USE_FLAT_CONFIG=false`) | exit 0, **0 errors, 50 warnings** (the same 50) |

**An invalid API run, kept for the record.** My first batch 3 API run (`api_full_pytest_run1_INVALID_postgres_in_recovery.log`: 28 failed, 3,583 passed, 48 skipped, 11 errors) was started while I also ran the On the water render harness against `cip_test`. The harness hit `deadlock detected`, and later in the suite connections failed with "the database system is in recovery mode" and "server terminated abnormally"; every failure I looked at is a connection error in the shipment tests. The timing fits, but I did not establish what crashed Postgres. I did not use that run. The run above was started alone afterwards. Lesson: run the full suite alone and keep the render harness away from `cip_test` while it runs. (I tried to save this as a memory note; the guard refused the write because the memory folder is outside the declared project roots, so it is only here.)

## Final commits and what the renders ran against

Code: `558c2d73`, `36dfc256`, `8c547457`, `36e4d65c` (final code). The renders below ran on `36e4d65c` (checked with `git rev-parse HEAD` immediately before), with the working tree otherwise clean of source changes; an evidence commit follows (specs for the renders were already committed, this report and the PNGs are not source).

## Result per item

"Proof" = the new test fails with the fix removed (`batch3/mutation_checks.md`: 15 mutations, all caught).

| Item | What changed | Test | Proof |
|---|---|---|---|
| Comparison chart legend (10 bars, 24 entries) | Over categories with one measure the legend is **two entries** (current, previous), not a pair per category; current bars share one colour so the muted dashed previous bars read against them. `TrendChart` also stops listing a series whose figures are all in rows the top N left out | `chartsBatch3.test.tsx` | caught (comparison, legend) |
| Comparison chart default order | It ranks rows by each row's own current figure (`rankKey`); it ranked by the first category's series, which is empty on every other row, so the order stayed as listed | same | caught |
| Dual axis: shared long-name tick, sort control | Over categories it passes `categoryAxis` and the saved presentation: wrapped tick, Sort, top N (default 10), data table of the plotted rows; the saved name sort and top N reach it. It also passes a unit | same | caught (2 mutations) |
| **Found while rendering:** category axis drew the key | A `TrendChart` category axis drew `customer:312`, not the customer's name (the tick ignored `xTickFormat`). This affected the comparison chart over categories already; fixed for both | same | caught |
| Table widget ignores a saved name sort | The table starts from the saved sort (name A-Z or Z-A, or lowest first by the saved measure) and top N; the first-run probe showed "Highest first" over server order | same | caught |
| Sort menu label for a saved Z-A | `Name Z-A` is a menu item and the label follows the saved sort | same | caught |
| Editor top N 15 vs renderer 10 | One default for both (`defaultTopN`: ranked bars 15, columns 10); the editor control is `TopNSelect` | same | caught |
| Saved `top_n` 50 shows nothing pressed | The top-N buttons add the saved value (50) and it is the pressed one | same | caught |
| Tiles refetch on a vessel click | While a vessel is selected the tiles and ETA shifts keep the query they had unless something else changed (distributor, customer, product, plan...); with none selected they follow everything as before | `buildShippingLinesUrl.test.ts` (3), `ShippingCommercialSummary.test.tsx` (the component asks no new request) | caught (2 tests) |
| Durban pill over the map caption | The caption sits **under** the map, in the flow; the note stays on the map | `OnTheWater.test.tsx` + render | caught; render metric 1 -> 0 |
| Cluster box over City Deep | A vessel label is reserved the width and height it draws (`labelWidthPx`, `LABEL_HEIGHT_PX` 52; the label was reserved 160 x 42 and draws about 201 x 48.5) and the port-name box is as wide as the name draws (8.4 px a letter). A label with no free corner is tried one box higher or lower before it is dropped | `onTheWater.rules.test.ts` (4), `OnTheWater.test.tsx` | caught (4 mutations); render metric 1 -> 0 |
| Widget CSV headers and units | Done in batch 2 (M9: exact text; a percent column exports the number its header says). Nothing more needed in batch 3 | `table.test.ts` | see batch 2 |

## Caller inventory

`batch3/CHART_CALLERS.md` (generated by `make_inventory.py`): **53 callers** of the shared charts in product code, with axis titles, unit, legend, long-name tick and sort / top N for each. **0 callers lack a title or a unit.** Findings: every product `TrendChart` except the comparison chart and the dual axis is a time axis (period, week, date), which needs neither the category tick nor sort; `CategoryBars`, `RankedBars` and `PairedBars` use the shared tick and controls; three callers switch the controls off for ordered buckets and say so in a comment (case-book age buckets, cover buckets, shipment lifecycle states). The dual axis was the one product caller that bypassed the shared parts, and the one without a unit prop. `workbench-ui/chartCallers.test.ts` scans the JSX so a new caller that omits a title or a unit fails.

Not in the inventory: the 13 design-lab surfaces (`src/design-lab/surfaces/`) call the design lab's **own** chart primitives (`design-lab/primitives/charts`), not the shared components; they have fixture data and live on `/design-lab/*`. Not changed.

## Renders

Playwright, Chromium, light and dark at 1280x800 and 390x844, reduced motion, run on `36e4d65c`. PNGs and `metrics.json` in `.eif/audit/REVIEW_20261102/batch3/renders/`: `builder/` (the fixture dashboard route `/design-lab/builder`: 28 widget cards per theme and width including the comparison, dual-axis and table widgets, plus the new route `/design-lab/builder-batch3`: the five cases with twelve long-named customers) and `otw/` (the real Shipments page, the On the water map and the vessel panel). `otw-before/` is the same harness on the code before the layout fix.

| Render | Widths / themes | Horizontal overflow of the page | Text overlaps | Text past its card |
|---|---|---|---|---|
| Batch 3 cases (5 cards) | 1280 and 390, light and dark | 0 of 4 | **0** | 0 |
| Fixture dashboard widgets (28 cards) | same | 0 of 4 | 4 per run (see below) | 0 |
| On the water, Shipments page | same | 0 of 4 | labels over each other 0; label over a port name **0** (before: 1 at 1280); Durban note over the caption **0** (before: yes at 1280); note over a label 0 | labels outside the map 0 |

- "Text overlaps" = pairs of SVG text, axis titles, legend entries and control captions whose boxes overlap by more than 1.5 px, within one card. Two **angled** ticks are counted apart (their bounding boxes overlap by geometry; 17 per run at 1280 and 30 at 390 on the dual-axis card): that is not text on text.
- The 4 fixture overlaps are not from this batch: in four widgets (a line, an area, a scatter and one starter widget) the first x label or the origin tick shares a corner with the "0" of the y axis. Not fixed.
- The same console error ("Failed to load resource: 404") appears 3 times per On the water run before and after.

**What these renders cannot show.** The data is fixture data: recorded-shape answers with fictional names and numbers for the builder pages; the On the water page runs on the harness's own seed in `cip_test` (a rolled-back "fixture tenant"), **not on `cip`** and not on real vessels, ports or customers. They show layout, overflow and overlap at two widths in headless Chromium with reduced motion: not real devices, not a screen reader, not a person looking at it. The overlap numbers are box measurements, not a judgement of legibility. No hover or keyboard state of the new charts was captured (the On the water hover was). I looked at a handful of the PNGs myself while fixing; that is not an independent visual review.

**What the renders showed that I did not fix.**
- **Dual axis at 390 px**: ten long names are drawn as angled one-line ticks cut to the same first words ("Kestrel Home and..."); a dual axis cannot use horizontal bars (it has a right-hand axis). The full name is in each tick's title and in the chart's data table. Not fixed.
- **On the water at 1280**: with its real size the 4-vessel cluster at Durban finds no free place on this short fixture map, so its label ("4 vessels at or near Durban") is not drawn (2 labels instead of 3); the "4" marker, the hover card and the "Arriving next" list still carry it. Before, the label was drawn and covered "CITY DEEP". This is the existing rule ("one that fits nowhere gets no label") applied to an honest box.

## Needs Warren

1. **Dual axis now starts at the top 10 categories** (it plotted every category before), with "Show all" and the Sort menu. Keep, or start with all?
2. **Comparison over categories: two-entry legend and one colour for current bars** (was one colour and one legend pair per category). The x axis names the categories. Keep?
3. **Tiles keep their query while a vessel is selected.** The alternative is to follow the filters the click clears (then they change on every click).
4. **Editor default**: columns 10, ranked bars 15 (the renderer's own). The other way round is one number.
5. **The 4-vessel Durban label** is not drawn at 1280 on the fixture map (above). Do you want it drawn over a port name instead, or a smaller label for a cluster?
6. Batch 2's list stands (mapping memory and alias tenancy, D-0132 status, apply `20261102_0051`, deploy and worker restart, AUD-PARI cleanup go, partial-shipment remainder, orphan with another quantity, M3 reading, M2 and `cst_alias_era_derive`).

## Not done

- Dual axis at 390 px; the 4 corner overlaps in fixture widgets; the 4-vessel label at 1280 (above).
- No render on `cip` data, no render by a person, no real-device check.
- `LABEL_HEIGHT_PX >= 49` and the render metrics are not mutation-checked.
- The `/design-lab/builder-batch3` page, its fixtures and two Playwright specs/configs are new tooling in the repo (`builderBatch3.ts`, `builder-batch3-render.spec.ts`, `playwright.builder-batch3.config.ts`); `on-the-water-render.spec.ts` now takes `CIP_RENDER_OUT` and `CIP_RENDER_SIZES`.
- Design-lab surfaces (own primitives) were not changed.

## Files

Code: `charts.tsx` (rank key, legend keys, plotted-series legend, category tick names), `ChartControls.tsx` (Name Z-A, pressed saved top N), `ComparisonChart.tsx`, `V2WidgetBody.tsx`, `TopNSelect.tsx` (new), `BuilderEditorDialog.tsx`, `buildShippingLinesUrl.ts`, `ShippingCommercialSummary.tsx`, `OnTheWater.tsx`, `layout.ts`.
Tests: `chartsBatch3.test.tsx` (17), `chartCallers.test.ts` (5), `buildShippingLinesUrl.test.ts` (+3), `ShippingCommercialSummary.test.tsx` (+1), `OnTheWater.test.tsx` (+2), `onTheWater.rules.test.ts` (+4): 32.
Evidence: `.eif/audit/REVIEW_20261102/batch3/` (this report's tables, `CHART_CALLERS.md`, mutation checks and harness, renders, logs).
