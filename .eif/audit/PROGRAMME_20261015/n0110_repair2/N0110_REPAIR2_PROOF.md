# N-0110 repair 2 — proof (2026-10-15)

Code: `92340adb` (D-0090 supersede by customer/product/period; D-0091 repeats summed, identical copies flagged),
`5e6bc4fd` (a week or month with no year resolves to the latest one started by the receive day).
Script: `replay.py` (re-applies every load with a stored file, oldest first, `received_on` = original day).

## Measured on cip before any write (read-only, `measure.py cip`)

| | rows | stored units | source units |
|---|---|---|---|
| site-merged | 366 (cust 11: 40, 12: 80, 15: 246) | 533 | 7373 |
| repeated, identical | 0 | 0 | 0 |
| repeated, differing | 99 (cust 18: 4, 20: 49, 57: 45, 299: 1) | 432 | 1249 |
| wrong year (2026-09-28, loaded 2026-08-11) | 75 (job 960: 56 / 510 u, job 968: 19 / 19 u) | 529 | — |

## Clone `cip_n0110r2` (dropped after)

Per customer `[rows, units, on-hand]`:

| customer | before | after run 1 | after run 2 |
|---|---|---|---|
| 11 | 51, 1, 15 | 51, 1, 15 | same |
| 12 | 82, 3, 31 | 82, 3, 31 | same |
| 15 | 362, 688, 201 | 1736, 6122, 2053 | same |
| 18 | 302, 2299, 5229 | 302, 2331, 5397 | same |
| 20 | 96, 541, 3357 | 96, 1253, 3357 | same |
| 52 | 130, 690, 14265 | 130, 690, 14265 | same |
| 57 | 769, 1522, 5714 | 769, 1579, 5714 | same |
| 299 | 31, 415, 0 | 31, 415, 0 | same |

Run 2 superseded 0 rows and changed no total (file compare identical).

Units recovered per customer:
- 15 (Makro Dispo): **+5434**. Site-merged chain-level rows restored one row per site. 315 older rows (595 u) were superseded by newer loads for the same customer, product and period, including overlapping weeks in the rolling-year Dispo files.
- 20 (Takealot): **+712**. 49 weeks split over two months were stored last-wins; now summed. On-hand is unchanged because each line repeats one snapshot.
- 57 (Game): **+57**. Differing repeats summed. 19 rows / 19 u moved from 2026-09-28 to 2025-09-29 (`week_not_yet_happened`, net 0).
- 18 (Computer Mania): **+32**. 4 repeated article rows summed; on-hand +168 where the lines' on-hand differed. 56 rows / 510 u moved from 2026-09-28 to 2025-09-29 (net 0).
- 11, 12, 52, 299: 0.

Left under-counted (no stored file): job 903 (cust 15, 43 rows), 911 (57, 13), 912 (12, 24), 913 (11, 11), 918 (299, 1). Job 917 (cust 18) has no file and no under-counted rows.
Loads 955, 956 and 967 stored no on-hand and were replayed sales-only.

## cip

`current_database()=cip`. Same 21 replays (new jobs 1647–1667). Totals after are identical to clone run 1. Wrong-year rows: 0.
Recompute: 7 customers, 701 positions.

Cause table (243 flagged of 314 compared; threshold 1 unit):
overwrite 0 (was 8), unmatched shipment 0, no POD 0, no prior on-hand 37 (was 29), repeated report 108,
unreported weeks 58, unexplained 40 (Computer Mania 28, Evetech 7, Takealot 5).

pytest on cip_test: 248 passed (CST, sell-through, stock gap, tenant profile, lineup period).
