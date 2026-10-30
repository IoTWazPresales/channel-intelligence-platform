# Store and distribution-centre census

Database `cip` as `cip`, read at 2026-10-30 13:43.
Branch at handover: `feat/ns-2-brief-nav-collapse` @ `08031f86`. Session was read-only (`default_transaction_read_only=on`). No migration and no master writes.

Display name is `dim_customer.name`. A store-grain fact row has a non-blank `site_label` or a `customer_location_id`. An explicit week is `week_start_date`, or `period_start_date` when `period_grain` or `period_type` is week. The 80% test uses that customer's distinct explicit weeks. A one-week label appears in exactly one of those weeks. Variant groups are site labels that match after lowercasing and removing every character that is not a letter or digit.

READY for a customer requires at least 8 explicit weeks, at least one site label in 80% or more of those weeks, one-week labels under 20% of distinct site labels, no variant groups, and reported SOH on at least half of explicit-week store rows. PARTIAL means a site label, a fact location id, or a `customer_location` row exists and READY fails. NONE means account-level sell-through only.

READY for a distributor requires a location-like staging column filled on at least half of inventory staging rows (`stock_on_hand` not null), fewer than half of that column's distinct values appearing on only one inventory row, and at least 4 inventory as-of dates. A location master, any filled location-like raw column, or a non-blank `ship_to_raw` is otherwise PARTIAL. NONE means distributor-level facts only.

## A0. Period grain on fact_customer_sellthrough

| period_grain | period_type | rows | week_start | site_label | location_id | reported_soh | period on Monday |
| --- | --- | --- | --- | --- | --- | --- | --- |
| day | daily | 11,710 | 0 | 0 | 0 | 3,865 | 1,680 |
| week | weekly | 2,854 | 226 | 2,404 | 0 | 1,254 | 2,854 |
| (null) | weekly | 334 | 0 | 234 | 0 | 268 | 312 |

## A1. Customer stores

| Customer | Rows | Rows with site_label | Distinct site_labels | Rows with location id | Distinct locations | First explicit week | Last explicit week | Explicit weeks | First store period | Last store period | Store periods |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AMAZON COMMERCIAL SERVICES (SOUTH AFRICA) | 11,732 | 0 | 0 | 0 | 0 |  |  | 0 |  |  | 0 |
| Computer Mania | 302 | 0 | 0 | 0 | 0 |  |  | 0 |  |  | 0 |
| Evetech | 130 | 0 | 0 | 0 | 0 |  |  | 0 |  |  | 0 |
| Game | 769 | 769 | 111 | 0 | 0 | 2025-08-11 | 2026-06-29 | 10 | 2025-08-11 | 2026-06-29 | 10 |
| Hifi | 51 | 51 | 22 | 0 | 0 | 2025-06-09 | 2025-06-09 | 1 | 2025-06-09 | 2025-06-09 | 1 |
| Incredible Connection | 82 | 82 | 23 | 0 | 0 | 2025-06-09 | 2025-06-09 | 1 | 2025-06-09 | 2025-06-09 | 1 |
| Makro | 1,736 | 1,736 | 27 | 0 | 0 | 2024-03-25 | 2026-06-29 | 30 | 2024-03-25 | 2026-06-29 | 30 |
| Takealot | 96 | 0 | 0 | 0 | 0 |  |  | 0 |  |  | 0 |

## A2. Stock at store grain

Shares use store-grain rows. Explicit-week shares use only rows that have an explicit week. In-transit and on-order count when the column is not null, including zero.

| Customer | Store rows | SOH | In transit | On order | Explicit-week rows | SOH of those | In transit of those | On order of those |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AMAZON COMMERCIAL SERVICES (SOUTH AFRICA) | 0 |  |  |  | 0 |  |  |  |
| Computer Mania | 0 |  |  |  | 0 |  |  |  |
| Evetech | 0 |  |  |  | 0 |  |  |  |
| Game | 769 | 99.0% | 0.0% | 0.0% | 769 | 99.0% | 0.0% | 0.0% |
| Hifi | 51 | 100.0% | 0.0% | 0.0% | 51 | 100.0% | 0.0% | 0.0% |
| Incredible Connection | 82 | 100.0% | 0.0% | 0.0% | 82 | 100.0% | 0.0% | 0.0% |
| Makro | 1,736 | 7.9% | 0.0% | 0.0% | 1,736 | 7.9% | 0.0% | 0.0% |
| Takealot | 0 |  |  |  | 0 |  |  |  |

## A3. Site-label stability

| Customer | Explicit weeks | Labels in those weeks | Labels in >=80% of weeks | Labels in one week | Labels on one row | Variant groups |
| --- | --- | --- | --- | --- | --- | --- |
| AMAZON COMMERCIAL SERVICES (SOUTH AFRICA) | 0 | 0 | 0 | 0 | 0 | 0 |
| Computer Mania | 0 | 0 | 0 | 0 | 0 | 0 |
| Evetech | 0 | 0 | 0 | 0 | 0 | 0 |
| Game | 10 | 111 | 10 | 2 | 2 | 0 |
| Hifi | 1 | 22 | 22 | 22 | 16 | 0 |
| Incredible Connection | 1 | 23 | 23 | 23 | 6 | 0 |
| Makro | 30 | 27 | 11 | 0 | 0 | 0 |
| Takealot | 0 | 0 | 0 | 0 | 0 | 0 |


Groups that differ only by case, spacing, or punctuation:

_No rows._

## A4. customer_location

_No rows._

## A5. Raw store, address, and coordinate columns

A key is included when its name matches store, site, outlet, shop, location, address, suburb, city, town, province, region, postal code, zip, or coordinates. Fill rate is non-blank values over all rows for that customer, or that customer and source on staging.

### Fact raw_source_row

| Customer | Key | Filled | Rows | Fill rate |
| --- | --- | --- | --- | --- |
| Game | Site | 769 | 769 | 100.0% |
| Hifi | Site Code | 51 | 51 | 100.0% |
| Hifi | Site Name | 51 | 51 | 100.0% |
| Incredible Connection | Site Code | 82 | 82 | 100.0% |
| Incredible Connection | Site Name | 82 | 82 | 100.0% |
| Makro | Site | 1,736 | 1,736 | 100.0% |
| Makro | Site Name | 1,736 | 1,736 | 100.0% |


### Staging raw_row_payload

`import_job` has no customer column. Customer is `resolved_customer_id` on the staging line.

| Customer | Source | Staging rows | raw_location_token fill | site_label fill |
| --- | --- | --- | --- | --- |
| AMAZON COMMERCIAL SERVICES (SOUTH AFRICA) | (customer file) | 46,490 | 0.0% | 0.0% |
| Computer Mania | (customer file) | 1,659 | 0.0% | 0.0% |
| Evetech | (customer file) | 567 | 0.0% | 0.0% |
| Game | (customer file) | 3,176 | 100.0% | 100.0% |
| Hifi | (customer file) | 3,914 | 100.0% | 100.0% |
| Incredible Connection | (customer file) | 32,418 | 100.0% | 100.0% |
| Makro | (customer file) | 4,124 | 100.0% | 100.0% |
| Takealot | (customer file) | 656 | 0.0% | 0.0% |


