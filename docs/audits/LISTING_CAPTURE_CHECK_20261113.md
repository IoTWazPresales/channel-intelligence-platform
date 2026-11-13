# Listing capture check, 2026-11-13

Lane W1-D0 (read-only). Branch `docs/w1d-listing-capture-check-20261113` from trunk `feat/integrate-20261103` @ `4d2ff66a`.
No product code, config or data changed. Read-only SQL ran on `cip` through the lane helper (`db_ro.py`: it prints the masked URL and
`current_database()`, then runs each statement in a READ ONLY transaction and rolls it back). Every query below printed
`current_database(): cip`. Times are SAST (+02:00) unless marked UTC.

Labels: **VERIFIED** means the output was seen in this session. **ASSERTED** means inference or something not re-run.

---

## Q1. Why did listing polling stop?

### Answer (short)

Polling did not stop because of the scheduler, the env flags or a site pause. Beat enqueues the poll every 30 minutes, the
tasks succeed, and both env switches are set on the worker. Polling stopped because **no site had a configured page reader**.

- Commit `3ea6cce4` (2026-11-03, "listing: learn product links and plan on the buy-box price") moved the page readers, link
  patterns and seller names out of code (`takealot_fetch.py` was deleted, including `TAKEALOT_API_ORIGIN = "https://api.takealot.com"`)
  and into the tenant table `listing_site`.
- Its migration `20261103_0053` backfills one `listing_site` row per marketplace **with `adapter_key` NULL, on purpose**. The
  migration docstring says: "The link patterns and sellers that used to be code constants are not copied: a site with no reader is
  'not configured' and is not fetched until a steward fills it in."
- `poll_active_listings` skips every listing whose site has no configured reader, without a request and without a row
  (`registry.py:1007-1016`, `configured_adapter` in `adapters/__init__.py:128-132`).
- Once the worker restarted on the new code (between 00:34 and 01:00 on 2026-11-04), every listing on every site was skipped.
  No observation was stored for any site until 2026-11-12 07:30.
- The daily autoconfigure task first ran on 2026-11-12 at 07:20. It gave **evetech** the `html_page` reader (its probe
  corroborated a stored page). **amazon** and **takealot** still have no reader, so they have been skipped on every poll since.
  Their last observation is 2026-11-04 00:33.

**Single root cause (VERIFIED in code and data): a data gap that a code change created.** The site-as-data refactor
(`3ea6cce4` plus migration 0053) shipped without migrating the reader configuration it removed from code. Nothing alerts when
due listings are skipped as `not configured`, so the stop was silent for 9 days. It is not a beat or schedule problem, not an
env problem and not a site pause.

### Evidence

**Last observations per site (VERIFIED)**

```sql
select l.marketplace, count(distinct l.id) listings, count(o.id) obs, max(o.fetched_at) last_obs,
       max(o.fetched_at) filter (where o.parse_status='ok') last_ok
from customer_listing l left join listing_observation o on o.listing_id=l.id group by l.marketplace order by 1
```
```
marketplace | listings | obs   | last_obs                         | last_ok
amazon      | 51       | 42217 | 2026-11-04 00:33:01.247914+02:00 | 2026-11-04 00:32:50.487237+02:00
evetech     | 88       | 75470 | 2026-11-13 02:01:11.706958+02:00 | 2026-11-13 02:01:11.706958+02:00
takealot    | 79       | 23040 | 2026-11-04 00:33:51.792519+02:00 | 2026-11-04 00:33:51.792519+02:00
```
At 2026-11-13 07:01 a re-read gave the same amazon and takealot values; evetech's last observation was 07:01:07.

**Observations per site and day (VERIFIED):** there are none from 2026-11-04 00:34 to 2026-11-12 07:30 for any site. From
2026-11-12 07:30 there are evetech rows only.
```
2026-11-13 | evetech  | 377  | 00:00:00 .. 02:01:57
2026-11-12 | evetech  | 2554 | 07:30:00 .. 23:36:16
2026-11-04 | amazon   | 102  | 00:00:20 .. 00:33:01
2026-11-04 | evetech  | 176  | 00:00:21 .. 00:34:04
2026-11-04 | takealot | 74   | 00:02:17 .. 00:33:51
2026-11-03 | amazon 2040 / evetech 3520 / takealot 1522 (full day)
```

