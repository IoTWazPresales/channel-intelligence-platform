# Live screen audit — 2026-11-19 (SAST)

Live app `http://localhost:3000` on RF2300014-NB3, main checkout at `22beb215` (`feat/integrate-20261103`), live DB `cip`.
Every SQL figure below was read from `cip` in a read-only psql session (`default_transaction_read_only=on`, `current_database()` printed = `cip`), between 16:20 and 16:45 SAST. No code, config or data was changed.

## STATUS OF THIS AUDIT — screenshots BLOCKED on a sign-in

The live app runs `CIP_AUTH_MODE=session` (`apps/api/.env`). The repo's Playwright specs that sign in (`apps/web/e2e/builder-auth.spec.ts`, `e4-saved-query-auth.spec.ts`) use `CIP_BUILDER_TEST_API` + `CIP_BUILDER_TEST_TOKEN` against a **test** API; neither variable is set on this PC and there is no dev-login route or seeded smoke user for live. `.cursor/rules/smoke-via-browser.mdc` requires a browser session but names no credential.
**So no route was screenshotted.** Needed from Warren, once: a login for the live app (or a viewer/steward account made for the audit). Then every route in section 3 gets 1280x800 and 390x844 full-page shots under `docs/audits/screens-20261119/`.

Sections 1–2 (the four items Warren found + the Reports strip) are proven from code and live data, without screenshots.

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

## 3. Route list (from `apps/web/src/features/shell/navConfig.ts`) — screenshots pending login

Overview: `/brief` · Business dashboard `/dashboards` · Reports `/reports` · Report inbox `/inbox`
Stock & Sell-through: `/stock`, `/stock?lens=cover`, `/stock?lens=movement`, `/channel-intelligence`, `/stock/replenishment`, `/stock?lens=execution`, `/forecasts`
Supply & Inbound: `/supply`, `/supply/shipments`, `/admin/shipment-evidence`, `/admin/po-management`
Planning: `/lineup`, `/lineup/cases`, `/commercial-planner`, `/roadmap`, `/pricing`
Promotions & Funding: `/commercial-planner/cpor-cases`, `/promotions`, `/promotions/timeline`, `/commercial-planner/cpor-cases/claims`, `/commercial-planner/cpor-cases/payment-evidence-import`, `/commercial-planner/cpor-cases/historical-import`, `/admin/customer-commercial-terms`, `/budgets`
Market & Listings: `/listing-capture` (tabs registry, observations, intelligence, proposals, quality[planned]), `/competition?tab=mappings`, `/competition?tab=prices`, `/competition?tab=competitor-listings` [planned]
Data & Stewardship: `/admin/imports`, `/admin/imports?template=customer_sell_through`, `/admin/mappings`, `/admin/masters`, `/admin/products`, `/admin/product-master-gaps`, `/admin/customers`, `/admin/customers/duplicates?tab=name_similarity`, `/admin/distributors`, `/admin/distributors/duplicates`, `/admin/channels-regions`, `/admin/cst-steward`, `/admin/steward-audit`
Administration: `/admin/users/list`, `/admin/ops`, `/admin/sql-viewer`, `/admin/port-conditions`, `/admin/audit-log`, `/settings`
Also linked: `/lineup/new-customer`, `/sell-out` (→ `/stock?lens=movement`).

Per-route status: **NOT YET AUDITED** — awaits a live login (screens + compare + classify).

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
