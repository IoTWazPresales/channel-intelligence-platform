# On the water — step 9 (1 Nov 2026): the data, the page, the tests, the differences

Built from `SPEC.md` and `Main.dc.html`. Same session, not independent. Rendered on `cip_test` fixture data (a rolled-back
tenant shaped like the mock-up: 7 vessels plus one overdue, 5,108 + 404 waiting, 851 booked, 9 lines that need a look); never
rendered on `cip` data. The renders are in `renders/` (`<width>-<theme>-1-tiles|2-map|3-vessel-panel|4-cards|5-hover|6-selected-grid|7-by-distributor.png`,
`metrics.json`).

## What was built

| Area | Where |
|---|---|
| Slip fields (BACKLOG-218) | `shipment_change_events.py`: `port_eta_date` and `on_board_date` in `_DATE_SLIP_FIELDS`. A blank that becomes a date is not a slip; only a date moving to another date is |
| Rules and maths (pure) | `apps/api/app/services/shipping/on_the_water.py`: at sea / arrived / booked / overdue, sea only, vessel key (name + voyage, else on-board + ETA + port + lane), position along the lane, slip from the report history, value per currency, needs a look |
| API | `GET /api/v1/shipping/on-the-water` (same filters as `/commercial-summary` and `/lines`), `GET` and `POST /api/v1/shipping/port-conditions` (admin, append-only, audited) in `shipping_water.py` |
| Grid filters | `vessel` (the vessel's lines only) and `cohort=needs_look` on `/lines`, `/commercial-summary`, `/eta-shifts`; `on_board_date`, `port_eta_date`, `port_ata_date` as date fields; the voyage fields in the line payload |
| Attention (BACKLOG-219) | `brief_signals.py`: row `shipment_needs_look`, opens `/supply/shipments?cohort=needs_look` |
| Tenant config | `commercial_tenant_profile`: key `on_the_water` (`hub_lane`, `stale_report_days`, `needs_look_days`) |
| UI | `apps/web/src/features/supply-inbound/onTheWater/` (`OnTheWater.tsx`, `layout.ts`, `format.ts`, `basemapDots.ts`), in the chart's slot in `ShippingCommercialSummary.tsx`; Map / By distributor toggle; click a vessel or a list row to filter the grid (`InboundShipmentsWorkspace.tsx`) |
| Administration | `/admin/port-conditions` (admin only, in the Administration menu): enter a figure, see the history |

## Tests (SPEC acceptance 2 and 3)

- API on `cip_test`: `test_on_the_water.py` (18 pure: vessel grouping, position fraction, slip, the four totals, sea only, currency rule, needs a look, overrides) and `test_on_the_water_db.py` (5, through HTTP on a rolled-back tenant: totals and currencies, grouping and slip from observations, needs a look and grid filter by vessel, port condition current row and who may enter one, the Attention row); `test_shipment_change_events.py` (+3 for the slip rule).
- Web: `onTheWater.rules.test.ts` (7: dates, money rule, slip text, clusters, labels never overlap, the page scope into the map), `OnTheWater.test.tsx` (11: tiles, stale note, scope, toggle, hover and keyboard-focus card, click-to-filter, selected panel, ports, needs a look link, bad payload), `HeadlineFigure.test.tsx` (+1).
- The 11 stale API tests: fixed (5 open-book: own tenant per test; 3 apply: patch `write_shipment_facts_and_close_book`; 2 grain tests: day grain; 1 sell-through filter: assert what the test controls).

## Renders against the mock-up (SPEC acceptance 4)

Measured in every run (6: 1920, 1280, 390 × dark, light): 0 page errors, 0 horizontal overflow, 0 label overlaps, 0 labels outside the map, every marker 44 px, the Durban pulse is `animation: none` under reduced motion, hover card and keyboard-focus card both show, a click on a vessel filtered the grid to exactly its 21 lines and the map kept all 5 markers, "Open the 9 lines" returned 9.

### Difference list

| # | Mock-up | Product | Class |
|---|---|---|---|
| 1 | Toggle "Map / Table" | "Map / By distributor" (SPEC D1: the bar chart stays as the second view) | CORRECT (SPEC wins over the mock-up) |
| 2 | A page with its own eyebrow and 28 px title | A section titled "On the water" inside the Shipments tab, in the chart's slot (D1) | CORRECT |
| 3 | Raw hex colours and the Inter / JetBrains import | CIP tokens (`tokensFor`) and the app's font (D2); light mode works | CORRECT |
| 4 | Basemap is an image | Inline SVG: land dots and lanes from path data, coloured by tokens | CORRECT (SPEC) |
| 5 | Labels at hand-set offsets | Computed: the selected vessel first, then up to 4; never over each other, a port name, a marker or the Durban note. At 390 px only the selected vessel is labelled | CORRECT (SPEC "never overlapping") |
| 6 | Durban pulses always, chip "anchorage wait [port feed] · Planned" | Pulses only while a vessel's arrival is overdue; chip "Durban · No figure entered · Planned", or the figure someone entered, with who and when | CORRECT (SPEC: manual port condition, D4) |
| 7 | Panel heading always "Selected vessel · inferred" | "Next to arrive · inferred" until a vessel is clicked, then "Selected vessel" | CORRECT (nothing is selected until it is) |
| 8 | No overdue state | Overdue arrival: amber "Arrival overdue" chip, drawn at the discharge port | CORRECT (SPEC) |
| 9 | Port conditions rows are fixed text | One row per port with cargo or a figure: units waiting, the figure or "No figure entered · Planned", link "Enter a figure" to the admin page | CORRECT (SPEC) |
| 10 | Side panel beside the map at 1440 px | Beside the map from about 1000 px of content (1280 screen); stacked under it on narrower | MIGRATE → closed (bases set to 600 / 340 px after the first render wrapped at 1280) |
| 11 | Chip covered the Durban port name and, later, the Durban note | Labels avoid port names, markers and the Durban note | MIGRATE → closed |
| 12 | "Arrival overdue" in green in the first build | Amber | MIGRATE → closed |
| 13 | On a phone-width map the footnote and Durban note sit on the map | Under the map | MIGRATE → closed |
| 14 | Port names near the right edge clipped | The name sits left of its dot beyond 82 % of the width | MIGRATE → closed |
| 15 | At 390 px SHANGHAI and CHONGQING names touch on a 336 px map | Not changed | BLOCKED: which ports to name at phone width is a design choice (a short list, or leader lines); needs a decision |
| 16 | Mock-up data (ACZA 27 Oct) | `cip_test` fixture shaped like it; real `cip` data not rendered | BLOCKED: render on `cip` after the web restart, with Warren looking |

### Found and fixed on the way

- **A regression of mine in Part 1:** `HeadlineFigure` was made a size container for every caller, so any strip of figures in an auto-height parent collapsed and its text overflowed (the Shipments KPI strip, seen in the first render). It is now opt-in (`fitBox`), used only by the dashboard KPI. The deployed web build from step 5 had the bug; the rebuild at the end of this step removes it.
- Report dates are counted from observations as well as lines, so a report known only from history still counts.

## Final checks on this tree

- Full API on `cip_test` (run from `apps/api`): **3,533 passed, 24 skipped, 0 failed** (`api_full_pytest_step9.log`).
- Full web: **221 files, 1,192 tests, all pass** (`web_full_vitest.log`); `tsc` clean; `next lint` 0 errors, the same 50 warnings.
- Web rebuilt into `.next` (BUILD_ID `xnDMql7u1ioTHtpZZZ-3s`, `/supply/shipments` and `/admin/port-conditions` built); web, worker and API restarted through the supervisor; `/health/ready` reports `cip`, web routes 200, Celery ping pong (`step9_services.txt`).

## The endpoint on the real cip data (read-only, `cip_water_check.txt`)

As of 1 Nov: report of 27 Oct (5 days old, not stale), 12 reports in history since 21 Jul. At sea 13,516 units in 162 lines on 14 vessels, US$8.26M, +738 units by air; arrived and waiting 3,417 units (City Deep 3,013, Port Louis 404); needs a look 6 lines, 336 units, on-board date moved 11 Oct → 18 Oct (the spec's example); the vessel filter returned exactly the vessel's 24 lines, the needs-a-look filter its 6, and Attention shows "6 shipped-sheet lines still open".

**For Warren:** 9 of the 14 vessels are flagged overdue, some by two or three months (for example ETA 14 Aug with 1,875 units and no arrival date). That looks like missing arrival records on old lines, not ships still at sea, and it inflates "At sea" and piles those vessels on Durban. The SPEC defines overdue as "port ETA before as-of" with no age limit; the existing KPI contract treats a promise older than 180 days as stale. I did not add a cut-off. Decision needed: an age past which an at-sea line with no arrival date is shown as "stale, check the report" and left out of At sea.

## Left open (not the SPEC's decisions to re-make)

- Slip uses the first ETA a report carried, not the smallest one; they are the same unless an ETA moved earlier.
- Positions for a discharge port the lane table does not know (not Durban, City Deep, Port Louis, Cape Town) are drawn at Durban and the route is labelled assumed.
- Live vessel tracking, port congestion feed: Planned (D4, D6).