**Tasks kept running and succeeding the whole time (VERIFIED, `task_run` ledger)**

```sql
select date_trunc('day', created_at) d, task_name, state, count(*) from task_run
where created_at > '2026-11-03' and task_name like 'listing_capture%' group by 1,2,3 order by 1,2,3
```
`listing_capture.poll_listings` has `succeeded` rows every day from 11-03 to 11-13: 1760, 129, 37, 38, 13, 29, 37, 26, 538, 90.
There are no `failed` rows. 2026-11-08 has no task rows at all, so the stack was down that day (ASSERTED). The first
`listing_capture.autoconfigure_sites` row is on 2026-11-12.

**The moment the behaviour changed (VERIFIED)**

```sql
select date_trunc('hour', created_at) h, count(*), round(avg(extract(epoch from finished_at-started_at))::numeric,2) avg_s
from task_run where task_name='listing_capture.poll_listings'
  and created_at between '2026-11-03 22:00+02' and '2026-11-04 12:00+02' group by 1 order by 1
```
```
2026-11-03 22:00 | 44 | 6.78
2026-11-03 23:00 | 88 | 6.30
2026-11-04 00:00 | 88 | 5.71
2026-11-04 01:00 | 2  | 0.90   <- from here: one task per run, under a second, no fetch
2026-11-04 02:00 | 2  | 0.36
...
2026-11-04 11:00 | 2  | 0.29
```
The poll runs about 5 listings per task and queues the next batch (`tasks.py:949-963`, `LISTING_POLL_BATCH_SIZE = 5`,
`registry.py:1120`). From 01:00 a run is one task with nothing to fetch, which is what `poll_active_listings` does when every due
listing is `skipped_not_configured`. The restart onto the new code is ASSERTED; the change in task shape is VERIFIED.

**Site rows (VERIFIED, re-read at 2026-11-13 07:01)**

```sql
select id, tenant_id, site_key, adapter_key, product_url_pattern is not null pup, page_id_pattern is not null pip,
       search_url_pattern is not null sup, details_url_pattern is not null dup, first_party_seller is not null fps,
       rate_limit_seconds, is_active, updated_by, updated_at from listing_site order by id
```
```
1 | default | amazon   | (none)    | pup t | pip t | sup f | dup f | fps f | rate null | active | listing-autoconfigure | 2026-11-12 07:20
2 | default | takealot | (none)    | pup t | pip t | sup f | dup f | fps f | rate null | active | listing-autoconfigure | 2026-11-12 07:20
3 | default | evetech  | html_page | pup t | pip t | sup f | dup f | fps f | rate null | active | listing-autoconfigure | 2026-11-12 07:20
```
All three rows have `created_at = 2026-11-03 23:19:38`, which is when migration 0053 ran on `cip`. `alembic_version` is
`20261110_0061`. `listing_site_seller` has 0 rows.

**The worker's own run record (VERIFIED, `worker.err.log` read through `cip-supervisor-status.ps1 -LogFile worker.err.log -Log 3000`)**
```
[2026-11-13 00:06:25,593: INFO/MainProcess] listing capture poll: {'polled': 88, 'failed': 0, 'listing_count': 88, 'skipped_backoff': 0,
 'skipped_paused': {}, 'skipped_not_configured': {'takealot': 79, 'amazon': 51}, 'paused_sites': {}, 'stopped_reason': None, 'duration_seconds': 382.923}
```
The 00:36, 01:06 and 01:36 runs show the same record.

**Scheduler and env (VERIFIED in code; the env values themselves are ASSERTED)**

- Beat entries: `celery_app.py:50-58` has `listing-capture-autoconfigure` at `crontab(hour=5, minute=20)` (05:20 UTC = 07:20 SAST)
  and `listing-capture-poll` at `crontab(minute="*/30")`. Snapshot retention is at 03:15 UTC.
