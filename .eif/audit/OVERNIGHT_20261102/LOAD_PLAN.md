# Load plan: staged store-level sell-through that is not on the facts (plan only)

No load was run. No job was validated or applied. The customers below were counted from staging, not assumed.

## Discovery

A store-level staging row is one with a non-blank site label, a non-blank raw location token, or a resolved location id. Loaded means `apply_status` in (`applied`, `duplicate`).

VERIFIED (this session, `confirm_headlines.py`): 8 customers have sell-through staging; 4 of them have store-level rows. VERIFIED (script `3_discover.py`) for the split:

| Customer id | Name (observed) | Staged rows | Store-level rows | Loaded rows | Store-level not applied | Jobs |
|---|---|---|---|---|---|---|
| 12 | Incredible Connection | 32,418 | 32,418 | 4,320 | 28,098 | 3 |
| 15 | Makro | 4,124 | 4,124 | 4,070 | 54 | 9 |
| 11 | Hifi | 3,914 | 3,914 | 1,599 | 2,315 | 2 |
| 57 | Game | 3,176 | 3,176 | 2,210 | 966 | 17 |
| 299 | AMAZON COMMERCIAL SERVICES (SOUTH AFRICA) | 46,490 | 0 | 19,392 | 0 | 11 |
| 18 | Computer Mania | 1,659 | 0 | 774 | 0 | 19 |
| 20 | Takealot | 656 | 0 | 440 | 0 | 17 |
| 52 | Evetech | 567 | 0 | 335 | 0 | 13 |

The last four are account-level files. They are out of this plan. `customer_location` was empty at the census (ASSERTED, `.eif/audit/STORE_DC_CENSUS_20261030/REPORT.md`). Staging sites are labels on the row, not location master rows.

## What stops each store-level customer

Dates below are the staged period, not the upload day. `year_confirmed` is null on every one of these jobs. The period is already stored (steward-declared on the early files). An unconfirmed year is not what is holding them. VERIFIED (script `3_jobs.py`, `3_keys.py`, `3_collapse.py`, `3_superseded.py`).

### Customer 12

| Job | File (observed) | Status / stage | Archived | Rows / store rows | Applied | Units staged / not applied | Period | Sites | What stops a load |
|---|---|---|---|---|---|---|---|---|---|
| 900 | IC_Store_sales_WK24.xlsx | completed / validated | yes | 21,634 / 21,634 | 0 | 369 / 369 | 2025-06-09 | 202 | Never applied. 6,248 resolved waiting, 15,386 product not matched. The file's sites are not all this customer's: 104 also appear on job 906, 68 on job 907, 30 on neither |
| 906 | IC_only_Store_sales_WK24.xlsx | completed / validated | yes | 5,392 / 5,392 | 0 | 257 / 257 | 2025-06-09 | 104 | Never applied. 4,320 resolved waiting, 1,072 product not matched |
| 912 | IC_only_Store_sales_WK24.xlsx | completed / validated | yes | 5,392 / 5,392 | 4,320 | 257 / 61 | 2025-06-09 | 104 | The resolved rows were applied and then collapsed: 4,320 lines became 82 facts whose source key has no site (`ct:12:0:<product>:2025-06-09`) while `site_label` is still filled. 1,072 lines stay unmatched. Facts hold 3 units |

### Customer 11

| Job | File (observed) | Status / stage | Archived | Rows / store rows | Applied | Units staged / not applied | Period | Sites | What stops a load |
|---|---|---|---|---|---|---|---|---|---|
| 907 | HiFi_only_Store_sales_WK24.xlsx | completed / validated | yes | 1,957 / 1,957 | 0 | 101 / 101 | 2025-06-09 | 68 | Never applied. 1,599 resolved waiting, 358 product not matched |
| 913 | HiFi_only_Store_sales_WK24.xlsx | completed / validated | yes | 1,957 / 1,957 | 1,599 | 101 / 10 | 2025-06-09 | 68 | Same collapse as job 912: 1,599 lines became 51 facts with a chain key and a site label. Facts hold 1 unit. 358 lines stay unmatched |

### Customer 57

Seventeen jobs, all store-level. The October apply jobs 1662, 1663, 1664 and 1667 are `completed` / `loaded`, not archived, and their facts are site-keyed. The rows still not applied are:

