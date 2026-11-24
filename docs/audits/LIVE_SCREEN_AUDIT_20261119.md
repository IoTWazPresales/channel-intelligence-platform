# Live screen audit — 2026-11-19 (SAST)

Live app `http://localhost:3000` on RF2300014-NB3, main checkout at `22beb215` (`feat/integrate-20261103`), live DB `cip`.
Every SQL figure below was read from `cip` in a read-only psql session (`default_transaction_read_only=on`, `current_database()` printed = `cip`), between 16:20 and 16:45 SAST. No code, config or data was changed.

## STATUS OF THIS AUDIT

- Sections 1–2: the four items Warren found, proven from code and live data (16:20–16:45 SAST).
- Section 7: D1 reader restore stopped; nothing was written to `cip`.
- Section 8: why discovery has not found websites and listings (read-only, dry run).
- **Section 9: signed-in screenshots of all 56 routes at 1280x800 and 390x844 (16:53–17:33 SAST), compared and classified.** The sign-in block noted earlier was cleared with the local admin login (not recorded here).

## Plain-language summary

1. **Listings — "no listings"**: the listings exist (218) and Evetech is being read every 30 minutes today (last read 16:06). The screen shows "0 observations / Last check: not yet" because the page's `/listing-capture/intelligence` call loads all 163,716 readings (with their stored page copies) one listing at a time and takes **90 seconds**; until it returns, the counts show 0. Amazon and Takealot have not been read since **4 Nov**, because their page-reader settings were deleted from code on 3 Nov and never copied into the database; the restore script built on 13 Nov was **never applied to `cip`**. Hifi, Incredible Connection, Makro, Computer Mania and Game have no website set up at all.
2. **Store map**: no store has ever had a coordinate on `cip` (`customer_location` has **0 rows**). By design, coordinates come only from (a) an exact match of the store's name to a bundled list of South African towns, or (b) someone dropping a pin. Store names look like "HIFI CORP MUSINA MALL", so the exact match never hits, and nobody has dropped a pin. There is no geocoding step to run. This is a design gap, not today's merges.
3. **Line-ups (1,646 pending for everyone)**: these are 1,647 old **draft** rows created in one go on **8 Aug 2026 18:41** by the "apply net requirement to line-up" action, before the reporting-customer rule existed. Only 177 rows (6 customers) belong to the 8 "Reports expected" customers; **1,470 rows across 598 customers do not**. Today's #122 stops *new* ones, but the list endpoint shows every row with no reporting filter, and nothing cleaned up the old rows.
4. **Promotion planner**: it is **not** sell-through only. It reads line-ups, lineup shelf prices, demand forecasts, weeks-of-cover (distributor stock), listing prices, competitor prices, shipments/buy plans/sell-out (for cost), SKU assumptions and earlier cases. The PR #96 price rule (shopper listing price, else lineup shelf price) directly conflicts with "sell-through only". Layout matches the mock-up only partly (details in 1.4).

Reports strip: Hifi and Incredible Connection "522 days ago" is what the data says: the only files ever loaded for them (`HiFi_only_Store_sales_WK24.xlsx`, `IC_only_Store_sales_WK24.xlsx`, loaded 10 Nov 2026) have no year in them and were dated week 24 of **2025** (9 Jun 2025). Whether that should have been 2026 needs Warren's confirmation (see questions).

## 1. The four items Warren found

### 1.1 Market & Listings (`/listing-capture`)