| Customer | Source | Key | Filled | Rows | Fill rate |
| --- | --- | --- | --- | --- | --- |
| Game | (customer file) | Site | 3,176 | 3,176 | 100.0% |
| Hifi | (customer file) | Site Code | 3,914 | 3,914 | 100.0% |
| Hifi | (customer file) | Site Name | 3,914 | 3,914 | 100.0% |
| Incredible Connection | (customer file) | Site Code | 32,418 | 32,418 | 100.0% |
| Incredible Connection | (customer file) | Site Name | 32,418 | 32,418 | 100.0% |
| Makro | (customer file) | Site | 4,124 | 4,124 | 100.0% |
| Makro | (customer file) | Site Name | 4,124 | 4,124 | 100.0% |

## B6. distributor_location

_No rows._

## B7. Distributor sell-out and inventory location columns

`fact_sales_sellout`, `fact_returns`, and `fact_inventory_distributor` have no column whose name matches store, location, site, branch, or outlet.

Staging keys match branch, warehouse, DC, depot, location, site, store, plant, godown, or address. Sell-out fill uses rows with `quantity_sold`. Inventory fill uses rows with `stock_on_hand`. A staged row can be both. The key scan completed. No staging key name matched that list.

_No rows._


Distinct non-blank values, top 25 by row count:

_No rows._


### Inventory facts: as-of dates and products

| Distributor | Rows | As-of dates | Products | First as-of | Last as-of |
| --- | --- | --- | --- | --- | --- |
| Brandhouse | 2,356 | 53 | 133 | 2025-01-03 | 2026-05-18 |
| Compuspeed | 2,504 | 66 | 84 | 2025-01-03 | 2026-06-08 |
| Dgstore | 1,350 | 22 | 90 | 2025-06-23 | 2026-02-09 |
| HV | 706 | 33 | 59 | 2025-02-17 | 2026-04-20 |
| Mustek | 16,821 | 78 | 928 | 2025-01-03 | 2026-06-08 |
| Pepkor | 96 | 1 | 96 | 2025-01-06 | 2025-01-06 |
| Pinnacle | 13,784 | 75 | 582 | 2025-01-03 | 2026-06-08 |
| Rectron | 9,775 | 73 | 493 | 2025-01-03 | 2026-06-08 |
| Redington | 6 | 2 | 3 | 2025-03-10 | 2025-03-17 |
| Syntech | 13 | 1 | 13 | 2026-06-08 | 2026-06-08 |

## B8. Shipment ship_to_raw

| Distributor | ship_to_raw | Lines | Units |
| --- | --- | --- | --- |
| ACZA | ACZA-ZA-C-03 | 64 | 1,663 |
| ACZA | ACZA-ZA-C-01 | 144 | 790 |
| ACZA | ACZA-ZA-BB-03 | 9 | 10 |
| AXIZ | AXIZ-ZA-IET-01 | 79 | 5,049 |
| AXIZ | AXIZ-ZA-ITL-01 | 13 | 1,176 |
| Brandhouse | BRANDHOUSE-MU-C | 267 | 14,777 |
| Brandhouse | BRANDHOUSE-MU-BB | 33 | 1,329 |
| Brandhouse | BRANDHOUSE-MU-TB | 1 | 34 |
| Compuspeed | COMPUSPEED-MU-BB | 126 | 5,736 |
| Compuspeed | COMPUSPEED-MU-C | 86 | 3,480 |
| Compuspeed | COMPUSPEED-MU-TB | 6 | 290 |
| DCC | DCC-ZA-BB | 314 | 28,054 |
| DCC | DCC-ZA-TB | 8 | 1,220 |
| Dgstore | DGSTORE-ZA-ET-01 | 137 | 1,363 |
| Dgstore | DGSTORE-ZA-ET-02 | 37 | 664 |
| Firsttech | FIRSTTECH-ZA-ET-01 | 54 | 822 |
| HV | HV-MU-C-MG | 78 | 4,530 |
| HV | HV-MU-C-MG-01 | 19 | 1,446 |
| HV | HV-MU-BB-MG-01 | 23 | 1,204 |
| Influencer | INFLUENCER-ZA-C | 4 | 7 |
| Mitsumi | MITSUMI-AE-C-ZA-01 | 28 | 1,696 |
| Mustek | MUSTEK-ZA-IR-01 | 1,736 | 103,858 |
| Mustek | MUSTEK-ZA-BB-01 | 832 | 79,536 |
| Mustek | MUSTEK-ZA-C-01 | 1,035 | 74,915 |
| Mustek | MUSTEK-ZA-TB-01 | 180 | 43,732 |
| Mustek | MUSTEK-ZA-IET-01 | 137 | 8,682 |
| Mustek | MUSTEK-ZA-ESH-01 | 44 | 1,063 |
| NITI | NITI-AE-TB-MU-01 | 2 | 70 |
| Pepkor | PEPKOR-ZA-DR-01 | 1,603 | 162,982 |
| Pepkor | PEPKOR-ZA-BB-01 | 147 | 9,287 |
| Pinnacle | PINNACLE-ZA-IR-01 | 3,295 | 479,220 |
| Pinnacle | PINNACLE-ZA-C-01 | 1,183 | 89,929 |
| Pinnacle | PINNACLE-ZA-IR-02 | 129 | 42,793 |
| Pinnacle | PINNACLE-ZA-IET-01 | 630 | 36,153 |
| Pinnacle | PINNACLE-ZA-BB-01 | 371 | 25,934 |
| Pinnacle | PINNACLE-ZA-TB-01 | 40 | 22,233 |
| Pinnacle | PINNACLE-ZA-ITL-01 | 37 | 6,142 |
| Pinnacle | PINNACLE-ZA-ESH-01 | 126 | 2,710 |
| Pinnacle | PINNACLE-ZA-EDU-01 | 6 | 240 |
| Pinnacle | PINNACLE-ZA-C-02 | 1 | 99 |
| Rectron | RECTRON-ZA-C | 1,549 | 121,525 |
| Rectron | RECTRON-ZA-BB | 697 | 71,921 |
| Rectron | RECTRON-ZA-IR | 75 | 18,575 |
| Rectron | RECTRON-ZA-ITL | 61 | 14,111 |
| Rectron | RECTRON-ZA-IET | 131 | 9,174 |
| Rectron | RECTRON-ZA-TB | 26 | 4,278 |
| Rectron | RECTRON-ZA-EDU | 2 | 225 |
| Redington | REDINGTON-AE-BB-ZA-01 | 33 | 2,978 |
| Redington | REDINGTON-AE-TB-ZA-01 | 10 | 241 |
| S4dl | S4DL-MU-TB | 2 | 116 |
| S4dl | S4DL-MU-BB | 1 | 65 |
| Stylus | STYLUS-AO-C-02 | 17 | 8,147 |
| Stylus | STYLUS-AO-C-03 | 6 | 828 |
| Stylus | STYLUS-AO-BB-03 | 2 | 138 |
| Stylus | STYLUS-AO-BB-01 | 1 | 21 |
| Superdist | SUPERDIST-MU-BB | 11 | 1,034 |
| Superdist | SUPERDIST-MU-BB-MG-01 | 3 | 184 |
| Syntech | SYNTECH-ZA-C-03 | 45 | 1,018 |
| Syntech | SYNTECH-ZA-C-01 | 13 | 67 |
| Tarsus | TARSUS-ZA-C-04 | 2 | 63 |
| Three | THREE-MU-C | 17 | 836 |
| Three | THREE-MU-BB | 10 | 683 |
| Three | THREE-MU-BB-01 | 1 | 10 |
| (unresolved distributor) | FIRSTTECH-ZA-ET-01 | 4 | 72 |

