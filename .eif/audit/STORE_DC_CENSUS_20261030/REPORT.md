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