- Archived validated copies of files a later job already loaded (898, 905, 921, 922, 923, 926, and the small unmatched tails on 928, 970, 971). Applying the copy again does not add a week the later job missed.
- A few unmatched product lines on the loaded jobs (1663: 2 lines, 1664: 1 line). Those stay out until the product is matched. No auto-create.

One archived job (968) wrote a future week and was superseded as `week_not_yet_happened` by 1662, which stored the same file as the previous year. Leave 968. Do not load a period after the upload day (`upload_date_rule`).

Loaded facts for this customer are site-keyed (VERIFIED `3_keys.py`). Census class READY is about week coverage and reported stock, not about an unloaded file. ASSERTED from the census: 10 explicit weeks, reported stock on 99% of store-week rows.

### Customer 15

Nine jobs. The October apply jobs 1659, 1660, 1661 and 1665 are loaded and site-keyed. The 54 unapplied rows are `product_not_matched` (13, 6, 5 and 3 on the loaded jobs, and the same tails on the archived copies 965, 966, 967, 972). The archived copies' facts were superseded by those October jobs (`restated_by_newer_load`). There is no large resolved set waiting. Census class PARTIAL is reported stock on 7.9% of store-week rows (ASSERTED). These 54 rows do not change that.

## One plan, any customer

Oldest period first. One job at a time. Clone proof before any write to `cip`. Warren's "run against cip" after the clone counts match. A report per job.

1. Discover, do not assume. Re-run the store-level staging query (site label, raw location token, or resolved location). Keep only customers whose store-level staged rows exceed store-level loaded facts. Account-level customers stay out.
2. Drop a job whose sites belong to more than one customer. Split it, or leave it, and load the per-customer file. Job 900 is that case on this database. Do not apply it.
3. Drop a job that is an older copy of a file a later job already loaded for the same customer and period, including a copy whose week was superseded because the year was wrong.
4. Leave unmatched product rows staged. Do not create a product, a customer, a distributor, or a location.
5. For a resolved set that was applied under a source key with no site, while the staging row has a site label: the current writer must key the fact by customer, product, period and site. Prove that on a clone before applying. Under the accepted replace rule, a newer load replaces the older row for the same customer, product and period. The clone must show the chain-key facts move aside and the site-keyed facts remain, with the same units and the same reported stock, and a second apply changes nothing.
6. Order the remaining jobs by period start, oldest first. For each job: validate, read the load report, then apply. Skip a row whose period starts after the job's upload day. Skip a week-number file whose year is not confirmed.
7. After each job, write a short report: rows read, loaded, not loaded by reason, facts written, units, reported stock, distinct sites, period range, and whether a second apply changed anything.
8. Recompute stock positions only for the customers the load touched, using the existing recompute. Do not store a calculated stock position as a fact.

Clone first, every time. The clone is a copy of `cip`. The proof is the counts in step 5 and step 7. Only then ask for "run against cip". This document is not that ask.

## What a load would change in the census grades

Census classes and the READY rule are ASSERTED from `.eif/audit/STORE_DC_CENSUS_20261030/REPORT.md` (30 Oct). They were not re-run. READY needs at least 8 explicit weeks, a site label on at least 80% of those weeks, one-week labels under 20% of distinct sites, no variant groups, and reported stock on at least half of store-week rows.

| Observed customer | Census class | After the plan |
|---|---|---|
| 57 | READY | Stays READY. The unloaded rows are copies or unmatched products, not missing weeks |
| 15 | PARTIAL | Stays PARTIAL. The 54 unloaded rows are unmatched products. The grade fails on reported-stock coverage, which those rows do not fix |
| 12 | PARTIAL (1 week, 23 sites on the facts) | Stays PARTIAL. A site-keyed re-apply of the same week restores sites and stock for that one week. It does not create 8 weeks |
| 11 | PARTIAL (1 week, 22 sites on the facts) | Stays PARTIAL, for the same reason |
| The four with no store-level rows | NONE | Stay NONE. There is no store row to load |

No grade moves to READY by this load. The two partial customers with one week become usable at store grain for that week only if the chain-key collapse is corrected on the clone first.