Lines with a blank ship_to_raw:

| Distributor | Lines | Units |
| --- | --- | --- |
| Mustek | 2 | 323 |
| (unresolved distributor) | 3 | 30 |

## C9. Store-week history and stock beside sales

A store-week is one store key and one explicit week. The store key is the site label, or `loc:` plus the location id when the label is blank. The store-week has both when some row has units sold not zero and some row has reported SOH. The same-row share is store-grain rows where that one row has both.

| Customer | Explicit weeks | Store-weeks | Store-weeks with units and SOH | Same-row units and SOH |
| --- | --- | --- | --- | --- |
| AMAZON COMMERCIAL SERVICES (SOUTH AFRICA) | 0 | 0 |  |  |
| Computer Mania | 0 | 0 |  |  |
| Evetech | 0 | 0 |  |  |
| Game | 10 | 591 | 98.8% | 98.3% |
| Hifi | 1 | 22 | 4.5% | 2.0% |
| Incredible Connection | 1 | 23 | 13.0% | 3.7% |
| Makro | 30 | 578 | 9.7% | 7.9% |
| Takealot | 0 | 0 |  |  |

## C10. Ship confirm date and POD date

A line counts when both `ship_confirm_date` and `pod_date` are present. The range is the earliest and latest of each date on those lines. `line_state` is the stored value.

| Distributor | line_state | Lines | Lines with both dates | First ship confirm | Last ship confirm | First POD | Last POD |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ACZA | shipped | 182 | 182 | 2020-02-26 | 2026-10-26 | 2020-02-26 | 2026-10-26 |
| AXIZ | shipped | 92 | 92 | 2022-07-30 | 2023-03-23 | 2022-08-05 | 2023-04-13 |
| Brandhouse | shipped | 288 | 285 | 2020-01-14 | 2026-08-21 | 2020-02-11 | 2026-08-29 |
| Compuspeed | shipped | 146 | 143 | 2020-07-24 | 2026-09-18 | 2020-07-24 | 2026-10-23 |
| DCC | shipped | 193 | 159 | 2025-08-12 | 2026-09-14 | 2025-08-20 | 2026-09-30 |
| Dgstore | shipped | 168 | 168 | 2025-02-25 | 2026-06-10 | 2025-02-28 | 2026-07-23 |
| Firsttech | shipped | 27 | 21 | 2026-08-21 | 2026-10-20 | 2026-09-02 | 2026-10-21 |
| HV | shipped | 115 | 113 | 2020-02-17 | 2025-11-21 | 2020-03-16 | 2025-12-26 |
| Influencer | shipped | 4 | 4 | 2023-06-15 | 2023-06-15 | 2023-06-15 | 2023-06-15 |
| Mitsumi | shipped | 23 | 23 | 2026-03-31 | 2026-07-31 | 2026-05-07 | 2026-08-07 |
| Mustek | shipped | 3,483 | 3,431 | 2020-01-07 | 2026-10-16 | 2020-01-13 | 2026-10-22 |
| NITI | shipped | 1 | 1 | 2026-10-13 | 2026-10-13 | 2026-10-21 | 2026-10-21 |
| Pepkor | shipped | 1,259 | 1,183 | 2023-06-30 | 2026-10-09 | 2023-07-11 | 2026-10-21 |
| Pinnacle | shipped | 5,282 | 5,252 | 2020-01-14 | 2026-10-09 | 2020-02-21 | 2026-10-23 |
| Rectron | shipped | 2,230 | 2,201 | 2020-01-07 | 2026-09-16 | 2020-01-13 | 2026-10-21 |
| Redington | shipped | 43 | 43 | 2023-08-12 | 2025-02-28 | 2023-09-14 | 2025-03-14 |
| S4dl | shipped | 3 | 3 | 2024-03-12 | 2025-10-21 | 2024-04-18 | 2025-10-21 |
| Stylus | shipped | 26 | 26 | 2021-05-14 | 2025-03-28 | 2021-05-14 | 2025-03-28 |
| Superdist | shipped | 14 | 14 | 2023-04-18 | 2026-05-22 | 2023-04-18 | 2026-07-30 |
| Syntech | shipped | 44 | 42 | 2025-11-06 | 2026-08-21 | 2025-11-06 | 2026-10-20 |
| Tarsus | shipped | 2 | 2 | 2020-01-20 | 2020-02-19 | 2020-03-05 | 2020-05-05 |
| Three | shipped | 28 | 28 | 2022-09-20 | 2024-08-20 | 2022-11-21 | 2024-09-25 |

## C11. Promotion scope

`cpor_case` rows: 310. `cpor_case_line` rows: 657.
`cpor_case` and `cpor_case_line` have no column whose name matches store, location, site, branch, or outlet.

JSON keys on `source_snapshot_json` and `cost_evidence_json` that match those words:

_No rows._


Case notes mentioning store, location, or site: 0 of 310. Line remarks mentioning those words: 4 of 657. A text mention is not a store-scope column.

## Classification

### Customers

| Customer | Class | Basis |
| --- | --- | --- |
| AMAZON COMMERCIAL SERVICES (SOUTH AFRICA) | NONE | sell-through has no site label, no location id, and no customer_location row |
| Computer Mania | NONE | sell-through has no site label, no location id, and no customer_location row |
| Evetech | NONE | sell-through has no site label, no location id, and no customer_location row |
| Takealot | NONE | sell-through has no site label, no location id, and no customer_location row |
| Hifi | PARTIAL | 1 explicit week; all 22 site labels appear in that week; reported SOH is present on every store row |
| Incredible Connection | PARTIAL | 1 explicit week; all 23 site labels appear in that week; reported SOH is present on every store row |
| Makro | PARTIAL | 11 of 27 site labels are in at least 80% of 30 weeks and none appear in only one week; reported SOH on 7.9% of store-week rows |
| Game | READY | 10 of 111 site labels are in at least 80% of 10 weeks; 2 of 111 appear in one week; no case, spacing, or punctuation groups; reported SOH on 99.0% of store-week rows |

