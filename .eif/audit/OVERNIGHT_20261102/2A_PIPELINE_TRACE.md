# 2a: Pipeline on cip against the 27 October workbook (read-only, 2 November 2026)

**Result: the difference is fully explained, nothing is unexplained.** The figure 49,849 is a reading taken *before* nine duplicate open facts were retired (audit event 26). Today cip's pipeline is 48,928 units, and the only thing it carries beyond the workbook's 48,898 is three leaked test facts (30 units). Line by line, all 737 workbook open lines match a cip fact with the same quantity.

Labels: **VERIFIED** = I ran it (query file named). **ASSERTED** = taken from a report or code comment and not re-run.

## Where the workbook is

`apps/api/storage/uploads/imports/f8a61716696045269dce5769323418eb/ACZA Shipped Unshipped 20261027.xlsx` (VERIFIED: the file exists; Import Center job 1697 carries that file name, status `completed`, created 2026-10-29 12:05, `2a_01_cip_pipeline_facts.py`). Sheets: `Unship` (723 data rows), `Shipped` (7,346 data rows), `BOM not ready` (2 rows). The report date is the single YYYYMMDD in the file name, 2026-10-27.

## How each side is counted

| Side | Rule | Source |
|---|---|---|
| cip "pipeline units" | facts of the tenant that are *kept* (live, no covering shipped twin, or an open remainder above 0), `line_state = 'open_order'`, `pod_date IS NULL`, quantity = counted (twin remainder) quantity | `apps/api/app/services/supply_overview.py` `_headline_sql` (VERIFIED by reading it; I ran the application's own SQL, below) |
| Workbook open lines | every `Unship` row + every `BOM not ready` row + every `Shipped` row whose Ship Confirm Date is blank or after the report date | Warren's settled decisions 1, 2 and 4 (ASSERTED in the handover; the same rule the loader applies) |

## Figures

| Figure | Value | Label | Query |
|---|---|---|---|
| Workbook open lines / units: Unship | 723 / 47,259 | VERIFIED | `2a_02_workbook_open_lines.py` |
| Workbook open lines / units: Shipped rows with no ship-confirm date (or after 27 Oct) | 12 / 1,316 | VERIFIED | same |
| Workbook open lines / units: BOM not ready | 2 / 323 | VERIFIED | same |
| **Workbook open total** | **737 lines / 48,898 units** ("about 48,900") | VERIFIED | same |
| Workbook Shipped rows that are confirmed shipped (not open) | 7,334 / 506,120 | VERIFIED | same |
| cip headline now (application SQL), `pipeline_lines` / `pipeline_units` | 740 / **48,928** | VERIFIED | `2a_03_join_and_causes.py` ("HEADLINE NOW") |
| cip pipeline facts, fact by fact, counted units | 740 facts / 48,928 | VERIFIED (equals the headline) | `2a_01_cip_pipeline_facts.py` |
| Reading quoted in CURRENT.md and the handover | 49,849 | ASSERTED (`STEP10_STOP_REPORT.md` lines 83 and 132, taken before event 26) | not re-run |

## Line-by-line join

Join key: order number (the quote number for `BOM not ready`, whose SO# column is blank), order line, item. VERIFIED, `2a_03_join_and_causes.py`, output `2a_join_result.json`.

| Result | Lines | Units |
|---|---|---|
| Workbook open lines found on cip with the **same quantity** | 737 | 48,898 |
| Workbook open lines found on cip with a different quantity | 0 | 0 |
| Workbook open lines **not on cip** (the reverse) | 0 | 0 |
| cip pipeline facts **not in the workbook** | 3 | 30 |

All 737 of those cip facts belong to job 1697 (`Unship` 723 / 47,259, `Shipped` sheet 12 / 1,316, `BOM not ready` 2 / 323). Job 1697's facts by state: `open_order` 737 / 48,898, `shipped` 6,612 / 506,120, `closed_superseded` 9 / 921 (VERIFIED).

Stored quantity equals counted quantity on every one of the 740 pipeline facts (the twin-remainder rule changes nothing today), so twins are not a cause of any difference now (VERIFIED, `2a_01`: the stored and counted columns sum to the same figure in every group).

## Per-cause table (adds up to the difference)

Difference asked about: 49,849 − 48,898 = **951 units**.

| # | Cause | Units | Lines | Label |
|---|---|---|---|---|
| 1 | Nine old-key open facts of job 1697 (duplicates of lines that now exist under the new key, left behind when job 1697 was re-processed), retired as `closed_superseded` by `shipped_fact_orphan_open_retire`, audit event 26 on 2 Nov 14:57. They were counted in 49,849 and are excluded now. | 921 | 9 | VERIFIED (their fact ids, quantities and `superseded_by_fact_id` read from cip; `2a_03`) |
| 2 | Three leaked test facts, item codes `AUD-PARI-…`, report type `shipped`, no job, created 2 Jul 2026 by `tests/test_data_integrity_audit.py`, turned into open orders by the unscoped reclassification on 29 Oct (review finding). They count in the pipeline and are not in the workbook. | 30 | 3 | VERIFIED for the facts, item codes, creation date and quantities (ids 99964, 99966, 99968, 10 units each); ASSERTED for the origin (the test file and the 29 Oct reclassification are from the 2 Nov review, `FINDINGS.md` Major/Minor) |
| 3 | Undated Shipped-sheet lines (12 / 1,316), `BOM not ready` (2 / 323), twins, closed states, quantity differences, lines missing on either side | 0 | 0 | VERIFIED (every one of these matches or is absent; see the join) |
| | **Total explained** | **951** | | = 921 + 30 |
| | **Unexplained** | **0** | | |

The nine facts of cause 1, as data (all `Unship`-type order lines, line `1.1`):

| Fact id | Order | Item | Units | Now points at fact |
|---|---|---|---|---|
| 148768 | 151126081010672 | 90NX09J2-M00RW0 | 21 | 170755 |
| 148777 | 151126071008977 | 90NX0AL1-M004B0 | 128 | 170759 |
| 148780 | 151126081014465 | 90NX0861-M01X30 | 36 | 170760 |
| 148785 | 151126081013514 | 90NX0AM2-M00640 | 120 | 170761 |
| 148786 | 151126081013513 | 90NX09J2-M00RW0 | 10 | 170813 |
| 148801 | 151126081010739 | 90NX09J2-M00FP0 | 21 | 170814 |
| 157127 | 151126091006582 | 90NX08N1-M03CC0 | 125 | 170754 |
| 163464 | 151126091007566 | 90NX08F1-M01520 | 300 | 170815 |
| 163465 | 151126101003140 | 90NX0AM2-M00N10 | 160 | 170816 |

Sum 921 units (VERIFIED).

## What this means

- The pipeline gap Warren saw was a timing effect: the 49,849 reading predates event 26. After event 26 the pipeline is 48,928, which is the workbook plus three test facts. I did **not** re-measure 49,849 itself (it is ASSERTED from the step 10 report); the arithmetic 48,928 + 921 = 49,849 closes exactly, which supports it but is not an independent proof that those nine facts were in that reading.
- The remaining 30 units are the leaked test facts. They go with the AUD-PARI cleanup (script `scripts/ops/remove_leaked_test_shipment_facts.py`, plan `.eif/audit/REVIEW_20261102/batch2/AUD_PARI_CLEANUP_PLAN.md`), which needs a clone proof and Warren's go; nothing was run tonight. After it, cip's pipeline would equal the workbook's 48,898 exactly.
- The match is for job 1697 only. Open orders from any other job are zero (no other job's facts appear in the pipeline), so the earlier complete-book closes and the twin retire left no other stragglers (VERIFIED: all 740 pipeline facts are job 1697 or the three test facts).

## Limits

- This compares quantities and keys, not prices, dates or distributor/customer resolution.
- The join key is order, order line, item. `BOM not ready` has no order line; its key is the quote number with the item. Two lines with the same key would be summed (none exist: 737 keys for 737 lines).
- The workbook lines come from the stored copy of the file used by job 1697, which is the file named `…20261027.xlsx` (VERIFIED by name; I did not hash it against an original).
- Read-only proof on every cip run: write probe refused, `default_transaction_read_only = on`, `transaction_read_only = on` (printed to stderr by `queries/ro.py`).

## Files

`queries/ro.py` (helper), `queries/2a_01_cip_pipeline_facts.py` → `queries/2a_cip_pipeline_facts.json`, `queries/2a_02_workbook_open_lines.py` → `queries/2a_workbook_open_lines.json`, `queries/2a_03_join_and_causes.py` → `queries/2a_join_result.json`.
