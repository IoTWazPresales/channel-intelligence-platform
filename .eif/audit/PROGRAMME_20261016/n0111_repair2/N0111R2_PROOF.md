# N-0111 repair 2: proof

Node N-0111 (stays N-0111). Branch `feat/ns-2-brief-nav-collapse`. Run `RUN-20261016-N0111-REPAIR2`; verification is a different run (`RUN-20261016-N0111-VER3`). Same session, same model: self-verification, not independent. N-0099 does the second look.

## Warren's decisions recorded (programme)
- **D-0112** the stock chain BRIDGES missing on-hand weeks (corrects D-0105's "restart").
- **D-0113** repeated Pinnacle lines inside one file follow D-0091.
- **D-0114** Compuspeed (1152) / Syntech (4145) un-merge PARKED; no partial un-merge.

## 1. Stock chain bridge (D-0112) - `0aeffcbc`
Rule (`customer_stock_gap.compute_positions`): for the whole Monday-Sunday weeks between two reported on-hand figures of one product:
- every such week has sales reported -> the later report is `compared`: expected = last reported on-hand + matched deliveries (POD in the window) - all sales in between. Each such week is stored `no_on_hand` (its units kept, never compared itself).
- any such week has no sales either -> the later report is stored `chain_restart` (screen label **Unreported weeks**, a data gap), nothing compared. A week with neither on-hand nor sales stores no row of its own (it was a filler row before).
- "sales reported" = a period overlapping the week whose stored row carries a units figure (a stock-only row stores units 0 and does not count: `figure_import_jobs` has no `units_sold`; rows from before N-0111 count).
- Stored value stays `chain_restart` (a CHECK constraint names it; no migration). Screens and text call it Unreported weeks.
- My reading, not stated by Warren: sales missing for ANY in-between week -> unreported weeks (the sum of sales would be incomplete). Say if a partly-covered gap should be handled differently.

Tests (pure, `test_customer_stock_gap.py`): bridge across one sales-only week (30 - 4 - 6 = 20, gap 0); two missing weeks with a delivery inside them and a real -5 gap; three weeks with neither -> `chain_restart`, no filler rows; one uncovered week among covered ones -> `chain_restart`; a month-grain sales row covers the weeks it spans; a row with no units figure does not cover its week. DB (`test_customer_stock_gap_cause_db.py`, cip_test): bridged chain through `list_stock_positions`; a stock-only row leaves its week unreported; the old restart test now shows no filler rows and the Unreported weeks reason.

## 2. Pinnacle repeated lines (D-0113) - `045fd68a`
In one load, lines with the same distributor, customer, product, date and invoice (sell-out and returns): lines that differ in any source column are summed into the one stored row (units, revenue, reported/computed revenue; unit price and currency: the later line's); a line identical in every source column counts once and is marked `duplicate`. The first line writes the row; later lines point at it. Across loads D-0110 is unchanged (a reload of the same invoice line replaces the figures and keeps the old ones). The `repeated_line` load-report reason is gone: repeated lines are loaded (identical copies counted once). Job summary carries `summed_lines` and `duplicate_lines`.

Tests (`test_dsi_line_supersede_db.py`, `test_import_load_report.py`, cip_test): differing lines 1 + 4 = 5 units, revenue 10 + 40 = 50, nothing kept as superseded, re-apply unchanged, both lines point at one fact row; identical pair counted once and flagged `duplicate`, a third line differing in a source column summed (3 + 3 = 6), re-apply unchanged; a reload of a summed line keeps the replaced total (5 -> 9 recorded); return lines -2 and -3 summed to 5; load report: 8 lines read, 5 loaded (1 identical copy), 3 not loaded.

## 3. Read-only count and backlog (D-0114)
`probe_unmerge_raw_cip.txt` (current_database() = cip, read-only). OPEN_CHANNEL rows whose raw source row / raw customer text names Compuspeed or Syntech (text hits, not proof of owner): `fact_inbound_shipment` 214 of 5,499 (Compuspeed 163, Syntech 51); `shipment_evidence_line` 1,414 of 31,975 (1,057 / 357); `shipment_evidence_observation` 576 of 16,093 (429 / 147); `shipment_evidence_current` 198 of 5,662 (152 / 46); `commercial_lineup_line` 52 of 92 (35 / 17). Written to `docs/BACKLOG.md` BACKLOG-212 with the trace file and the trigger "before distributor-level reporting is shown to users". No un-merge made, no cip write.

## 4. cip recompute (derived table `customer_stock_position`, once)
`recompute_stock_gap_output.txt`; `current_database()=cip` printed first; the script refuses unless the database name is passed.

| status | before (previous rule) | after (bridge rule) |
|---|---|---|
| compared | 16 | 16 |
| flagged (compared, gap >= 1 unit) | 16 | 16 |
| no on-hand reported (`no_on_hand`) | 3,457 | 36 |
| unreported weeks (`chain_restart`) | 298 | 298 |
| first report | 387 | 387 |
| positions | 4,158 | 737 |

Why nothing new is compared: `probe_restarts_cip.txt` (read-only). Of the 298 report points after a gap, 289 have no sales row of any kind between the two on-hand reports (Computer Mania 2025-07-20 -> 2025-09-29, 71 days; median gap 85 days for Computer Mania, 85 for Evetech); 9 have some sales rows between the reports but not for every week (the only gaps with any sales rows; the 36 `no_on_hand` rows are Makro 34, Takealot 2). No gap in the real data has sales for every missing week, so the bridge finds nothing to bridge on cip today. The drop 3,457 -> 36 is the removal of filler rows for weeks with neither on-hand nor sales; those weeks are now the 298 unreported-weeks report points. All 16 compared rows are Game, first cause no prior on-hand (unchanged).

## 5. Tests and services
- Full API pytest on cip_test: 3041 passed, 21 skipped, 0 failed (`pytest_full.txt`).
- Full web vitest (2 workers): 187 files, 872 passed, 0 failed (`vitest_full.txt`).
- Web rebuilt (`web_build.txt`, BUILD_ID `IJmu4NDqQX50Pq1SZ7SkS`); web and API restarted through `scripts/cip-supervisor-stop.ps1 -Component web|api -Restart`; local `/health` 200, `/login` 200, `/auth/me` 401 (tunnel still blocked by the network on port 7844).
- Not rendered: the admin screens need sign-in.

## Limits
- Same session, same model; not independent. N-0099 does the second look.
- Stored status value is still `chain_restart` (label Unreported weeks); no migration.
- Partly covered gaps are treated as unreported weeks (my reading, above).
- Summed repeated lines keep the later line's unit price; no price is recomputed from the totals.
- A repeated line whose source columns all match counts once even if the file meant two sales; that is D-0091 as Warren set it.
- Pinnacle proof is on cip_test through the real apply function (staging lines built directly), not through the file parser.
- Wide week-column files and month labels still do not roll the year (earlier limit, unchanged).