### Distributors

Included when the distributor has a location master row, distributor staging, a sell-out fact, an inventory fact, or a shipment.

| Distributor | Class | Basis |
| --- | --- | --- |
| (unresolved distributor) | PARTIAL | 1 non-blank ship_to_raw values |
| ACZA | PARTIAL | 3 non-blank ship_to_raw values |
| AXIZ | PARTIAL | 2 non-blank ship_to_raw values |
| Brandhouse | PARTIAL | 3 non-blank ship_to_raw values; inventory facts have 53 as-of dates and no location column |
| Compuspeed | PARTIAL | 3 non-blank ship_to_raw values; inventory facts have 66 as-of dates and no location column |
| DCC | PARTIAL | 2 non-blank ship_to_raw values |
| Dgstore | PARTIAL | 2 non-blank ship_to_raw values; inventory facts have 22 as-of dates and no location column |
| Firsttech | PARTIAL | 1 non-blank ship_to_raw values |
| HV | PARTIAL | 3 non-blank ship_to_raw values; inventory facts have 33 as-of dates and no location column |
| Influencer | PARTIAL | 1 non-blank ship_to_raw values |
| Mitsumi | PARTIAL | 1 non-blank ship_to_raw values |
| Mustek | PARTIAL | 6 non-blank ship_to_raw values; inventory facts have 78 as-of dates and no location column |
| NITI | PARTIAL | 1 non-blank ship_to_raw values |
| Pepkor | PARTIAL | 2 non-blank ship_to_raw values; inventory facts have 1 as-of dates and no location column |
| Pinnacle | PARTIAL | 10 non-blank ship_to_raw values; inventory facts have 75 as-of dates and no location column |
| Rectron | PARTIAL | 7 non-blank ship_to_raw values; inventory facts have 73 as-of dates and no location column |
| Redington | PARTIAL | 2 non-blank ship_to_raw values; inventory facts have 2 as-of dates and no location column |
| S4dl | PARTIAL | 2 non-blank ship_to_raw values |
| Stylus | PARTIAL | 4 non-blank ship_to_raw values |
| Superdist | PARTIAL | 2 non-blank ship_to_raw values |
| Syntech | PARTIAL | 2 non-blank ship_to_raw values; inventory facts have 1 as-of dates and no location column |
| Tarsus | PARTIAL | 1 non-blank ship_to_raw values |
| Three | PARTIAL | 3 non-blank ship_to_raw values |

## D. Customer distribution centres

Read 2026-10-30 15:31 on `cip` as `cip`, read-only (`default_transaction_read_only=on`). Produced by `census_dc.py`; queries in `queries_section_d.sql`.

Model (Warren, 30 Oct): customers run their own distribution centres, distributors deliver into them, and the DCs supply the stores. So DC stock and DC-level sell-in are a separate level between distributor and store.

Raw key match: names containing `dc`, `d/c`, `distribution`, `warehouse`, `wh`, `depot`, `hub`, `jhb`, `cpt`, `dbn`, `midrand`, `centurion` (short tokens only as whole words), or `stock`/`soh`/`on hand` combined with a place word (dc, warehouse, depot, hub, store, site, branch, location, and the city codes). Site-label match uses the same words on the label value. Fill rate is non-blank values over all rows for that customer (fact `raw_source_row`, or staging `raw_row_payload`).

Classes: DC STOCK REPORTED = rows or columns with units or SOH at a DC-like place. DC NAMED ONLY = a DC-like key or label exists with no stock or sales figure on it. NO DC DATA = nothing DC-like found. A negative describes this search and its patterns, not proof of absence.

**Result.** No customer reports DC stock. No raw key (fact or staging) and no site label matched a DC word for any of the 8 customers with sell-through rows, so D1 and D2 are empty and `customer_location` has no rows (D5). The only DC-shaped signal is the shipment ship-to `PEPKOR-ZA-DR-01` (1,603 lines, 162,982 units), which receives for Incredible Connection, Hifi, JD Furniture and the Homeless lines: that is Pepkor's DC, named on inbound shipments only. Game's and Makro's store lists use store names; a DC filed under a plain store-style name would not match these words, so the label list should be eyeballed once with Warren before this is read as proof that those customers have no DC.

### D1. Raw keys matching a DC word

_No rows._


### D2. Site labels that look like a DC

_No rows._


### D3. ship_to_raw on lines that resolve to a customer (direct)

315 customer/ship-to pairs across 156 customers; the top three ship-to values per customer by units are shown. Every pair is in `queries_section_d.sql` (D4_ship_to_direct_customers). Ship-to codes look like `DISTRIBUTOR-COUNTRY-CHANNEL-NN`; the DC-style ones are in D4.