- `celery_app.py:83-86`: when `dev_beat_disabled()` is true, the beat schedule is `{}`. On Windows with a solo pool it is true
  unless `CIP_ENABLE_DEV_BEAT=1` (`celery_queues.py:76-86`).
- Gates in the poll task (`tasks.py:927-937`): `dev_beat_disabled`, then `scheduler_should_run` (`CIP_LISTING_CAPTURE_SCHEDULE`
  truthy and at least one listing, `registry.py:812-817`), then `CIP_LISTING_LIVE_FETCH` (`observation.py:184-192`). Autoconfigure
  uses `CIP_LISTING_LIVE_FETCH` for its probe (`autoconfig.py:103-109`, `:390-393`).
- The supervisor starts the worker with `CIP_ENABLE_DEV_BEAT=1`, `CIP_LISTING_CAPTURE_SCHEDULE=1`, `CIP_LISTING_LIVE_FETCH=1`
  and a beat schedule file under its state folder (`scripts/cip-supervisor.ps1:58`, `:563-568`).
- Supervisor status (VERIFIED, 02:00:20): `env CIP_LISTING_LIVE_FETCH present=True CIP_LISTING_CAPTURE_SCHEDULE present=True`;
  `worker healthy ... worker=1 beat=1`.
- The poll records above prove all three gates pass: had any gate failed, the task would return `skipped` before polling, and it
  polled 88 evetech listings.
- `celery inspect` was not run: the ledger and the worker log already show enqueue and success, so it was not needed.

**Pause (VERIFIED from the run record):** `skipped_paused: {}` and `paused_sites: {}` on every logged run, so no site is paused.
Dead-link back-off is `skipped_backoff: 0`.

**Regression commit (VERIFIED)**

`git -C <WT> log --format="%h %ad %s" -- apps/api/app/services/listing_capture/adapters apps/api/app/worker/celery_app.py apps/api/alembic/versions/20261103_0053_listing_sites_links_offers.py`
```
000e1e1d 2026-11-12 listing-capture: decide the page-named seller per reading customer on shared sites
9ba66022 2026-11-12 listing-capture: keep stored seller identities and per-customer sellers in autoconfig
a0f672ab 2026-11-11 listings: keep an existing own seller and honest coverage counts
28eda97c 2026-11-11 listings: fill the own seller and add the coverage tab
d5f78d0e 2026-11-06 listing-capture: autoconfigure reporting-customer sites (#54)
3ea6cce4 2026-11-03 listing: learn product links and plan on the buy-box price   <- behaviour change
```
`git show --stat 3ea6cce4` shows `takealot_fetch.py | 260 -----------` deleted and `auto_finder.py` deleted. It adds
`adapters/{__init__,html_page,rest_buybox}.py`, `sites.py` and migration `20261103_0053`. The schedule file has not changed since
`26e583c2` (2026-10-23).

**Why autoconfigure did not fix amazon or takealot (VERIFIED in code; the probe outcome is ASSERTED)**

`_fill_fields` (`autoconfig.py:414-449`) sets `adapter_key` in only two cases:
- (a) the live HTML probe corroborates a stored page by barcode or model (`_html_probe`, `:378-411`); or
- (b) the customer's seed names `site.adapter_key` **and** every required field for that reader would then be filled
  (`_configured_after`).

The seeds for customers 20 and 299 (see Q2) carry only `page_id_pattern` and `product_url_pattern`. They have no `adapter_key`
and no `details_url_pattern`, so (b) cannot fire. (a) did not fire for those sites: the probe may have got a non-200 response,
a bot page or no barcode/model match. The probe result is not logged, so this part is ASSERTED. The buy-box reader also needs
`details_url_pattern` (`rest_buybox.py:31`), which was the deleted code constant.

### Side finding: evetech has a reader but no seller identity (VERIFIED data; cause ASSERTED)

