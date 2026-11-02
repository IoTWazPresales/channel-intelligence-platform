# On the water: fixes from Warren's review of the live page (2 Nov 2026)

Same session, not independent. Read-only on `cip` throughout; the one `cip` write (item 2) is dry-run only and waits for "run against cip".

## 1. A click refreshes the grid, not the map

Cause: the map's query URL carried the grid's filters (line state, status, date field and range, search, POD, lifecycle, slip, a card cohort, a
clicked vessel). A vessel click resets several of them to neutral, so on a page with any filter set the map query changed and refetched.
The KPI tiles and ETA shifts also carried the clicked vessel.

Fix:
- `buildOnTheWaterUrl` keeps only who the page is about: distributor, customer, purchase order, product family and model, currency, operating unit, plan quarter and business unit, lineup attribution.
- `buildShippingCommercialSummaryUrl` and `buildShippingEtaShiftsUrl` leave out a clicked vessel and the needs-a-look cohort.
- `useSelectionInUrl` writes `?vessel=` and `?cohort=needs_look` with `history.replaceState` only (no router push, no reload, no page request); the workspace reads `?vessel=` on load, so a reload or a shared link lands on the same selection.
- Tests: the map query is requested once and not again for a vessel, the needs-a-look cohort, line state and status, a date range and POD filter, or a search (`OnTheWater.test.tsx`, "does not ask for the map again"); it is requested again when the distributor changes. The URL builders and the hook (`replaceState` called, `pushState` never, nothing on first render, nothing for an unchanged selection) are tested.

## 2. Needs a look against the 27 Oct workbook (read-only, `diag_needs_look.py`)

Workbook, Shipped sheet, no ship confirm date: **12 lines / 1,316 units** (Pepkor 523, DCC 290, Mustek 482, Rectron 21). The rule selects the right kind of line:
a Shipped-sheet line still open with no ship confirm date and an ex-works date older than 7 days. Three of the twelve have ex-works 26 Oct (Mustek 125 and 300, DCC 160: 585 units), exactly 7 days old on 2 Nov, so they are not yet "older than 7 days".
Nine lines / 731 units qualify today: Pepkor 523, DCC 130, Mustek 57, Rectron 21.

The card shows **15 lines / 1,067 units** (Pepkor 651, DCC 260, Mustek 114, Rectron 42): the 9 correct lines plus 6 copies (336 units).

Cause: the re-process of job 1697 was read under the new source keys. The old open facts of the Shipped sheet (fact key made from the old source key) lost their evidence line when it was purged (`ON DELETE SET NULL`) and stayed.
The re-process did run the open-book close (`closed 0`), but that close only takes facts of an earlier job: these are the same job, so it skipped them. There are **9** such facts (921 units, facts 148768, 148777, 148780, 148785, 148786, 148801, 157127, 163464, 163465), every one with a replacement fact of the same order line in the same job.
The grid rows "looked like Unship open orders" because they are open orders of the Shipped sheet: the same orders were on the Unship sheet before they got a delivery number, where they are `closed_disappeared`.

Fix of the cause (code): `retire_orphaned_open_rows` runs at the end of every fact write for a job: an open fact of that job with no evidence line becomes `closed_superseded` (pointing at the fact that carries the same order line) or `closed_disappeared` when nothing does. Test on `cip_test` (before: the rule counts the re-keyed line twice; after: once).

Fix of the data (cip write, **not run**): `merge_shipped_fact_identity_twins.py --retire-orphan-open-rows --job 1697` dry run on cip: **9 orphaned open rows, 921 units, 9 with a replacement**. `--apply --expect-db cip` retires them.

| Card | Workbook (7-day rule) | Now on cip | After the write |
|---|---|---|---|
| Lines / units | 9 / 731 | 15 / 1,067 | 9 / 731 |
| Pepkor | 523 | 651 | 523 |
| DCC | 130 | 260 | 130 |
| Mustek | 57 | 114 | 57 |
| Rectron | 21 | 42 | 21 |

After the write the card matches the workbook; the 3 lines of 26 Oct (585 units) join it on 3 Nov when they pass 7 days.
The same 15 lines also sit in the "Arriving this week" tile (open orders by promise date), so that tile drops by the 6 copies too.

## 3. "Arriving this week" against the vessels due this week (read-only, `diag_arriving.py`, `diag_arriving2.py`)

Tile (unfiltered, week 2 to 8 Nov): **7,565 units / 57 lines**. Vessels due this week by ETA at port: COSCO 5 Nov **4,286** units (32 lines) and COSCO 7 Nov 2,913 (13 lines): **7,199 units / 45 lines**.
The two sets do not overlap at all. The tile counts by the derived estimated delivery date (`eta_date`), the map by ETA at port:
- 36 shipped sea lines (5,328 units) on vessels already past their port ETA whose delivery estimate falls this week;
- 21 open-order air and truck/air lines (2,237 units) with no port ETA (15 of them are the needs-a-look lines);
- none of the 45 lines on the vessels due this week: their estimated delivery falls after the week.

Done: the tile reads "Arriving this week · est. delivery" with the caption "by estimated delivery date ... the map shows ETA at port", the by-distributor chart and the smart-preset chip say "(est. delivery)", and the map, hover card, selected panel, cluster chip and vessel aria labels say "ETA at port".

## 4. Vessel badge

"N days overdue · ETA moved +M days" (two facts), "ETA moved +M days" when not overdue, "ETA unchanged", "N days overdue" when the ETA did not move (`badgeText`, tested); the map label for an overdue vessel reads "N days overdue · moved +Md".

## 5. Side panel

Minimum width 360 px (`flex: 1 1 360px; min-width: min(360px, 100%)`, so a 390 px phone does not overflow). At 1280 the map and the panel sit side by side (map 582 px, panel 360 px).

## Also

Shanghai's name now sits above its dot (`PORT_LABEL_SIDE`), so it no longer runs over Chongqing's (left of its dot, as asked); Shenzhen unchanged. Seen in the 1280 and 390 renders (0 label overlaps, 0 outside, 0 horizontal overflow).