| Customer | Distributor | ship_to_raw | Dealer tokens | Lines | Units |
| --- | --- | --- | --- | --- | --- |
| 3g Mobile | Three | THREE-MU-BB | 3 | 9 | 668 |
| 3g Mobile | Three | THREE-MU-C | 5 | 14 | 569 |
| ABSA | Mustek | MUSTEK-ZA-TB-01 | 1 | 12 | 3,900 |
| ABSA | Mustek | MUSTEK-ZA-BB-01 | 1 | 1 | 2,000 |
| AMAZON COMMERCIAL SERVICES (SOUTH AFRICA) | Pinnacle | PINNACLE-ZA-IR-01 | 4 | 255 | 6,765 |
| AMAZON COMMERCIAL SERVICES (SOUTH AFRICA) | Pinnacle | PINNACLE-ZA-IET-01 | 1 | 2 | 48 |
| Afrihost | Rectron | RECTRON-ZA-BB | 2 | 2 | 152 |
| Afrocentric | Mustek | MUSTEK-ZA-TB-01 | 2 | 6 | 800 |
| Agriculture Limpopo | Mustek | MUSTEK-ZA-TB-01 | 1 | 2 | 109 |
| Ally Pool | Pinnacle | PINNACLE-ZA-C-01 | 2 | 3 | 540 |
| Apex High School | Mustek | MUSTEK-ZA-TB-01 | 2 | 4 | 1,300 |
| Apex High School | Rectron | RECTRON-ZA-TB | 2 | 2 | 235 |
| Attorney General's Chambers Botswana | Rectron | RECTRON-ZA-TB | 1 | 1 | 105 |
| Auckland PARK Preparatory School | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 125 |
| BASA School | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 80 |
| BASA School | Rectron | RECTRON-ZA-TB | 1 | 1 | 40 |
| BB - Marketing Sample | ACZA | ACZA-ZA-BB-03 | 1 | 3 | 3 |
| BB - Marketing Sample | ACZA | ACZA-ZA-C-03 | 1 | 3 | 3 |
| BT GAMES (PTY) LTD | Pinnacle | PINNACLE-ZA-IR-01 | 2 | 21 | 212 |
| BUSINESS CONNEXION (PTY) LTD | Pinnacle | PINNACLE-ZA-BB-01 | 1 | 1 | 20 |
| Bank Info: Citibank | Stylus | STYLUS-AO-C-02 | 1 | 2 | 1,881 |
| Beyond Zero | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 72 |
| Bitou Municipality | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 114 |
| Botswana Communications Regulatory Authority | Rectron | RECTRON-ZA-TB | 1 | 2 | 505 |
| Cape Nature | Pinnacle | PINNACLE-ZA-TB-01 | 1 | 1 | 40 |
| Cape Winelands | Mustek | MUSTEK-ZA-TB-01 | 1 | 2 | 120 |
| Central BANK Mauritius | Three | THREE-MU-BB | 1 | 1 | 15 |
| Central BANK Mauritius | Three | THREE-MU-BB-01 | 1 | 1 | 10 |
| City Of Johannesburg | Mustek | MUSTEK-ZA-TB-01 | 2 | 3 | 360 |
| City Of Tshwane | Mustek | MUSTEK-ZA-TB-01 | 2 | 3 | 650 |
| Cloudedu | Rectron | RECTRON-ZA-C | 1 | 7 | 764 |
| Coghsta Limpopo | Mustek | MUSTEK-ZA-TB-01 | 1 | 6 | 267 |
| Community Safety Gauteng | Mustek | MUSTEK-ZA-TB-01 | 1 | 2 | 120 |
| Computer Mania | Mustek | MUSTEK-ZA-IR-01 | 6 | 1,286 | 72,309 |
| Computer Mania | Mustek | MUSTEK-ZA-BB-01 | 6 | 49 | 1,909 |
| Computer Mania | Pinnacle | PINNACLE-ZA-IR-01 | 1 | 20 | 1,183 |
| Computer Mania Homeless | Mustek | MUSTEK-ZA-IR-01 | 1 | 2 | 14 |
| DBE | Mustek | MUSTEK-ZA-TB-01 | 1 | 2 | 255 |
| DHS | Mustek | MUSTEK-ZA-TB-01 | 1 | 2 | 284 |
| DOE Limpopo | Mustek | MUSTEK-ZA-TB-01 | 1 | 2 | 293 |
| DOE Limpopo | Pinnacle | PINNACLE-ZA-TB-01 | 1 | 5 | 223 |
| Department Of Education MP | Mustek | MUSTEK-ZA-TB-01 | 1 | 4 | 4 |
| Department Of Health Gauteng | Mustek | MUSTEK-ZA-TB-01 | 1 | 3 | 248 |
| Department Of Sport EC | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 60 |
| Dept Of Education Limpopo | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 115 |
| Dept Oh Health Limpopo | Mustek | MUSTEK-ZA-TB-01 | 1 | 2 | 825 |
| Dubai Hub | Superdist | SUPERDIST-MU-BB-MG-01 | 1 | 2 | 130 |
| Dubai Hub | Compuspeed | COMPUSPEED-MU-BB | 1 | 4 | 94 |
| ESQUIRE TECHNOLOGIES | Pinnacle | PINNACLE-ZA-IR-01 | 3 | 11 | 4,446 |
| ESQUIRE TECHNOLOGIES | Rectron | RECTRON-ZA-C | 2 | 7 | 802 |
| ESQUIRE TECHNOLOGIES | Pinnacle | PINNACLE-ZA-C-01 | 3 | 10 | 780 |
| Ecole Du Centre | Compuspeed | COMPUSPEED-MU-TB | 2 | 3 | 85 |
| Elangeni TVET College | Pinnacle | PINNACLE-ZA-TB-01 | 1 | 2 | 390 |
| Eshop | Pinnacle | PINNACLE-ZA-ESH-01 | 8 | 126 | 2,710 |
| Eshop | Dgstore | DGSTORE-ZA-ET-01 | 5 | 137 | 1,363 |
| Eshop | Mustek | MUSTEK-ZA-ESH-01 | 2 | 44 | 1,063 |
| Eskom | Mustek | MUSTEK-ZA-TB-01 | 2 | 5 | 5 |
| Evetech | Pinnacle | PINNACLE-ZA-IET-01 | 4 | 402 | 15,575 |
| Evetech | Pinnacle | PINNACLE-ZA-IR-01 | 8 | 409 | 12,870 |
| Evetech | Mustek | MUSTEK-ZA-IR-01 | 5 | 256 | 10,917 |
| FNB | Mustek | MUSTEK-ZA-IR-01 | 3 | 22 | 1,332 |
| FNB | Mustek | MUSTEK-ZA-IET-01 | 4 | 28 | 1,115 |
| FNB | Mustek | MUSTEK-ZA-C-01 | 1 | 8 | 669 |
| Financial And Fiscal Commission | Pinnacle | PINNACLE-ZA-TB-01 | 1 | 1 | 30 |
| Firsttech | Pinnacle | PINNACLE-ZA-C-01 | 1 | 1 | 216 |
| Furnmart | Pinnacle | PINNACLE-ZA-IR-01 | 5 | 42 | 10,296 |
| Furnmart | Rectron | RECTRON-ZA-IR | 1 | 15 | 1,584 |
| Furnmart | Pinnacle | PINNACLE-ZA-C-01 | 1 | 6 | 576 |
| GP Education | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 334 |
| GP Education | DCC | DCC-ZA-TB | 1 | 1 | 167 |
| GP Health | Mustek | MUSTEK-ZA-TB-01 | 1 | 6 | 99 |
| Game | Pinnacle | PINNACLE-ZA-IR-01 | 11 | 450 | 98,308 |
| Game | Pinnacle | PINNACLE-ZA-IR-02 | 5 | 129 | 42,793 |
| Game | Pinnacle | PINNACLE-ZA-TB-01 | 2 | 2 | 5,181 |
| Gauteng Department Of Health | Mustek | MUSTEK-ZA-TB-01 | 1 | 4 | 375 |
| Google South Africa | Mustek | MUSTEK-ZA-TB-01 | 2 | 5 | 38 |
| HOMECHOICE (PTY) LTD | Rectron | RECTRON-ZA-IR | 1 | 1 | 1,215 |
| Hifi | Pepkor | PEPKOR-ZA-DR-01 | 13 | 302 | 38,322 |
| Hifi | Pinnacle | PINNACLE-ZA-IR-01 | 12 | 83 | 12,566 |
| Hifi | Pinnacle | PINNACLE-ZA-TB-01 | 1 | 1 | 1,188 |
| Hilton College | Mustek | MUSTEK-ZA-BB-01 | 1 | 1 | 120 |
| Hilton College | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 5 |
| Hilton School | Rectron | RECTRON-ZA-TB | 1 | 3 | 150 |
| Homeless | Rectron | RECTRON-ZA-C | 4 | 176 | 13,084 |
| Homeless | Mustek | MUSTEK-ZA-C-01 | 3 | 66 | 4,659 |
| Homeless | Pinnacle | PINNACLE-ZA-C-01 | 3 | 49 | 3,808 |
| Homeless Q4 Retail | Pepkor | PEPKOR-ZA-BB-01 | 1 | 1 | 114 |
| Homeless Q4 Retail | Rectron | RECTRON-ZA-BB | 1 | 1 | 114 |
| IC Entry | Pinnacle | PINNACLE-ZA-IR-01 | 1 | 4 | 2,544 |
| IC Entry | Pinnacle | PINNACLE-ZA-C-01 | 1 | 1 | 684 |
| IC Homeless | Pepkor | PEPKOR-ZA-DR-01 | 1 | 2 | 24 |
| IC Online | Pinnacle | PINNACLE-ZA-C-01 | 1 | 3 | 136 |
| IEC | Mustek | MUSTEK-ZA-TB-01 | 1 | 5 | 880 |
| Icasa | Mustek | MUSTEK-ZA-TB-01 | 1 | 2 | 55 |
| Impact Catalyst | Mustek | MUSTEK-ZA-TB-01 | 1 | 2 | 846 |
| Incredible Connection | Pepkor | PEPKOR-ZA-DR-01 | 9 | 1,267 | 122,960 |
| Incredible Connection | Pinnacle | PINNACLE-ZA-IR-01 | 8 | 736 | 121,763 |
| Incredible Connection | Pepkor | PEPKOR-ZA-BB-01 | 10 | 142 | 8,801 |
| Inscape | Pinnacle | PINNACLE-ZA-TB-01 | 1 | 1 | 24 |
| JD Furniture | Pinnacle | PINNACLE-ZA-IR-01 | 5 | 38 | 6,966 |
| JD Furniture | Pinnacle | PINNACLE-ZA-C-01 | 1 | 1 | 1,485 |
| JD Furniture | Pepkor | PEPKOR-ZA-DR-01 | 2 | 7 | 1,116 |
| LOOT | Pinnacle | PINNACLE-ZA-TB-01 | 1 | 1 | 40 |
| Laerskool Van Riebeeckpark | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 40 |
| Lebone School | Rectron | RECTRON-ZA-EDU | 1 | 2 | 225 |
| Lewi | Pinnacle | PINNACLE-ZA-IR-01 | 3 | 16 | 9,867 |
| Lewi | Pinnacle | PINNACLE-ZA-TB-01 | 1 | 2 | 1,988 |
| Lewi | Pinnacle | PINNACLE-ZA-C-01 | 1 | 1 | 1,485 |
| Lewis Furniture | Pinnacle | PINNACLE-ZA-IR-01 | 4 | 56 | 14,364 |
| Lewis Furniture | Rectron | RECTRON-ZA-IET | 1 | 1 | 216 |
| Lighthouse Primary & Secondary School | S4dl | S4DL-MU-TB | 2 | 2 | 116 |
| Lighthouse Primary & Secondary School | Brandhouse | BRANDHOUSE-MU-TB | 1 | 1 | 34 |
| Limpopo Economic Dev | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 75 |
| Limpopo Education | Pinnacle | PINNACLE-ZA-TB-01 | 1 | 1 | 280 |
| Limpopo Provincial Government | Mustek | MUSTEK-ZA-TB-01 | 1 | 2 | 90 |
| Limpopo Social Dev | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 124 |
| Limpopo Sport Arts And Culture | Mustek | MUSTEK-ZA-TB-01 | 1 | 2 | 320 |
| Limpopo Transport | Mustek | MUSTEK-ZA-TB-01 | 1 | 4 | 370 |
| MARKETING | ACZA | ACZA-ZA-C-01 | 1 | 1 | 200 |
| MICRO-D (PTY) LTD | Mustek | MUSTEK-ZA-BB-01 | 1 | 2 | 108 |
| MICROPOINT (SA) (PTY) LTD | Rectron | RECTRON-ZA-C | 1 | 3 | 324 |
| MICROPOINT (SA) (PTY) LTD | Rectron | RECTRON-ZA-BB | 1 | 1 | 280 |
| MKT Sample | Mustek | MUSTEK-ZA-C-01 | 2 | 11 | 406 |
| MKT Sample | Pinnacle | PINNACLE-ZA-C-01 | 1 | 2 | 402 |
| MKT Sample | ACZA | ACZA-ZA-C-01 | 9 | 20 | 119 |
| MP Education | Mustek | MUSTEK-ZA-TB-01 | 1 | 2 | 1,634 |
| MP Health | Mustek | MUSTEK-ZA-TB-01 | 3 | 5 | 1,010 |
| MP Health | Pinnacle | PINNACLE-ZA-TB-01 | 1 | 2 | 361 |
| Makro | Pinnacle | PINNACLE-ZA-IR-01 | 9 | 783 | 151,849 |
| Makro | Pinnacle | PINNACLE-ZA-TB-01 | 1 | 1 | 2,970 |
| Makro | Pinnacle | PINNACLE-ZA-BB-01 | 4 | 33 | 1,664 |
| Makro Homeless | Pinnacle | PINNACLE-ZA-IR-01 | 1 | 18 | 228 |
| Mango 5 | Rectron | RECTRON-ZA-TB | 1 | 4 | 76 |
| Maranatha Christion School | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 50 |
| Marketiing Material Order By Estelle | ACZA | ACZA-ZA-C-01 | 1 | 5 | 68 |
| Matrix | Mustek | MUSTEK-ZA-IR-01 | 10 | 95 | 8,146 |
| Matrix | Rectron | RECTRON-ZA-IR | 3 | 26 | 2,484 |
| Matrix | Mustek | MUSTEK-ZA-C-01 | 1 | 5 | 934 |
| Media Sample | ACZA | ACZA-ZA-C-01 | 2 | 6 | 10 |
| Media Sample | ACZA | ACZA-ZA-BB-03 | 1 | 2 | 2 |
| Microman | Mustek | MUSTEK-ZA-C-01 | 3 | 19 | 1,456 |
| Microman | Mustek | MUSTEK-ZA-IR-01 | 1 | 15 | 1,028 |
| Ministry Of Education Mauritius | Compuspeed | COMPUSPEED-MU-TB | 1 | 1 | 125 |
| Ministy OR Labour | NITI | NITI-AE-TB-MU-01 | 1 | 2 | 70 |
| Motheo TVET | Pinnacle | PINNACLE-ZA-IR-01 | 1 | 2 | 2,970 |
| Mustek Deal | Mustek | MUSTEK-ZA-TB-01 | 1 | 11 | 14,000 |
| Nelson Mandela University | DCC | DCC-ZA-TB | 1 | 6 | 1,020 |
| Nsfa | Mustek | MUSTEK-ZA-TB-01 | 1 | 2 | 2,772 |
| OK FURNITURE | Rectron | RECTRON-ZA-IR | 1 | 1 | 990 |
| Omni Digital (Pty) Ltd | Rectron | RECTRON-ZA-IR | 1 | 1 | 990 |
| Omni Digital (Pty) Ltd | Rectron | RECTRON-ZA-BB | 1 | 3 | 368 |
| Open Channel | Rectron | RECTRON-ZA-C | 20 | 1,327 | 103,480 |
| Open Channel | Mustek | MUSTEK-ZA-BB-01 | 18 | 743 | 71,919 |
| Open Channel | Pinnacle | PINNACLE-ZA-C-01 | 21 | 1,028 | 70,389 |
| Orient Islamic School | Mustek | MUSTEK-ZA-TB-01 | 1 | 2 | 70 |
| Orient School | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 90 |
| PC PALACE CC | Mustek | MUSTEK-ZA-BB-01 | 1 | 1 | 8 |
| Polytechnic | Compuspeed | COMPUSPEED-MU-TB | 1 | 1 | 50 |
| Q2 Retail | Rectron | RECTRON-ZA-BB | 1 | 2 | 60 |
| Retail - Incredible | Pepkor | PEPKOR-ZA-BB-01 | 2 | 2 | 206 |
| Retail - Incredible | Rectron | RECTRON-ZA-BB | 1 | 2 | 80 |
| Returnable Tiger Lake PR Media Review Sample | ACZA | ACZA-ZA-C-01 | 1 | 2 | 2 |
| Rivonia Primary School | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 23 |
| Rondebosch Boys' Preparatory School | Pinnacle | PINNACLE-ZA-TB-01 | 1 | 2 | 252 |
| SADC | HV | HV-MU-BB-MG-01 | 1 | 3 | 190 |
| SADC - NITI | Compuspeed | COMPUSPEED-MU-BB | 1 | 3 | 310 |
| SAPS | Mustek | MUSTEK-ZA-TB-01 | 2 | 22 | 5,817 |
| SITA | Mustek | MUSTEK-ZA-TB-01 | 2 | 5 | 1,690 |
| SITA | Rectron | RECTRON-ZA-TB | 1 | 4 | 1,284 |
| SITA | Mustek | MUSTEK-ZA-BB-01 | 2 | 10 | 704 |
| Saasta | Redington | REDINGTON-AE-TB-ZA-01 | 1 | 4 | 106 |
| Sacaa | Pinnacle | PINNACLE-ZA-TB-01 | 1 | 1 | 180 |
| Sample - MP Sample | ACZA | ACZA-ZA-C-01 | 1 | 1 | 1 |
| Sample - Media Review Sample | ACZA | ACZA-ZA-C-01 | 1 | 1 | 4 |
| Sample ADV | Rectron | RECTRON-ZA-TB | 1 | 1 | 1 |
| Samples | ACZA | ACZA-ZA-C-01 | 10 | 57 | 125 |
| Samples | ACZA | ACZA-ZA-C-03 | 4 | 22 | 38 |
| Samples | ACZA | ACZA-ZA-BB-03 | 2 | 4 | 5 |
| Sapsc5 | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 500 |
| Shoprite | Pinnacle | PINNACLE-ZA-C-01 | 1 | 13 | 1,920 |
| Smartlab | Rectron | RECTRON-ZA-TB | 2 | 6 | 1,692 |
| Smollan Group | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 1 |
| Social Development | Mustek | MUSTEK-ZA-TB-01 | 5 | 7 | 901 |
| Sports Arts And Culture Eastern Cape | Redington | REDINGTON-AE-TB-ZA-01 | 1 | 6 | 135 |
| St Charles | Rectron | RECTRON-ZA-TB | 1 | 1 | 40 |
| St John's Diocesan School For Girl | Pinnacle | PINNACLE-ZA-TB-01 | 1 | 2 | 90 |
| St Patrick’s College | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 72 |
| St. John School | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 2 |
| Sub-d | Rectron | RECTRON-ZA-BB | 2 | 14 | 1,252 |
| Sub-d | Pinnacle | PINNACLE-ZA-BB-01 | 1 | 2 | 160 |
| TAL | Mustek | MUSTEK-ZA-C-01 | 1 | 13 | 501 |
| TB - Dept Of Comm Safety | Mustek | MUSTEK-ZA-TB-01 | 1 | 2 | 12 |
| TBH | Brandhouse | BRANDHOUSE-MU-C | 5 | 190 | 11,320 |
| TBH | Brandhouse | BRANDHOUSE-MU-BB | 3 | 21 | 637 |
| TCS | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 30 |
| TFG | Mustek | MUSTEK-ZA-IR-01 | 5 | 48 | 9,263 |
| TUT | Mustek | MUSTEK-ZA-TB-01 | 1 | 6 | 486 |
| TUT | Pinnacle | PINNACLE-ZA-TB-01 | 1 | 3 | 233 |
| TUT | DCC | DCC-ZA-TB | 1 | 1 | 33 |
| TWK | Mustek | MUSTEK-ZA-TB-01 | 1 | 2 | 600 |
| Takealot | Pinnacle | PINNACLE-ZA-IET-01 | 9 | 208 | 19,975 |
| Takealot | Pinnacle | PINNACLE-ZA-IR-01 | 10 | 313 | 18,364 |
| Takealot | Rectron | RECTRON-ZA-IET | 4 | 73 | 5,700 |
| Technolab | Pinnacle | PINNACLE-ZA-C-01 | 1 | 4 | 396 |
| Telkom | Pinnacle | PINNACLE-ZA-ITL-01 | 3 | 10 | 2,380 |
| Telkom | Pinnacle | PINNACLE-ZA-C-01 | 1 | 4 | 1,485 |
| Umgungundlovu TVET | Mustek | MUSTEK-ZA-TB-01 | 1 | 1 | 132 |
| University Of Johannesburg | Pinnacle | PINNACLE-ZA-TB-01 | 1 | 1 | 45 |
| Ux482_returnable Media Review Sample By Juan | ACZA | ACZA-ZA-C-01 | 1 | 1 | 2 |
| VAN SCHAIK BOOKSTORE | Mustek | MUSTEK-ZA-IR-01 | 1 | 1 | 297 |
| Vodacom | Rectron | RECTRON-ZA-ITL | 5 | 61 | 14,111 |
| Vodacom | Pinnacle | PINNACLE-ZA-ITL-01 | 3 | 27 | 3,762 |
| Vodacom | Rectron | RECTRON-ZA-IR | 2 | 11 | 3,062 |
| WINELANDS STUDIO (PTY)LTD | Mustek | MUSTEK-ZA-TB-01 | 1 | 2 | 83 |
| WOOTWARE COMPUTERS | Rectron | RECTRON-ZA-IET | 4 | 31 | 834 |
| WOOTWARE COMPUTERS | Rectron | RECTRON-ZA-C | 2 | 9 | 174 |
| WOOTWARE COMPUTERS | Pinnacle | PINNACLE-ZA-C-01 | 1 | 2 | 48 |
| WSL | Pinnacle | PINNACLE-ZA-TB-01 | 1 | 8 | 5,214 |
| WSL | Pinnacle | PINNACLE-ZA-IR-01 | 1 | 3 | 1,221 |
| Wza260200006 | ACZA | ACZA-ZA-C-03 | 1 | 4 | 400 |
| Wza260700035 | ACZA | ACZA-ZA-C-03 | 1 | 2 | 30 |
| Wza260700036 | ACZA | ACZA-ZA-C-03 | 1 | 8 | 24 |
| Wza260700038 | ACZA | ACZA-ZA-C-03 | 1 | 3 | 91 |
| Wza260700043 | ACZA | ACZA-ZA-C-03 | 1 | 7 | 245 |
| École Du Nord | Compuspeed | COMPUSPEED-MU-TB | 1 | 1 | 30 |


