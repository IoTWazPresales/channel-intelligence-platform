# N-0110 repair: measured on cip, read-only (2026-10-15)

Product: `d31433fe` (re-upload supersede, `20261015_0038`), `be0a1d5d` (gap causes).

## Old overwrite: stored rows holding two or more source rows

`probe_overwrite.py cip`: current_database() cip; 1823 fact rows.

| What collapsed into one stored row | rows | units in source rows minus stored |
|---|---|---|
| two or more sale days (the Monday overwrite) | **0** | 0 |
| two or more sites (older site-less key `…:0:…`, last row won) | 366 | 6840 |
| same site, same period repeats (current code still keeps the last) | 99 | 817 |

No applied source row on cip carries a sale day. The only date-like source columns are
attributes (`Last Sold`, `Last Recv`, `LAST PURCHASED`, `LAST SOLD`) or a week (`Transaction Week`).
Site collapse is customers 15 (246 rows), 12 (80), 11 (40). 75 rows sit on a week dated after
the load that wrote them (customer 18: 56, customer 57: 19; week 40 stored as 2026-09-28 by a
load made 2026-08-11).

## Re-upload double count (clone `cip_n0110r`, validate only, then dropped)

Of 26 pre-change loads, 5 had no stored file and 3 are refused now (no on-hand, not sales-only).
13 re-upload under the same keys. 5 would write new keys beside the old rows:
Computer Mania week 40 and ASUS Week 40 (week moved 2026-09-28 -> 2025-09-29), and
Asus Dispo WK1 / WK14 / WK34 (one row per site instead of one per product). See
`N0110_REUPLOAD_PROOF.md` for the fix proven on a clone.

## Why each flagged position differs

`measure_causes.py` via dbrun on cip, READ ONLY transaction, same classifier as the Stock gap tab.
Threshold 1 unit (D-0086). 701 positions, 314 compared, 243 flagged (unchanged; no number moved).

First cause that applies:

| cause | flagged | sign |
|---|---|---|
| (a) sales under-counted by an old overwrite | **8** | 6 over, 2 short; all by site, 0 by sale day |
| (b) shipment excluded, no customer match | **0** | |
| (c) shipment with no proof-of-delivery date | **0** | |
| (d) no prior reported on-hand to start from (site coverage changed) | **29** | 19 over, 10 short |
| (e) none of (a)-(d) | **206** | |

(e) split further, both data gaps found while measuring:

| cause | flagged | |
|---|---|---|
| repeated report: every figure equals the previous report's | 108 | Computer Mania 2025-12-29, 2026-03-30, 2026-06-29, 2026-09-28 store identical figures (different files) |
| unreported weeks: short gap, window has periods with no report | 58 | |
| unexplained: real stock-difference signal | **40** | Computer Mania 28, Evetech 7, Takealot 5 |

Shipments for the unexplained products: 1597 shipped lines matched with POD, 6 matched shipped
without POD (outside the windows), 3 unmatched open orders. So (b) and (c) are 0 by data, not by rule.