`listing_site_seller` has 0 rows and evetech's `first_party_seller` is NULL. As a result, `listing_offer.is_own_seller` is never
set (3,793 offers, 0 with the flag) and `listing_observation.buy_box_own` is never set (0 rows). The seller-fill code (#88,
merged into trunk at `01b08292`, 2026-11-12 11:07) landed **after** the only autoconfigure run (2026-11-12 07:20). The worker
was relaunched around 23:20 on 2026-11-12 (supervisor `launches=2`). Expectation (ASSERTED): the 2026-11-13 07:20 autoconfigure
will write customer 52's seller row on evetech, because `html_page` counts as the customer's own site (`autoconfig.py:510-533`).
At 07:01 it had not run yet.

---

## Q2. Why do the other flagged reporting customers produce no reader and no proposals?

"Flagged" = `customer_report_config.feed_profile_json.listing_seed` is present. That is what autoconfigure (`autoconfig.py:11-13`,
`:590-593`) and the CST import (`cst_d1.py:240-245`, `upsert_cst_listing_seed :265-319`) read. A "reporting customer" is
`customer_report_config.reports_expected = true`. The table below lists every reporting customer: three are flagged and five
are not.

```sql
select c.id, c.name, (r.feed_profile_json ? 'listing_seed') has_seed, r.feed_profile_json->'listing_seed' seed
from customer_report_config r join dim_customer c on c.id=r.customer_id where r.reports_expected order by c.id
```
Seeds (VERIFIED):
- 20 `{'marketplace': 'takealot', 'site': {page_id_pattern, product_url_pattern}, 'external_id_from': 'listing_external_id'}`
- 52 `{'marketplace': 'evetech', 'site': {page_id_pattern, product_url_pattern}, 'external_id_from': 'raw_product_token'}`
- 299 `{'marketplace': 'amazon', 'site': {page_id_pattern, product_url_pattern}, 'external_id_from': 'raw_product_token'}`
- 11, 12, 15, 18, 57: no seed.

None of the seeds has `adapter_key`, `details_url_pattern`, `search_url_pattern` or seller names/ids.

Per-customer counts (VERIFIED):
```sql
-- reported_products = distinct product in fact_customer_sellthrough; soh = reported_soh > 0 in any period
-- listings by marketplace; seeds = cst_listing_seed by status; queue = listing_link_queue by status; site_candidate rows
```
The tenant-wide tables `listing_link` (0 rows) and `listing_link_queue` (0 rows) are empty. `site_candidate` has 0 rows for
every reporting customer: it holds store-site evidence, not web domains.

| id | customer | flagged | site / domain | reader | discovery ran? | reported products (with SOH) | listings (no product link) | proposals (seed `proposed`) | link-queue rows | why no reader / no proposals |
|---|---|---|---|---|---|---|---|---|---|---|
| 20 | Takealot | yes | takealot (seed URL pattern) | none: `adapter_key` NULL | autoconfigure 2026-11-12: no adapter set | 55 (46) | 79 (22) | 0 (79 confirmed) | 0 | The reader config was a code constant deleted in `3ea6cce4`. The seed lacks `adapter_key` and `details_url_pattern`, the probe did not corroborate, and there are no seller names. No new proposals because all 79 feed rows are already confirmed and no new feed rows arrived (last sell-through period 2026-07-27). |
| 52 | Evetech | yes | evetech (seed URL pattern) | `html_page` | yes, probe corroborated 2026-11-12 | 71 (69) | 88 (18) | **63 proposed** (88 confirmed) | 0 | Has a reader and proposals. The 63 proposals wait for a steward. Seller identity is still empty (see Q1 side finding). |
| 299 | AMAZON COMMERCIAL SERVICES (SOUTH AFRICA) | yes | amazon (seed URL pattern) | none: `adapter_key` NULL | autoconfigure 2026-11-12: no adapter set | 119 (38) | 51 (**51**) | 0 (51 confirmed) | 0 | No reader (same cause as 20). All 51 listings have no product, so link learning skips them (`links.py:198-200`, `no_product`) and coverage cannot count them against reported products. No seller names. |
| 11 | Hifi | no | unknown | none | autoconfigure excluded it: `no_site_key` | 51 (15) | 0 | 0 | 0 | No `listing_seed`, no listings, no domain anywhere in the data. Autoconfigure finds no site key (`autoconfig.py:232-243`, `:337-352`). Proposals only come from a seeded CST feed (`cst_d1.py:240-245`). |
| 12 | Incredible Connection | no | unknown | none | excluded, `no_site_key` | 82 (51) | 0 | 0 | 0 | Same as 11. |
| 15 | Makro | no | unknown | none | excluded, `no_site_key` | 46 (21) | 0 | 0 | 0 | Same as 11. |
| 18 | Computer Mania | no | unknown | none | excluded, `no_site_key` | 93 (77) | 0 | 0 | 0 | Same as 11. |
| 57 | Game | no | unknown | none | excluded, `no_site_key` | 16 (7) | 0 | 0 | 0 | Same as 11. |