### D4. ship_to_raw with a `-DR-`, `-DC-`, `-WH-` or DC word, all lines

| Distributor | ship_to_raw | Lines | Units |
| --- | --- | --- | --- |
| Pepkor | PEPKOR-ZA-DR-01 | 1,603 | 162,982 |


`-DR-` lines by customer/dealer token (who is the receiver):

| Dealer token | Distributor | ship_to_raw | Lines | Units |
| --- | --- | --- | --- | --- |
| Q4 IC | Pepkor | PEPKOR-ZA-DR-01 | 370 | 30,824 |
| Q3 IC | Pepkor | PEPKOR-ZA-DR-01 | 352 | 29,055 |
| Q1 IC | Pepkor | PEPKOR-ZA-DR-01 | 235 | 25,837 |
| Q2 IC | Pepkor | PEPKOR-ZA-DR-01 | 198 | 15,488 |
| Q4 IC RFP | Pepkor | PEPKOR-ZA-DR-01 | 65 | 12,852 |
| Q4 Hifi | Pepkor | PEPKOR-ZA-DR-01 | 82 | 7,440 |
| Q1 Hifi | Pepkor | PEPKOR-ZA-DR-01 | 34 | 5,188 |
| Q3 Hifi | Pepkor | PEPKOR-ZA-DR-01 | 51 | 4,794 |
| Q3 IC RFP | Pepkor | PEPKOR-ZA-DR-01 | 26 | 4,628 |
| Q4 HiFi RFP | Pepkor | PEPKOR-ZA-DR-01 | 22 | 4,536 |
| Q1 IC RFP | Pepkor | PEPKOR-ZA-DR-01 | 19 | 3,612 |
| Q3 HiFi RFP | Pepkor | PEPKOR-ZA-DR-01 | 17 | 3,024 |
| Q4 HiFi | Pepkor | PEPKOR-ZA-DR-01 | 20 | 2,572 |
| Q2 HiFi | Pepkor | PEPKOR-ZA-DR-01 | 21 | 2,476 |
| Q1 HiFi | Pepkor | PEPKOR-ZA-DR-01 | 13 | 2,412 |
| Q2 Hifi | Pepkor | PEPKOR-ZA-DR-01 | 17 | 2,232 |
| Q1 HiFi RFP | Pepkor | PEPKOR-ZA-DR-01 | 9 | 1,836 |
| Q3 HiFi | Pepkor | PEPKOR-ZA-DR-01 | 13 | 1,332 |
| Q4 JD Furn | Pepkor | PEPKOR-ZA-DR-01 | 3 | 648 |
| Q1 JD Furn | Pepkor | PEPKOR-ZA-DR-01 | 4 | 468 |
| Q4 IC/Hifi RFP | Pepkor | PEPKOR-ZA-DR-01 | 1 | 408 |
| Q1 HIFI | Pepkor | PEPKOR-ZA-DR-01 | 2 | 372 |
| Q3 Homeless | Pepkor | PEPKOR-ZA-DR-01 | 14 | 324 |
| Q3 IC Cycling Deal | Pepkor | PEPKOR-ZA-DR-01 | 1 | 256 |
| Q1 Homeless | Pepkor | PEPKOR-ZA-DR-01 | 6 | 144 |
| Q3 HIFI | Pepkor | PEPKOR-ZA-DR-01 | 1 | 108 |
| Q4 Homeless | Pepkor | PEPKOR-ZA-DR-01 | 5 | 92 |
| Q4 IC Homeless | Pepkor | PEPKOR-ZA-DR-01 | 2 | 24 |


