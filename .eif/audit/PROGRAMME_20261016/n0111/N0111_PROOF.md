# N-0111 proof: history upload readiness (Amazon, Takealot, Pinnacle)

Run: RUN-20261016-N0111-IMPL (build), RUN-20261016-N0111-VER (self-verification, same session, same model).
Commits: `d61e5af0` (API, migration, tests), `d7807c8b` (web).

## What was built (customer sell-through: Amazon 299, Takealot 20)
1. Monday-Sunday is the tenant default week calendar (`week_calendar` in the tenant profile, default
   `monday_sunday` -> ISO weeks). A customer's own feed-profile `week_calendar` (iso, fiscal, none) still wins.
2. A line with a full sale date stays a day; day rows roll up into Monday-Sunday weeks (volume series
   uses `date_trunc('week')`; the read model counts each Monday-Sunday week of day rows once; the stock
   chain treats day rows inside contiguous weeks as one chain).
3. Week or month numbers without a year: the parser logs every year it would have had to fill in; the
   file is held (`cst_year_required`, with the year the file name or folder suggests) and apply refuses
   the job until `cst_confirmed_year` is set (upload form, or `POST /api/v1/imports/jobs/{id}/cst-confirm-year`).
4. Per-figure supersession: units sold, on-hand, in-transit and on-order are replaced only when the newer
   load carries them, under the same key (upsert) and across keys (other site, grain or file). Replaced
   figures are kept in `fact_customer_sellthrough_superseded` with the superseding load and `figures`;
   a row that gives up some figures keeps the rest. Nothing is hard-deleted. Stock-only files load when
   marked Stock only.
5. A Monday-Sunday week with no reported on-hand is stored as a `no_on_hand` position and the chain
   restarts at the next on-hand (`chain_restart`, nothing compared). The gap tab Flag reads
   "No on-hand reported" / "Chain restarts".

Migration `20261016_0041`: clone proof on `cip_n0111` (upgrade, downgrade, upgrade: every count equal;
downgrade with N-0111 positions present also clean), then cip as the migration role: fact rows 3197,
units 12394, on-hand 30832, superseded 390, positions 701, staging 46718 unchanged. Details:
`N0111_CLONE_PROOF.md`, `N0111_CIP_APPLY.md`.

## Synthetic 2-year set on the clone (2023-01-02 to 2025-01-12, products 2, 3, 4)
Per customer: two day-dated history files (one gap week with no file), a week-number-only file (`W31.csv`),
sales-only then stock-only for week 2024-12-30, stock-only then sales-only for 2025-01-06, an identical
re-upload of the 2024 file, an overlapping day-dated correction of weeks 61-62; then the whole set again.

| Source | before | after round 1 | after re-running the whole set |
|---|---|---|---|
| Amazon 299 (synthetic products) | units 0, latest on-hand 0 | units 2245, latest on-hand 1095, rows 2151 | units 2245, latest on-hand 1095, rows 2151 |
| Takealot 20 (synthetic products) | units 0, latest on-hand 0 | units 2245, latest on-hand 1095, rows 2151 | identical |
| Pinnacle 29 (synthetic products) | sell-out 0, inventory rows 1 | units 2203, latest on-hand 101, sell-out rows 1096, inventory rows 310 | identical |

- Year: `W31.csv` without a year -> held, 0 fact rows, message names the missing year; year 2023 confirmed -> 3 rows in week 2023-07-31.
- Stock-only left sales unchanged: week 2024-12-30 units 18 -> 18, on-hand 0 -> 1098 (both customers; Pinnacle sell-out 2159 -> 2159).
- Sales-only left stock unchanged: week 2025-01-06 on-hand 1095 -> 1095, units 0 -> 21 (both customers; Pinnacle inventory rows 307 -> 307).
- Identical re-upload: no change, no superseded record. Overlapping correction: +42 units, 42 superseded records with `figures`.
- Stock positions per customer: 2145 compared, 3 first report, 3 no on-hand (the gap week), 3 chain restarts.
- Re-running the whole set changed no total (each source: True). The superseded trail grows on the re-run
  (the re-run 2024 file and correction replace each other's figures again); totals are unchanged.

## Pinnacle (distributor sales/inventory): rule by rule
1. Week calendar: no gap. Facts are dated by transaction date and snapshot date; weekly views bucket Monday-Sunday. Not changed.
2. Day grain: no gap. Sell-out is stored per transaction date. Not changed.
3. Week numbers without a year: no year is ever guessed; a line with no date does not load (proof: 0 applied), and an inventory file
   without a snapshot date needs a confirmed Application Date period. Difference: there is no "confirm the year" path; DSI files must carry dates.
4. Per figure: no gap for sales vs stock (separate fact tables; proved both ways). Differences: a same-key reload overwrites units in place and
   the earlier figure stays only on the earlier load's staging lines (no superseded table); there is no cross-key supersession, so a correction
   with new invoice numbers adds rows (proof: +2 units).
5. Stock chain: different model. The distributor reconciliation opens from the last snapshot before the first sale and uses the 10 percent band;
   it has no weekly chain to restart. Left as is (N-0110 preserved it).
Limit: the Pinnacle proof used the real fact upsert from resolved staging lines; the DSI file parser and mapping workflow were not scripted.

## Findings
- A day column headed only "Date" is not read as the sale date: rows stage with no period, are not applied, and the job still reads completed
  with a warning. Headers that work: Sale Date, Sales Date, Transaction Date, Date Sold (or Week / Transaction Week for week starts).
- One confirmed year covers every week number in a file; a file running from week 52 into week 1 needs splitting.
- Newest upload wins per figure: loading an old file after a newer one replaces the newer figures for the same weeks.
- Stock positions on cip were not recomputed (no cip data writes in this node): press Recompute on the Stock gap tab.
- Confirming the year of an already-uploaded job is API-only (no button); re-upload with Year confirmed ticked.
- Not rendered in a browser (sign-in).
