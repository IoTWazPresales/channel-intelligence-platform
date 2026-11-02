# Batch 3: mutation checks (new web tests run with the fix removed)

Harness: `.eif/audit/REVIEW_20261102/batch3/mutate_web.py` breaks ONE fix, runs the tests written for it, restores the file (and asserts the restore). Last full run on the final code: `mutate_web_run.txt`.

| Fix broken | Tests run | Result |
|---|---|---|
| Sort menu shows "Name A-Z" for a saved Z-A (`ChartControls.sortKey`) | `chartsBatch3.test.tsx` | 5 failed |
| A saved top N of 50 has no pressed button (`topNOptions`) | `chartsBatch3.test.tsx` | 2 failed |
| Legend lists series the top N left out (`TrendChart`) | `chartsBatch3.test.tsx` | 1 failed |
| Comparison ranks by the first category's own series (`rankKey`) | `chartsBatch3.test.tsx` | 2 failed |
| Table widget ignores the saved sort (`RankedTable`) | `chartsBatch3.test.tsx` | 2 failed |
| Dual axis without `categoryAxis` | `chartsBatch3.test.tsx` | 2 failed |
| Editor and chart disagree on the default top N (`defaultTopN`) | `chartsBatch3.test.tsx` | 1 failed |
| Category axis draws the key ("customer:312"), not the name | `chartsBatch3.test.tsx` | 2 failed |
| Tiles follow a vessel click (`tileFilterParams`) | `buildShippingLinesUrl.test.ts`, `ShippingCommercialSummary.test.tsx` | 2 failed |
| A vessel label reserved a fixed 160 px (`labelWidthPx`) | `onTheWater.rules.test.ts` | 1 failed |
| `placeLabels` ignores an anchor's own size | `onTheWater.rules.test.ts` | 1 failed |
| A port name wider than its avoid box (`PORT_NAME_PX_PER_LETTER`) | `OnTheWater.test.tsx` | 1 failed |
| The map caption back on the map | `OnTheWater.test.tsx` | 1 failed |
| A label that fits no corner is dropped (the one-box-higher/lower candidates) | `onTheWater.rules.test.ts` | 1 failed |
| A caller may omit the unit (dual axis) | `chartCallers.test.ts` | 1 failed |

**All 15 mutations were caught** (14 in the last full run, `mutate_web_run.txt`; the placement fallback one right after it). Tests that are controls (they must pass with or without the fix) are not counted as failures; the batch 3 web tests are 32 (17 in `chartsBatch3.test.tsx`, 5 in `chartCallers.test.ts`, 3 in `buildShippingLinesUrl.test.ts`, 1 in `ShippingCommercialSummary.test.tsx`, 2 in `OnTheWater.test.tsx`, 4 in `onTheWater.rules.test.ts`). Not mutation-checked individually: the controls (a Name A-Z sort still reads A-Z, the standard top-N options are unchanged, a table with no saved sort is unchanged, the dual axis keeps both axis titles, the follow-a-real-change and clear-the-vessel cases of the tile query, `sortKey` for every sort, the Name Z-A menu item) and the scan's own sanity tests.

Not mutation-checked: the `LABEL_HEIGHT_PX >= 49` assertion (a constant; the render measured 48.5 px) and the render metrics themselves.