### D5. customer_location types

_No rows._


### D6. Classification

| Customer | Class | Basis |
| --- | --- | --- |
| Hifi | DC NAMED ONLY | shipments go to `PEPKOR-ZA-DR-01` (302 lines, 38,322 units) with no stock reported there |
| Homeless | DC NAMED ONLY | shipments go to `PEPKOR-ZA-DR-01` (24 lines, 532 units) with no stock reported there |
| IC Homeless | DC NAMED ONLY | shipments go to `PEPKOR-ZA-DR-01` (2 lines, 24 units) with no stock reported there |
| Incredible Connection | DC NAMED ONLY | shipments go to `PEPKOR-ZA-DR-01` (1,267 lines, 122,960 units) with no stock reported there |
| JD Furniture | DC NAMED ONLY | shipments go to `PEPKOR-ZA-DR-01` (7 lines, 1,116 units) with no stock reported there |
| AMAZON COMMERCIAL SERVICES (SOUTH AFRICA) | NO DC DATA | no DC-like raw key, no DC-like site label, no DC-style ship-to |
| Computer Mania | NO DC DATA | no DC-like raw key, no DC-like site label, no DC-style ship-to |
| Evetech | NO DC DATA | no DC-like raw key, no DC-like site label, no DC-style ship-to |
| Game | NO DC DATA | no DC-like raw key, no DC-like site label, no DC-style ship-to |
| Makro | NO DC DATA | no DC-like raw key, no DC-like site label, no DC-style ship-to |
| Takealot | NO DC DATA | no DC-like raw key, no DC-like site label, no DC-style ship-to |


145 further customers appear only on shipment lines (no sell-through rows) and show no DC-like ship-to: NO DC DATA. Counts by class over all 156 customers: DC STOCK REPORTED 0, DC NAMED ONLY 5, NO DC DATA 151.