How "discovery ran?" was established: VERIFIED, there is one `listing_capture.autoconfigure_sites` task row (2026-11-12) and it
left the site rows as shown. Per-customer outcomes (excluded / needs_pattern) are derived from the code paths, not from a logged
report: ASSERTED. The run's log line was not in the 3,000-line log tail.

**Structural reasons (VERIFIED in code):**

1. **No domain discovery exists.** A site key comes only from the seed's `marketplace` or from existing `customer_listing` rows
   (`autoconfig.py:337-352`). A reporting customer without either is excluded with `no_site_key`. No code derives a customer's
   web domain.
2. **No product search exists for products without a listing.** `learn_link` (`links.py:189-290`) and `note_fetch` (`:293-354`)
   start from an existing `CustomerListing`. The barcode search lives only inside the buy-box reader's fetch (`rest_fetch`). No
   job walks "reported product × configured site" to find or propose pages. `learn_link` is called only from the steward endpoint
   (`listing_capture.py:635-641`) and is not scheduled. Both link tables have 0 rows.
3. **Proposals come only from a seeded CST feed.** `upsert_cst_listing_seed` writes `status="proposed"` only when the import row
   has a marketplace (from the seed) and an external id (`cst_d1.py:280-283`). Unseeded customers can never get a proposal.
4. **The buy-box reader is shaped for one retailer's API.** `rest_buybox.py` parses fixed JSON field names (`plid` `:248`,
   `tsin` `:252`, `desktop_href`, `badges.items[type=saving]` `:238-247`). Site data can point it at a URL, but not at another
   site's response shape. Under the no-hardcoding rule this is a defect: the reader is generic by name and specific to one
   retailer by content.

### Data Warren must supply (per customer)

Steward data only, entered on Sites & sellers or in the customer's `listing_seed`. None of it is code.

- **20 Takealot (site `takealot`):**
  - reader `adapter_key = rest_buybox_json`
  - `details_url_pattern`: the product-data endpoint with `{page_id}`; the deleted constant's origin was the retailer's public API host
  - `search_url_pattern` (barcode search), if link learning should find new products
  - the customer's own seller name(s) or id(s) on the site
  - optional request spacing
- **299 Amazon (site `amazon`):**
  - which reader to use; whether `html_page` can read these pages at all is UNKNOWN until a probe corroborates one
  - the customer's seller name(s)/id(s) on the site
  - **product links for the 51 listings**: all have `product_id` NULL
- **52 Evetech:** none required. The seller name is inferred from the customer name at the next autoconfigure (ASSERTED). Warren
  should confirm it, or supply the exact page-shown seller name if it differs. 63 proposals await steward decisions.
- **11 Hifi, 12 Incredible Connection, 15 Makro, 18 Computer Mania, 57 Game:**
  - whether each has a web shop to watch at all
  - if yes, its site key and domain, product URL pattern and page-id pattern (or a few known product URLs to derive them,
    `url_pattern.derive_listing_url_pattern`), and the seller name shown for its own stock
  - and/or a `listing_seed` on its CST feed if its reports carry a product URL or token

---

## Q3. Why are there no stock-based suggestions?

### Answer (short)

No code produces a standalone "in stock at the customer but not listed" or "our price vs competitor price" suggestion list.
The closest logic, `sell_through_causes.attach_causes`, adds listing and price causes only to SKUs already flagged for weak sell-through.
For price comparison, the competitor data is empty and the seller identity that would say whose buy box it is has never been
filled. So nothing can come out of any path today.