| Fact | Evidence (cip, read-only) |
|---|---|
| 218 listings, not 200 | `customer_listing`: amazon 51 active; evetech 24 active + 64 out_of_stock; takealot 32 active + 42 dead_link + 5 out_of_stock = 218. The header "200 monitored listings" is the page size: `MarketSurface.tsx:318` requests `/listings?page_size=200` and `:863` prints `listings.length`. "89 active" counts active rows **within the first 200** only. |
| Readings exist | `listing_observation` 163,716 rows on all 218 listings, 2026-08-09 → **2026-11-19 16:06**. Today: 2,731 OK (200), 63 OK (404), 4 parse_failed. |
| Why "0 observations / Last check: not yet" | `obsCount` (`MarketSurface.tsx:850`) and `lastCheckAt` (`:398`) come only from `GET /listing-capture/intelligence`. `build_listing_intelligence` (`apps/api/app/services/listing_capture/intelligence_v1.py`, loop from ~line 160) does one query **per listing** loading every `ListingObservation` ORM row, including `raw_snapshot` (LargeBinary, `models/listing_capture.py:54`). Timed on the live DB at 16:40 by calling the same function from the API venv (SELECTs only, no commit; note: libpq `PGOPTIONS` read-only flag did not apply to that driver session, so it was read-only by code, not by session): **90.1 s**, returned 218 items / 163,716 observations, no error. While it runs the page shows 0 and "not yet"; React Query `retry: 1` and each tab re-fires it (4 calls in a row in `api.log`). |
| Amazon / Takealot "Not configured", last check 4 Nov | `listing_site`: takealot and amazon `adapter_key` **empty**, no `details_url_pattern`/`search_url_pattern`; evetech `adapter_key=html_page` (autoconfigure 12/13 Nov). Last readings: amazon 2026-11-04 00:33, takealot 2026-11-04 00:33. Cause: commit `3ea6cce4` (3 Nov) deleted the per-site readers from code (`takealot_fetch.py`, `auto_finder.py`, registry dispatch) and migration `20261103_0053` did not carry them into `listing_site` (`docs/ops/listing_site_readers_20261113.json` "about"). |
| Reader restore never applied | Script `apps/api/scripts/ops/restore_listing_site_readers.py` + snapshot `docs/ops/listing_site_readers_20261113.json` landed in `3b64c6df` (13 Nov). No apply log under `C:\Users\warren_eliason\cip-apply-logs\` (only `20261110-step3-listing-seed`); `docs/BACKLOG.md` BACKLOG-234 says "Do not run the reader restore script against `cip`"; `listing_site` still has empty columns. |
| Hifi, Incredible Connection, Makro, Computer Mania, Game "no site key" | Only 3 `listing_site` rows exist (takealot, amazon, evetech). These 5 reporting customers have no website/site key, so discovery skips them. Never built/configured for them. |
| Not caused by today | No listing tables touched by 0062/0063; poll job runs (worker beat up; readings today). Stop dates are 4 Nov. |

Class: **DATA STEP** (reader restore: fills empty columns on 2 `listing_site` rows — takealot 6 values, amazon 2; nothing else written) · **CODE BUG** (intelligence N+1 + raw_snapshot load, 90 s; header count = page size) · **NOT BUILT / DECISION** (sites for the other 5 reporting customers; seller names per site — `not_in_code_warren_must_supply` in the snapshot).
Fix sizes: intelligence read as one aggregate SQL without `raw_snapshot` — small (≈0.5 day incl. tests); header shows `total` — tiny; restore — 10 min on a clone, then apply (backup first).

### 1.2 Stores map (Sell-through → Stores and DCs)

| Fact | Evidence |
|---|---|
| No coordinates ever on cip | `customer_location`: **0 rows** total (only table with `latitude/longitude`). |
| Where coordinates are meant to come from | `apps/api/app/services/store_dc/place_name.py` docstring: "does not call a geocoder and it does not write a coordinate". `suggest_store_location` matches the store name **exactly** (after case/punctuation fold; whole label or a part split by `, ; | /` or spaced dash) to `store_dc/data/za_populated_places.csv` (GeoNames). A coordinate is written only by `drop_pin` (`store_dc/map.py:203`) into `customer_location`. Recorded as intended in `terminals/cip-requirements-alignment-20261118.md:28` ("No new geocoding decision is needed"). |
| Why "No place match. Drop a pin." everywhere | Store names on cip: `HIFI CORP MUSINA MALL`, `INCREDIBLE CELLULAR MUSINA`, `Amanzimtoti Main Store`, `GAME LILONGWE` (latest per customer). The whole name is never a town name and has no separator, so exact match fails. Stores on the map: Game 111, Incredible Connection 104, Hifi 68, Makro 27; Takealot/Amazon/Evetech/Computer Mania have no store labels. |
| Regression? | No. Never had data; no job exists to run; no API key involved. |

Class: **NOT BUILT / WRONG RULE** (decision needed: how pins get made). Options and sizes in section 4.

### 1.3 Planning → Lineup cases (1,647 plan lines / 1,646 pending)

| Fact | Evidence |
|---|---|
| What the screen lists | `fact_lineup_plan_item` via `GET /lineup/items` (`apps/api/app/api/v1/endpoints/lineup.py:129-151`): filters only customer/channel/period — **no reporting-customer filter**. |
| Rows | 1,647 rows, all `2026Q2`; 1,646 `draft` + 1 `approved` (approved 2026-09-02, actor blank, `lineup_plan_item_event` id 1). |
| Who made them | All created **2026-08-08 18:41** in one batch, notes `b2_net_requirement dist=… forecast_share=…` = `apply_net_requirement_to_lineup` (`services/lineup/export_apply.py:293`, endpoint `POST /lineup/…apply-net-requirement`, `lineup.py:604`), added in `9e4f72e9` (1 Aug). Not from #118/#119/#122. |
| Reporting vs not | Reporting (`customer_report_config.reports_expected`, 8 customers): **177 rows, 6 customers**. Not reporting: **1,470 rows, 598 customers**. |
| Today's change | `5713f961` (#122) makes **new** applies skip non-reporting customers (`export_apply.py:262-284`). Existing rows untouched; list not filtered. |
| Knock-on | `derive_planned_reservation_sync` (`services/cpor/promo_plan_builder.py:365-372`) reads up to 5,000 `fact_lineup_plan_item` rows with no customer filter → the budget "planned reservation" includes the 1,470 non-reporting drafts. |

Class: **CODE BUG** (list + planned reservation need the reporting filter; small, ≈0.5 day) · **DATA STEP** (optional: retire the 1,470 non-reporting draft rows — needs Warren's yes; nothing deleted here).

### 1.4 Promotion planner (`/promotions`) — sell-through only?

Warren's rule: the planner uses **only** customer sell-through. It does not today. Every non-sell-through source (live row counts in brackets):

| # | Where | Source | Used for |
|---|---|---|---|
| 1 | `promo_plan_builder._specs_from_lineup` (`:122-131`) | `commercial_lineup_case/line` (36 / 3,446) | which products to propose |
| 2 | `_srp_evidence_by_product_sync` (`:336-362`) | lineup `dap_evidence_local` / `msrp_local` | price (SRP) for reserve |
| 3 | `derive_planned_reservation_sync` (`:365-457`) | `fact_lineup_plan_item` (1,647, all customers) + `commercial_sku_assumption` (31) | planned reserve / budget check |
| 4 | `_forecast_volume_sync` (`:308-333`, used `:963`, `:1100`) | `fact_demand_forecast` (66,627) | expected units |
| 5 | `load_promotion_line_evidence` (`:700-711`) | `customer_listing` + `listing_observation` | last shopper price |
| 6 | `_approved_competitor_prices` (`:611-646`, used `:717-722`) | `fact_competitor_price` (0) / approved mappings (0) | price context |
| 7 | `load_promotion_line_evidence` (`:761-767`) | `weeks_of_cover_observation` (217,260) — distributor stock cover | stock health / high cover |
| 8 | `suggest_intake_weighted_mac` (`services/cpor/intake_weighted_mac.py`, called `:939`, `:1539`) | `fact_inbound_shipment` (15,818), `fact_buy_plan` (0), `fact_sales_sellout` (58,128 — distributor sell-out, not customer sell-through), `fact_lineup_plan_item` | per-line cost (MAC) |
| 9 | `support_bias`, `norms_and_comparable`, `portfolio_intelligence`, `build_same_customer_comparables` (`:224`) | earlier `cpor_case/line` (310 / 657) | support norms, comparables, KPI money |
| 10 | **PR #96 item 6 price rule** `store_dc/stock_actions._srp_for_line` (`stock_actions.py:350-373`), used by aged-stock Promote (`:528-531`, `:623`) | shopper **listing price**, else **lineup shelf price (msrp)**; with `load_promotion_line_evidence` also **competitor prices**; comparables use **earlier cases** | promotion price; no price → `no_positive_srp`, no draft |

Sell-through *is* used: `FactCustomerSellthrough` units/SOH (`:742-751`), aged-stock valuation from the customer's reported MAC/unit cost (`stock_actions.py` `AGED_COST_BASIS`).

**CONFLICT (flagged, not resolved):** the PR #96 item 6 price derivation and items 1–9 contradict "sell-through only". Sell-through files carry `unit_sell_price`, `unit_cost`, `unit_mac`, `reported_soh`, so a sell-through-only price/cost/stock is possible, but expected units have no sell-through-only forecast today. Needs Warren's answer (section 4, Q1).

Mock-up vs page (code read, no screenshot yet):

| Mock-up | Page today (`PromotionPlannerSurface.tsx`) | Class |
|---|---|---|
| KPI strip: In planning, Live promotions, Planned reserve, Actual support, At-risk actions | In planning `:395`, Live promotions `:406`, At-risk `:418` present; **Planned reserve, Actual support missing**; extra cards: Drafts to finish, Ended, Awaiting approval, Starting in 4 weeks, Unplanned aged stock, Calendar clashes (`:434-500`) | NOT BUILT (BACKLOG-254) |
| Filters: Customer, Status, dates, Distributor, Product | `CaseScopeFilters` (customer/distributor/product) + stage filter; date range not confirmed | verify on screen |
| Timeline by customer, Week/Month, Live/Approved/Planned/Ended bars | **Not on `/promotions`**. A separate `/promotions/timeline` (`CustomerTimelineSurface`, `customer-calendar/timeline`) exists; no Week/Month toggle found in the planner; no clash marker | NOT BUILT |
| Detail panel: support, expected units, stock health, linked claims, evidence, risks, next actions | `PlanWorkspace` (case detail, support bias, CIP quantities); **stock health, linked claims, structured risks missing** (BACKLOG-254) | NOT BUILT |
| Action queue: Overdue approvals, Low stock risk, Funding gaps, Evidence outstanding, Conflicting windows | Overdue approvals `:320`, Evidence outstanding `:333`, Conflicting windows `:345`; **Low stock risk, Funding gaps missing** | NOT BUILT |
| Real data | `cpor_case`: settled 210, ended 74, cancelled 23, **draft 3, live 0, approved 0** → "Live promotions" and most queues are legitimately near-empty | DATA (no current cases) |

## 2. Reports strip ("Hifi / Incredible Connection last 522 days ago")

`fact_customer_sellthrough` latest period per reporting customer: Amazon 2026-10-12 · Game 2026-06-29 · Makro 2026-06-29 · Computer Mania 2026-06-29 · Takealot 2026-07-27 · Evetech 2026-07-27 · **Hifi 2025-06-09 · Incredible Connection 2025-06-09**. Hifi/IC: one file each ever (`HiFi_only_Store_sales_WK24.xlsx`, `IC_only_Store_sales_WK24.xlsx`, loaded 2026-11-10, 1,544 / 4,237 rows); the raw rows have no year (columns `Sales TW`, `Site Code`, `Site Name`, …), and the importer dated them week 24 of 2025. The week starting 2025-06-09 ends 2025-06-15, which is 522 days before 2026-11-19, so "522 days" is the data, not a reader fault. If the file was week 24 **2026**, it is a **CODE BUG** (year inference for year-less week files); otherwise it is real staleness (no newer Hifi/IC file loaded). Other customers are 4–5 months stale (last loads 11 Aug–21 Oct): real.

## 3. Route list (from `apps/web/src/features/shell/navConfig.ts`)

Overview: `/brief` · Business dashboard `/dashboards` · Reports `/reports` · Report inbox `/inbox`
Stock & Sell-through: `/stock`, `/stock?lens=cover`, `/stock?lens=movement`, `/channel-intelligence`, `/stock/replenishment`, `/stock?lens=execution`, `/forecasts`
Supply & Inbound: `/supply`, `/supply/shipments`, `/admin/shipment-evidence`, `/admin/po-management`
Planning: `/lineup`, `/lineup/cases`, `/commercial-planner`, `/roadmap`, `/pricing`
Promotions & Funding: `/commercial-planner/cpor-cases`, `/promotions`, `/promotions/timeline`, `/commercial-planner/cpor-cases/claims`, `/commercial-planner/cpor-cases/payment-evidence-import`, `/commercial-planner/cpor-cases/historical-import`, `/admin/customer-commercial-terms`, `/budgets`
Market & Listings: `/listing-capture` (tabs registry, observations, intelligence, proposals, quality[planned]), `/competition?tab=mappings`, `/competition?tab=prices`, `/competition?tab=competitor-listings` [planned]
Data & Stewardship: `/admin/imports`, `/admin/imports?template=customer_sell_through`, `/admin/mappings`, `/admin/masters`, `/admin/products`, `/admin/product-master-gaps`, `/admin/customers`, `/admin/customers/duplicates?tab=name_similarity`, `/admin/distributors`, `/admin/distributors/duplicates`, `/admin/channels-regions`, `/admin/cst-steward`, `/admin/steward-audit`
Administration: `/admin/users/list`, `/admin/ops`, `/admin/sql-viewer`, `/admin/port-conditions`, `/admin/audit-log`, `/settings`
Also linked: `/lineup/new-customer`, `/sell-out` (→ `/stock?lens=movement`).

Per-route status: see section 9.

## 4. Decisions needed from Warren (WRONG RULE / design)

1. **Planner sell-through only.** Today it also uses line-ups, forecasts, distributor stock cover, listing and competitor prices, shipments and earlier cases (table 1.4), and the PR #96 price rule takes the shopper listing price, else the lineup shelf price. Options: (a) strictly sell-through: price = sell-through `unit_sell_price`, cost = sell-through MAC/unit cost, stock = sell-through SOH, expected units = sell-through run-rate; drop the rest; (b) sell-through for units/stock, keep listing/lineup price as a fallback shown as "not sell-through"; (c) keep as is.
2. **Store pins.** Options: (a) manual pins only (as built; someone drops ~310 pins); (b) better offline match — strip the chain name and words like "Mall"/"Store", match the remaining town against the GeoNames list, steward confirms (≈1 day, no outside service); (c) a geocoding service (e.g. Google Places; needs an API key and per-call cost; ≈1–2 days).
3. **Old line-up drafts.** 1,470 draft rows for 598 non-reporting customers from 8 Aug. Options: (a) hide them (filter only, keep rows); (b) mark them cancelled/archived on `cip` (1,470 row updates, backup first); (c) delete them.
4. **Hifi / Incredible Connection WK24 files.** Were they week 24 of 2025 or 2026? If 2026, re-date 5,781 rows (DATA STEP) and fix year inference (CODE BUG).
5. **Listing sites for Hifi, Incredible Connection, Makro, Computer Mania, Game.** Should CIP watch their websites? If yes, which site per customer, and each customer's own seller name per site.
6. **Reader restore on `cip`.** BACKLOG-234 says not to run it on `cip`; Warren's 16:2x message authorises it. Confirm the amazon `first_party_seller` stays empty (snapshot says code never named one).

## 5. DATA STEPs (each: backup, clone proof, `current_database()`, then apply)

| Step | Writes | Size |
|---|---|---|
| D1 Listing-reader restore (`restore_listing_site_readers.py --apply`) | fills empty columns only on `listing_site` takealot (adapter_key, details/search/product URL patterns, page_id_pattern, first_party_seller, rate_limit) and amazon (adapter_key, rate_limit); evetech kept | 2 rows updated |
| D2 (after Q3) line-up drafts | `fact_lineup_plan_item` non-reporting drafts | 1,470 rows |
| D3 (after Q4) Hifi/IC re-date | `fact_customer_sellthrough` period fields | 5,781 rows |
| D4 (after Q2) store pins | `customer_location` inserts | up to ~310 rows |

## 6. CODE BUG / NOT BUILT, grouped by files (for non-overlapping lanes)

| Lane | Items | Files |
|---|---|---|
| L1 Listings read speed + counts | intelligence N+1 / raw_snapshot (90 s); header shows page size not total; active count over first page only | `apps/api/app/services/listing_capture/intelligence_v1.py`, `apps/api/app/api/v1/endpoints/listing_capture.py`, `apps/web/src/features/market-listings/MarketSurface.tsx` |
| L2 Line-ups reporting filter | `/lineup/items` + planned reservation ignore `reports_expected` | `apps/api/app/api/v1/endpoints/lineup.py`, `apps/api/app/services/cpor/promo_plan_builder.py` (`derive_planned_reservation_sync` only), `apps/web/src/features/lineup/*` |
| L3 Planner layout vs mock-up (start now) | Planned reserve + Actual support KPIs; timeline by customer with Week/Month and status bars on the planner; detail panel stock health / linked claims / risks; Low stock risk + Funding gaps queue cards; clash marker | `apps/web/src/features/promotions-funding/PromotionPlannerSurface.tsx`, `PlanWorkspace.tsx`, `timeline/*` (UI only; data sources wait for Q1) |
| L4 Planner data sources (waits for Q1) | items 1–10 in table 1.4 | `apps/api/app/services/cpor/promo_plan_builder.py`, `intake_weighted_mac.py`, `apps/api/app/services/store_dc/stock_actions.py` (overlaps L2 file: sequence L2 first) |
| L5 Store pins (waits for Q2) | place matcher or geocoder | `apps/api/app/services/store_dc/place_name.py`, `map.py`, `apps/web/src/features/store-dc/StoreMap.tsx` |
| L6 Year inference (waits for Q4) | year-less WK files | CST sell-through importer (not yet located) |

Matches a written requirement: L2 (Warren 2026-11-19: line-ups only for reporting customers; built for new writes in #122), L3 (mock-up + BACKLOG-254), L1 (navConfig "screen shows the last check", BACKLOG-226 coverage), D1 (restore script + `cip-requirements-alignment-20261118.md:54,80`).

## 7. D1 reader restore — STOPPED (16:40 SAST)

Warren (16:40): the readers were deleted on purpose; the **discovery tool** is meant to find each customer's website and listings. D1 was stopped during its first step (the pre-change `pg_dump`). **Nothing was changed on `cip`**, no clone was created, `restore_listing_site_readers.py` was never run (not on a clone, not on `cip`). The partial dump was deleted. Log: `C:\Users\warren_eliason\cip-apply-logs\20261119-d1-reader-restore\progress.txt`. Section 1.1's "DATA STEP D1" is withdrawn.

## 8. Why discovery has not discovered websites and listings on live

All read-only: SQL on `cip`, a discovery **dry run** (`apply=False`, `SET TRANSACTION READ ONLY`, no network: a fake fetch that answered 404 to every URL), Redis run-state reads, worker logs.

### 8.1 How discovery works (code)

- `apps/api/app/services/listing_capture/discovery.py` `discover_reporting_customers` (line 119), called only from `autoconfig.autoconfigure_sites` (`autoconfig.py:122-200`). That runs from the beat task `listing_capture.autoconfigure_sites` **once a day at 05:20 UTC = 07:20 SAST** (`worker/celery_app.py:48-53`) and from the steward button `POST /listing-capture/sites/autoconfigure` (`endpoints/listing_capture.py:230`).
- **Discovery does not find a customer's website.** The site key comes from the customer's `customer_report_config.feed_profile_json.listing_seed.marketplace`, or else from the customer's existing `customer_listing.marketplace` values (`autoconfig.py:11-14`, `_site_keys`). With neither, the customer gets `no_site_key` and is skipped (`discovery.py` plan loop; `autoconfig.py:425-434`). A domain is recorded only by a steward on **Sites & sellers → "Record the site key and domain for a reporting customer that has neither"** (`ListingSitesLens.tsx:163-182`, `POST /listing-capture/sites/onboard`, `site_onboarding.record_customer_site`).
- For a known site, discovery takes each product with `reported_soh > 0` in the customer's latest sell-through period that has **no listing yet**. It looks for the product's barcode, then its model, using the site's `search_url_pattern`, then a search form on the site's home page, then the site's sitemap (`_search_candidates`, `discovery.py:583-619`). A page is kept only when its barcode or model matches. It proposes a `cst_listing_seed` row (`proposed`); it never creates a listing. At most 25 products per customer/site per run. Fetches share the #95 per-site pacing (`site_fetch`, default 5 s, 403/429 pause in Redis, 10-minute budget).
- No search engine or outside API is used. No search-provider key exists in the code (searched `listing_capture/` and `worker/tasks.py`). The only switches are `CIP_LISTING_LIVE_FETCH` and `CIP_LISTING_CAPTURE_SCHEDULE`; both are on, because the poll fetches live.
- The reader for a site (`adapter_key`) is set automatically only to the general HTML reader. That happens after a page whose barcode or model matches the product (`discovery.py` docstring; `autoconfig` probe). Nothing sets the JSON reader (`adapters/rest_buybox.py`) automatically.

### 8.2 Has it ever run on live? **No.**

- The discovery code for reporting customers (`d2723d8a` 16 Nov, `a0c7dcc5`, `c5a4a991` shared pacing, `ead229f5`/`da478da7` 18 Nov) is **not** in `f691c44d`, the code live ran until the 15:56 restart today (`git merge-base --is-ancestor` = false for all five). The 07:20 runs on 17, 18 and 19 Nov ran the older autoconfigure. They finished in 0.5–1.0 s (`worker.err.log.1`), and Redis has **no** discovery run record for `cip` (`cip:listing_capture:last_run:cip:` holds only `autoconfigure:default` and `poll`; all 333 discovery keys belong to `cip_test` test tenants).
- **First scheduled run with the new code: 20 Nov 07:20 SAST**, unless a steward presses "autoconfigure" on Sites & sellers first.
- Output on `cip` so far: `cst_listing_seed` holds 281 rows, all from sell-through feeds, none from discovery: takealot 79 confirmed, evetech 88 confirmed + 63 proposed (11 Aug), amazon 51 confirmed (9 Aug). `listing_link` 0 rows, `listing_link_queue` 0, `site_candidate` 0, `platform_audit_event` with a site or listing action: 0.

### 8.3 What blocks each reporting customer (dry run of the live code, no network)

| Customer | Seed on cip | Dry-run result | Blocker | Class |
|---|---|---|---|---|
| Hifi (11) | none | `no_site_key` | no site key or domain recorded; discovery cannot find the website itself | DATA STEP (steward records the domain on Sites & sellers) + NOT BUILT (if Warren wants CIP to find the website by itself) |
| Incredible Connection (12) | none | `no_site_key` | same | same |
| Makro (15) | none | `no_site_key` | same | same |
| Computer Mania (18) | none | `no_site_key` | same | same |
| Game (57) | none | `no_site_key` | same | same |
| Takealot (20) | marketplace + page patterns, no search URL | `reader_not_configured`; 18 stocked products, **all 18 already have a listing** → nothing to discover | Its 79 listings are unread because `adapter_key` is empty. The daily probe fetches a product page (HTTP 200) but finds no barcode or model in the HTML (`no_barcode_or_model_match`, Redis autoconfigure record 19 Nov 05:20 UTC), so it never sets the HTML reader. Nothing derives the JSON reader. | NOT BUILT (reader for a site whose product page is built in the browser) |
| Amazon (299) | marketplace + page patterns, no search URL | `no_search_url`; 0 watched; would fetch the home page and `sitemap.xml` (14 requests in the dry run) | All **51 amazon listings have no `product_id`** (probe: `no_listing_with_product_and_url`), so the probe has nothing to check. Discovery can only use the home-page search form or the sitemap; whether Amazon answers a script is unknown until the first live run. | DATA STEP (link the 51 listings to products) + likely NOT BUILT (search on a site that blocks scripts) |
| Evetech (52) | marketplace + page patterns | 34 stocked products, all watched; reader `html_page` set | none: working | MATCHES |

### 8.4 What would make discovery work (no code changed here)

1. **Run it once on live now** (DATA STEP; authorised as a job run): Sites & sellers → autoconfigure, or the beat task with `on_demand=True`. It writes `cst_listing_seed` proposals only, plus Redis run records. On today's data it will propose little: Takealot and Evetech are fully watched, and the other 5 have no site key.
2. **Record the 5 websites** (DATA STEP, steward screen exists): site key + domain for Hifi, Incredible Connection, Makro, Computer Mania, Game. Warren chose "watch all five sites". The domains are customer data and must come from Warren or the steward. Discovery then searches each one on its next run.
3. **NOT BUILT, needs a decision:** (a) automatic website finding for a customer (there is no search provider; it would need one, e.g. a web-search API key, or a rule using the customer's e-mail domain); (b) a reader for sites whose product page is built in the browser (Takealot), because the HTML probe can never match there; (c) Amazon product links for its 51 listings, and a way to search Amazon.

## 9. Signed-in screen audit — all 56 routes (16:53–17:33 SAST)

**Method.** Playwright (`C:\Users\warren_eliason\terminals\screen_audit_20261119.cjs`), signed in to `http://localhost:3000` as the local admin through the normal login form (login HTTP 200; the password is not written anywhere in this repo or log). For each route: wait for network idle (45 s cap, 120 s for `/listing-capture`), +1.5 s, then a full-page shot at **1280x800** and at **390x844** (device scale 2, so files are 2560/780 px wide), plus the page text. **112 screenshots + `results.json`** are on Warren's PC in `C:\Users\warren_eliason\terminals\screens-20261119\` (not committed: binary, several are 50k–185k px tall). SQL below read-only on `cip` (`current_database()` = `cip`, `default_transaction_read_only=on`).

**Limits of this pass.** (1) Most shells scroll inside `main`, so a "full-page" shot is often just the viewport (1688 px tall at 390). (2) The page text was read once, at the 1280 pass; some panels were still loading then (e.g. `/brief` text said "No start actions" while its 390 shot, taken seconds later, shows the admin start cards). Where text and screenshot disagree, the screenshot is the evidence. (3) No 390 page overflows sideways: every 390 shot is exactly 390 CSS px wide.

### 9.1 Per-route classification

| Area | Route | Real data on live? | Class |
|---|---|---|---|
| Overview | `/brief` | Start cards for admin, signals load late; "No tenant dashboard yet" (none published) | MATCHES |
| Overview | `/dashboards` | 6 signals, widget builder, 3 saved dashboards | MATCHES |
| Overview | `/reports` | Builder works; inbox counters still "Loading…" at capture | MATCHES (slow counters, see 9.3 T1) |
| Overview | `/inbox` | Weekly WoC deliveries to 16 Nov; shipping digests from 29 Oct | MATCHES |
| Stock | `/stock`, `?lens=cover` | SOH 59,955 units, 2,481 pairs, cover 21.8 w, as of 29 Oct | MATCHES (data age: last import 29 Oct, see N1) |
| Stock | `?lens=movement` | Sell-out W29–W41, shipped-in to W44 | MATCHES (sell-out stops W41, N1) |
| Stock | `/channel-intelligence` | Customer sell-through KPIs, down 38% YoY | MATCHES |
| Stock | `/stock/replenishment` (Stores and DCs, store map) | No store has coordinates | NOT BUILT — known item 1.2 |
| Stock | `?lens=execution` | 26Q3 plan 32,509 vs shipped 10,493 (32%) | MATCHES |
| Stock | `/forecasts` | "Forecasts need 8 weeks of applied sell-out… covers 2 of 8 weeks. Latest sell-out is W41 (2026-10-09)" | **DATA STEP — N2** |
| Supply | `/supply`, `/supply/shipments` | 948 open, 171 past ETA, US$34.3m pipeline | MATCHES |
| Supply | `/admin/shipment-evidence`, `/admin/po-management` | Evidence lines; 335 protected PO links | MATCHES (po-management 390 page is 38k CSS px tall, N10) |
| Planning | `/lineup`, `/lineup/cases` | 1,647 plan lines / 1,646 pending for everyone | CODE BUG + DATA STEP — known item 1.3 |
| Planning | `/lineup/new-customer` | Customer list = exactly the 8 "Reports expected" customers | MATCHES (#122) |
| Planning | `/commercial-planner` | "No plans yet" — 0 plans created, 29 lineups listed | MATCHES (empty by use) |
| Planning | `/roadmap` | "No roadmap rows"; `fact_product_roadmap` = 0 | **DATA STEP — N5** |
| Planning | `/pricing` | "No recorded prices" | **DATA STEP — N6** |
| Promotions | `/commercial-planner/cpor-cases` (Budget ledger / Case book) | Book R4.4m, 74 ended, 210 settled | MATCHES |
| Promotions | `/promotions` | KPIs, 0 in planning, 75 at-risk | WRONG RULE + NOT BUILT — known item 1.4 |
| Promotions | `/promotions/timeline` | Empty until a customer is chosen | MATCHES (as built; mock-up wants the timeline on the planner itself, L3) |
| Promotions | `.../claims`, `.../payment-evidence-import`, `.../historical-import` | 304 plans via historical import, 1 template | MATCHES |
| Promotions | `/admin/customer-commercial-terms` | "No customer commercial terms yet" | **DATA STEP — N7** (moot if planner is sell-through only) |
| Promotions | `/budgets` | Ledger renders | MATCHES |
| Market | `/listing-capture` registry / observations / intelligence / proposals / quality | 218 listings, 148,989–163,716 readings; screen shows 0 while the 90 s call runs; amazon/takealot "Not configured"; "Sites ready 1 of 3" | CODE BUG + NOT BUILT — known item 1.1 and section 8 |
| Market | `/competition?tab=mappings`, `?tab=prices` | 0 mappings, 0 prices; `dim_competitor_product` = 0 | **DATA STEP — N3** |
| Market | `/competition?tab=competitor-listings` | Labelled "planned — nothing here works yet" (BACKLOG §9.9) | **NOT BUILT — N4** |
| Data | `/admin/imports` (+ CST template) | 201 completed jobs; **0 in the last 7 days; last import 29 Oct 14:05** | MATCHES (screen) — data age is N1 |
| Data | `/admin/mappings`, `/admin/masters`, `/admin/products`, `/admin/product-master-gaps`, `/admin/customers` (+ duplicates), `/admin/distributors` (+ duplicates), `/admin/channels-regions`, `/admin/cst-steward`, `/admin/steward-audit` | 3,264 candidates, 18,157 products, 1,697 gap tokens, real masters | MATCHES |
| Admin | `/admin/users/list`, `/admin/sql-viewer`, `/admin/audit-log`, `/settings` | 3 users, audit rows, settings | MATCHES |
| Admin | `/admin/ops` | "Services degraded — tunnel blocked" (outbound 7844 blocked on this network since 08:54) | MATCHES (reports the real state; network, not CIP) |
| Admin | `/admin/port-conditions` | "No figures entered yet"; `port_condition` = 0 | **DATA STEP — N8** (hand-entered by design) |

Route totals (56): **MATCHES 39** · known four items 9 routes · new non-matching 8 routes.

### 9.2 New findings beyond the four known

| # | Finding | Evidence | Class |
|---|---|---|---|
| N1 | **Sales data on live is old.** No import of any kind since **29 Oct 14:05**. Distributor sell-out (`fact_sales_sellout`, 58,128 rows) ends **9 Oct 2026 (W41)**. Customer sell-through (`fact_customer_sellthrough`, 20,546 rows) ends per customer as in section 2: Amazon 12 Oct; Takealot/Evetech 27 Jul; Game/Makro/Computer Mania 29 Jun; Hifi/IC Jun 2025. | `import_job` max(created_at) = 2026-10-29 14:05 +02; 0 jobs in 7 days | DATA STEP (load newer files) + **decision** (Q1 below): a sell-through-only planner will plan off data 1–5 months old |
| N2 | Forecasts page cannot forecast | needs 8 weeks of applied sell-out, has 2; 66,627 `fact_demand_forecast` rows kept as workspace only | DATA STEP (same root as N1) |
| N3 | Competition empty | `dim_competitor_product` 0, `fact_competitor_mapping` 0, `fact_competitor_price` 0 | DATA STEP (no competitor data ever loaded) |
| N4 | Competitor listings tab is a placeholder | page says "planned … nothing here works yet" | NOT BUILT (BACKLOG §9.9) |
| N5 | Product roadmap empty | `fact_product_roadmap` 0 | DATA STEP |
| N6 | Recorded prices empty | screen "No recorded prices" | DATA STEP (moot for a sell-through-only planner) |
| N7 | Customer commercial terms empty | screen "No customer commercial terms yet" | DATA STEP (moot for a sell-through-only planner) |
| N8 | Port delay figures empty | `port_condition` 0 | DATA STEP (manual by design) |
| N9 | **Counts show 0 while loading** instead of a placeholder: Market header "0 monitored listings · 0 observations" on the observations tab; Promotions header "0 ended" at 390 while the 1280 pass shows 74 ended. This is what Warren read as "no listings". | `results.json` text for `/listing-capture?tab=observations`; `promotions__390.png` vs `promotions__1280.png` | CODE BUG (UI: show "…" until loaded; goes with lane L1, plus `PromotionPlannerSurface.tsx` header in L3) |
| N10 | Mobile: whole tables rendered unpaged — `/lineup/cases` 390 shot is 185,524 px (≈92,800 CSS px) tall, `/admin/po-management` 76,052 px (≈38,000 CSS px) | screenshot sizes | CODE BUG (paging/virtualise at 390; lineup part goes with L2) |

### 9.3 To check (not classified yet)

- T1: nine routes never reached network idle within 45 s (`/dashboards`, `/stock?lens=execution`, `/admin/po-management`, `/lineup/cases`, `/commercial-planner`, `/roadmap`, the 3 `/competition` tabs) and `/reports` counters still said "Loading…". Either a slow API call or a poller that never stops. Needs the API log timings per call before it can be called a CODE BUG.

### 9.4 Counts per class (findings across sections 1, 8 and 9)

| Class | Count | Items |
|---|---|---|
| MATCHES | 39 routes | 9.1 |
| CODE BUG | 5 | listings 90 s intelligence read; header = page size; line-ups list/reserve ignore "Reports expected"; N9 zero-while-loading; N10 mobile paging |
| DATA STEP | 11 | delete 1,470 old drafts (decided); run discovery once; record 5 customer websites; link 51 Amazon listings to products; N1 newer sales files; N2; N3; N5; N6; N7; N8 |
| NOT BUILT | 5 | store pins offline matching + steward confirm (decided); planner layout vs mock-up; automatic website finding; reader for browser-built pages (Takealot) / Amazon search; N4 competitor listings |
| WRONG RULE | 1 | planner uses 10 non-sell-through sources incl. PR #96 price rule (decided: strict sell-through) |
| To check | 1 | T1 |

### 9.5 Decisions still needed from Warren

1. **Old sales data vs sell-through only (new).** Newest customer sell-through is 12 Oct (Amazon) and 27 Jul or older for everyone else; nothing imported since 29 Oct. Options: (a) load the missing customer files, then build the sell-through-only planner; (b) build it now and let it show "data as of <date>" per customer; (c) also count distributor sell-out (newest 9 Oct) as sell-through.
2. **Hifi / Incredible Connection week 24 files:** 2025 or 2026? (still open from the first round).
3. **The 5 websites:** (a) Warren/steward gives the website for Hifi, Incredible Connection, Makro, Computer Mania, Game and CIP's discovery takes it from there; (b) build automatic website finding (needs a web-search API key, or a rule from the customer's e-mail domain).
4. **Takealot (79 listings unread since 4 Nov):** its product page is built in the browser, so the page reader can never match. Options: (a) build a browser-based reader (heavier, runs a headless browser); (b) a reader for the site's JSON data; (c) stop watching Takealot.
5. **Amazon (51 listings, none linked to a product):** (a) steward links them, then discovery checks them; (b) stop watching Amazon.
6. **Empty pricing / commercial terms / competitor data:** with a sell-through-only planner, should these screens stay (for later use) or be hidden?