### Evidence

- grep over `apps/api/app` and `apps/web/src` for `not_listed|no_listing|missing_listing|unlisted|in_stock_not_listed|price_gap|competitor_price|undercut|listing_gap`
  (VERIFIED). No match is a suggestion generator. The matches are:
  - `sell_through_causes.py:307` `_competitor_prices` and `:397-510` `attach_causes`. Causes `cheaper_elsewhere`, `no_page`,
    `listing_unavailable`, `stock_at_stores`, `competitor_cheaper` are attached only to rows the caller passes in (flagged
    sell-through SKUs). When a product has no listing, the row says `not_checked: "web listing (none registered for this customer)"` (`:461-464`).
  - `promo_plan_builder.py:609` `_approved_competitor_prices`: a planner input, not a suggestion.
  - `competition/propose.py:51` (`competitor_price=None`) and `competition/matching.py`: competitor product mapping.
  - Web `MarketSurface.tsx:150`: `no_listing: 'No product link'` is a CPOR **activation** status for a promotion case, not a
    stock suggestion. `brief_signals.py:404-474` counts the CPOR activation worklist.
  - The design-lab text (`design-lab/surfaces/MarketSurface.tsx:452`) itself says `fact_competitor_price` has no import
    template and no rows.
- Data (VERIFIED):
  ```sql
  select (select count(*) from fact_competitor_price), (select count(*) from fact_competitor_mapping), (select count(*) from listing_offer),
         (select count(*) from listing_offer where is_own_seller is not null), (select count(*) from listing_observation where buy_box_own is not null),
         (select count(*) from listing_observation where buy_box_seller is not null)
  ```
  ```
  competitor_prices 0 | competitor_mappings 0 | offers 3793 | offers_with_own_flag 0 | obs_with_buy_box_own 0 | obs_with_buy_box_seller 0
  ```
  All 3,793 offers are evetech, captured 2026-11-12 07:30 to 2026-11-13 07:00, with 0 distinct seller names.
- The size of the gap a "listed vs in stock" suggestion would expose (VERIFIED). Counts are products with `reported_soh > 0`
  in any period, and how many have no `customer_listing` for that customer:
  ```
  11: 15 / 15   12: 51 / 51   15: 21 / 21   18: 77 / 77   20: 46 / 0   52: 69 / 2   57: 7 / 7   299: 38 / 38
  ```
  For 299, all 38 fall in the gap because its 51 listings have no product link. "Any period" overstates current stock:
  last periods range from 2025-06-09 (11, 12) to 2026-10-12 (299). A builder must use the latest period per customer.

---

## Recommended units

### W1-D: polling defect fix

The root cause is configuration data, not a broken scheduler. So the unit has two halves: a data step only Warren can authorise,
and a code change that stops this failing silently again.

1. **Data (Warren's go; a `cip` write, so not a builder action):** fill `listing_site` for `takealot` and `amazon` from the Q2
   list through Sites & sellers, or the existing site endpoints. Then let the next poll run; do not trigger one by hand.
   Acceptance: `skipped_not_configured` is absent from the next run record, and `max(fetched_at)` advances for both sites.
2. **Code: make a skipped site loud.**
   - Files: `apps/api/app/worker/tasks.py` (`listing_capture_poll_listings_task`, `:901-969`) and
     `apps/api/app/services/listing_capture/registry.py` (`listing_poll_run_record`).
   - When a run finishes with `skipped_not_configured` > 0 for a site that has due listings, log at WARNING with the site keys
     and counts. Put a `not_configured_sites` list on the run record, so the existing capture health
     (`autoconfig.capture_health`, `ListingCaptureHealth.tsx`) and any ops alert can show "N listings not polled for X days".
   - Also give `autoconfigure_sites` a logged per-site outcome with the probe status, so the reason a site stayed unconfigured
     is visible. Today the probe result is dropped (`autoconfig.py:405-411`).
   - No site names in code.
   - Test: `apps/api/tests/test_listing_capture_n0101_polling.py` on cip_test. Fixture: two sites, one configured and one with
     `adapter_key` NULL, each with a due listing. Assert the task's run record lists the unconfigured site with its count. Assert
     a WARNING record via `caplog`. Assert the configured site's listing still gets an observation.
   - Second test in `test_listing_site_autoconfig.py`: a probe that returns 403 records `probe_status=403` on that site's outcome.
3. **Optional, needs a decision:** should a reader-configuration migration in future refuse to apply when it would leave due
   listings unreadable? Record it as a decision for Warren. Do not build it in W1-D.

### W1-B: generic discovery and reader pipeline, proposed listings, stock-based suggestions

What is missing:

1. **Site and domain onboarding for a reporting customer without a seed.** Today `no_site_key` is a dead end. Needed: a steward
   path to attach a site key and domain to a customer, either a seed or a site-candidate row with web evidence. The patterns are
   then derived from a few pasted product URLs (`url_pattern.derive_listing_url_pattern` exists).
2. **Product discovery job.** A scheduled, rate-limited job: for each reporting customer × configured site × reported product
   with no listing and no open or decided queue row, search the site (its `search_url_pattern`, by barcode, then model). Write
   `listing_link_queue` rows with candidates, or confirmed `listing_link` rows when corroborated by barcode or model, reusing
   `identity.corroboration`. Today link learning starts only from an existing listing and runs only on demand.
3. **Proposed listings from discovery.** A confirmed link for a customer and product should propose a `customer_listing`. It
   should follow the same proposal and confirm flow as `cst_listing_seed`, not only feed rows. Also needed: a backfill step
   that links the 51 product-less amazon listings (and 22 + 18 others) to products, by corroborated page or by steward.
4. **Generic structured reader.** The buy-box JSON reader must take its field paths (page id, variant id, price, availability,
   seller, badge) from site data, or a named reader profile stored as data. **Defect under the no-hardcoding rule:**
   `rest_buybox.py:238-255` reads one retailer's response field names (`plid`, `tsin`, `desktop_href`, `badges.items[type=saving]`).
5. **Seller identity per customer per site** is still empty (0 rows). Discovery must keep the existing rule: seed or steward
   first, customer name inferred only on the customer's own site. Seller names Warren supplies (Q2 list) go into
   `listing_site_seller`, never into code.
6. **Stock-based suggestions (new read model; no code computes them today).** Per tenant, scoped to My-accounts like
   `brief_signals`:
   - (a) **In stock, not listed:** a product with `reported_soh > 0` in the customer's **latest** reported period, and no
     watched listing on any configured site of that customer.
   - (b) **Our price vs competitor:** for watched listings, own price (own seller on the buy box) vs the best other offer from
     `listing_offer`, plus `fact_competitor_price` once it has an import.
   - Each suggestion carries its evidence (period, SOH, listing, observation time). With no data it says "not checked", as
     `attach_causes` does.
   - It reuses `sell_through_causes` helpers rather than duplicating price logic.
   - (b) depends on item 5 and on `fact_competitor_price` getting an import template (currently 0 rows; no template).

Today nothing is keyed to a named retailer or customer in the listing-capture services, **except the buy-box reader's response
shape (item 4)**. Elsewhere in the API, `cst_p4_customer_bootstrap.py` (ids fixed by Q-004) and `customer_leftover_repair.py:31`
name customers. They are outside listing capture and out of scope here, but are noted for the no-hardcoding sweep.

---

## Commands run (all read-only)

- `git -C <WT> branch --show-current`, `git -C <WT> status --porcelain`, `git -C <WT> log ...` (as above),
  `git -C <WT> show --stat 3ea6cce4 -- ...`, `git -C <WT> show 3ea6cce4 -- .../takealot_fetch.py` (grep for URL constants).
- `scripts/cip-supervisor-status.ps1` (status) and `-LogFile worker.err.log -Log 3000`; the output went to `<WT>/apps/api/.tmp/`.
- `db_ro.py -` with the SELECTs quoted above. One SELECT failed on a wrong column name (`week_end`) and was re-run with
  `period_start_date`. Nothing was written.
- Not run: `celery inspect` (not needed; the evidence above is direct). No restart, no capture trigger, no write to `cip`.
