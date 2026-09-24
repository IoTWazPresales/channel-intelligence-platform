# N-0039 implementation: listing links open the real product page

Implementation run (moment c), lenses: backend-engineer, frontend-engineer, test-engineering-specialist.
This run picked up where an earlier implementer was cut off by a usage limit. That implementer left uncommitted, unreviewed work. This run reviewed all of it, kept what was right, fixed one real defect (below) and finished the rest. Self-check only. GOV-008 verification still has to happen in a separate run.

## Review of the inherited work
- Kept: the `auto_finder` fix, `takealot_product_url`, the confirm guard, the write-back and dead-link rules, `listing_url_verified_at`, the `ListingUrl` UI and all the tests. They matched DISCOVERY.md and passed.
- **Defect found and fixed: a unique-key collision.** `uq_customer_listing_customer_url` is unique on (customer_id, url). On cip, listings 69 and 73 are two report SKUs (234076925 and 234153078) for the same product (6059) and customer (20), and both resolve to PLID101365041.
  - The inherited repair script crashed with `UniqueViolation` (id 73 -> PLID101365041 URL already held by 69) on its first scratch dry run, before this fix.
  - The inherited runtime write-back had the same problem: it would have raised at `session.flush()` during a poll.
  - Fix, in both places: if another listing of the same customer already holds the resolved URL, the URL is not rewritten and not stamped verified. `meta_json.url_conflict_listing_id` records the holder, and the lower id keeps the URL. Nothing is merged. See Q1.
- Changed the tooltip on "Unverified link" to "Not yet confirmed to open the product page.". The inherited text talked about marketplace APIs, which is wrong for Amazon and Evetech rows.

## Criteria

| # | Result | Evidence |
|---|---|---|
| 1 | PASS | `auto_finder.py:25` `_PLID_RE` now needs an explicit `PLID` prefix, so bare digits (the report SKU) give no URL. `auto_finder.py:29` `takealot_product_url` builds `/x/PLID<n>`, or uses the canonical slug URL only when it ends in the same PLID; a bare `/PLID<n>` canonical is rejected. `registry.py:229` makes `confirm_suggested_proposals` skip any Takealot seed whose URL has no extractable PLID (`takealot_plid_unresolved`). Tests: `test_listing_auto_finder.py`, including `test_takealot_sku_never_yields_plid_sku_url` (4 SKUs), `test_takealot_known_plid_yields_product_page_shape`, `test_confirm_suggested_proposals_skips_takealot_sku_seeds` and `..._guards_takealot_without_plid`. |
| 2 | PASS | `registry.py:271` `_write_back_verified_url`, called from `record_observation`. It runs only for a Takealot fetch that has `plid_source`, no fetch reason, parse ok and a `resolved_plid`. It sets `url` to the canonical URL or `/x/PLID<n>`. `meta_json.original_url` is set once and never overwritten; `meta_json.url_verified_at` is the fetch time. Tests: `test_record_observation_writes_back_canonical_url_and_keeps_original`, `..._known_plid_rewrites_sku_url_without_canonical`, `..._original_url_preserved_across_rewrites`, `..._uncorroborated_ean_hit_does_not_rewrite`, `..._url_conflict_does_not_rewrite_or_verify` (new). |
| 3 | PASS | `takealot_fetch.py:210` records `details_status`, the REST status for the URL's or known PLID. `registry.py:453`: Takealot is marked `dead_link` when `details_status` is 404/410 **and** the reason is `plid_not_found` or `ean_not_unique_or_missing`, or, as before, when a resolved PLID itself 404s. The row and its URL are kept (observed, never deleted). The 3-strike `should_backoff_dead_link` is unchanged. Tests: `test_record_observation_rest_404_no_ean_marks_dead_link`, `..._rest_404_ean_search_miss_marks_dead_link`, `..._rest_404_but_ean_resolves_stays_active`, `..._no_plid_no_ean_is_not_dead`, `..._dead_link_backoff_unchanged`. |
| 4 | PASS | `MarketSurface.tsx:202` `listingUrlState` and `:210` `ListingUrl`, used for the detail URL row (`:1503`); an "Original URL" row appears when one exists. An anchor (`target="_blank" rel="noopener noreferrer"`) is rendered only when the state is verified and the URL is http(s). Unverified shows plain text plus an "Unverified link" chip. Dead shows plain text plus a "Dead link" chip and no anchor. The grid caption and panel subtitle stay plain text, as before. **Definition of "verified"**: see the next section. It is in code at `registry.py:309` (`listing_url_verified_at` docstring) and in the TSDoc on `listingUrlState`. Web tests: 5 new tests in `MarketSurface.test.tsx`, including one that never anchors `javascript:`. |
| 5 | PASS | See "How listing data was obtained" below. |
| 6 | PASS, on the cip_test fallback | `cip_n0039_clone` did not exist: it was not in the `pg_database` list, so there was nothing to reuse or drop. It **cannot be created**: `CREATE DATABASE` returned `permission denied to create database` for user `cip` (`clone_create.log`). I followed the node's fallback and used `cip_test`, isolated in a scratch schema `n0039` so cip_test `public` stayed untouched (`public.customer_listing` = 0 before and after). The schema came from a schema-only `pg_dump` of cip (`customer_listing`, `listing_observation`, `dim_product`, rewritten to `n0039.`), the rows from a data-only `pg_dump`. Loaded: 218 / 168 / 18,177 rows. The one expected error is the FK to `dim_customer`, which was not copied (`scratch_create.log`). Every run printed `current_database() = cip_test` before writing. Numbers are below. The scratch schema was dropped (`scratch_verify_drop.log`: remaining matches = 0). cip was re-read afterwards: 0 `original_url`, 0 `dead_link`, 79 bare `/PLID` URLs, so it is unchanged. |
| 7 | PASS | No new dependencies. No network fetches in this run; all tests use mocked `http_get`. |
| 8 | PASS | pytest: 75 passed. That covers `test_listing_auto_finder.py`, `test_takealot_listing_fetch.py`, plus the neighbouring `test_listing_capture_lc_u1.py`, `test_listing_capture_p5_live_fetch.py`, `test_listing_intelligence_v1.py` and `test_cst_listing_seed_fields.py`. vitest `MarketSurface.test.tsx`: 6 passed. `tsc --noEmit`: exit 0. eslint on both changed web files: 0 errors and 1 warning; the warning (`MarketSurface.tsx:350` react-hooks/exhaustive-deps) is in code this change does not touch. Servers were not restarted. Commit `fc69fda3`. |

## "Verified" (precise definition)
A listing URL is verified when the API returns a non-null `url_verified_at`. The API sets it (`listing_url_verified_at`) when either of these holds:
1. `meta_json.url_verified_at` is stamped. This happens:
   - (a) for Takealot, when `record_observation` resolved a real PLID (fetched directly, or found by EAN search and confirmed by barcode or SKU), parsed a price, and wrote the product URL back;
   - (b) for other marketplaces, when a fetch of the stored URL returned HTTP 200 and parsed ok;
   - (c) by the N-0039 repair, stamped with the time of the observation that resolved the PLID, not the repair time.
2. The marketplace is not Takealot and a stored observation of this listing has HTTP 200 with parse ok (`last_ok_fetch_by_listing`).

A Takealot price observation alone never verifies the URL, because Takealot prices come from the REST API and not from the stored URL. `status = dead_link` overrides verified in the UI. Everything else is unverified.

## How listing data was obtained when the stored URL does not resolve (DISCOVERY.md, "How the data was obtained without a working URL")
Takealot prices never came from the stored `/PLID<sku>` URL:
1. `takealot_fetch.fetch_takealot_listing` calls the REST `product-details/PLID<n>` endpoint with the ID in the URL. For a SKU this returns 404.
2. It then searches by `dim_product.ean` and accepts only a single unique hit.
3. It re-fetches the details for that PLID and confirms the match by barcode or SKU.
4. Price comes from `buybox.items[].price`.

The real PLID was stored only in `meta_json.takealot_plid` and the canonical `desktop_href` only in `parse_flags.canonical_url`. That is why the 21 priced Takealot listings had correct prices but broken links. Amazon and Evetech do fetch and parse the stored URL, so for those marketplaces an ok observation does verify the URL.

## Repair proof (scratch `cip_test` schema `n0039`, data copied from cip 2026-09-24)
Script: `apps/api/scripts/ops/repair_n0039_takealot_listing_urls.py`. It is a dry run (rollback) by default. `--apply` commits. `--expect-db` must equal `current_database()`.

| count | before | after apply | after 2nd apply |
|---|---|---|---|
| takealot rows | 79 | 79 | 79 |
| bare `/PLID<n>` URL | 79 | 59 | 59 |
| slug product URL | 0 | 20 | 20 |
| with original_url | 0 | 20 | 20 |
| with url_verified_at | 0 | 20 | 20 |
| flagged unverified (url_check) | 0 | 58 | 58 |
| url_conflict | 0 | 1 | 1 |
| dead_link | 0 | 3 | 3 |
| active | 218 | 215 | 215 |
| non-Takealot fingerprint (md5) | 2617953a… | 2617953a… (unchanged) | unchanged |

- Planned changes by rule: R-a 20, R-a-conflict 1 (id 73, held by 69), R-b 55, R-b-dead 3 (ids 55, 56, 57). R-a total 21 and R-b total 58, matching DISCOVERY.
- The second apply planned 0 changes, so the script is idempotent.
- Guard: with `--expect-db cip` against cip_test the script printed `STOP` and exited 2.
- Sample: id 52 `https://www.takealot.com/PLID222547542` became `…/asus-zenscreen-mb169ck-15-6-inch-fhd-ips-portable-monitor/PLID98174082`.

Logs: `scratch_create.log`, `repair_dryrun.log`, `repair_apply.log`, `scratch_verify_drop.log`. Driver: `clone_db.py`.

### Ready-for-cip (Warren runs; not run here)
Run from the repo root. Dry run first, then apply:
```
(cd apps/api && .venv/Scripts/python.exe scripts/ops/repair_n0039_takealot_listing_urls.py --expect-db cip)
(cd apps/api && .venv/Scripts/python.exe scripts/ops/repair_n0039_takealot_listing_urls.py --expect-db cip --apply)
```
Expect the dry run to show `planned changes by rule: {"R-a": 20, "R-a-conflict": 1, "R-b-dead": 3, "R-b": 55}`, unless cip has changed since 2026-09-24.

## Files changed
- `apps/api/app/services/listing_capture/auto_finder.py`
- `apps/api/app/services/listing_capture/registry.py`
- `apps/api/app/services/listing_capture/takealot_fetch.py`
- `apps/api/app/api/v1/endpoints/listing_capture.py`: list and patch return `url_verified_at` and `original_url`
- `apps/api/scripts/ops/repair_n0039_takealot_listing_urls.py` (new)
- `apps/api/tests/test_listing_auto_finder.py`
- `apps/api/tests/test_takealot_listing_fetch.py`
- `apps/web/src/features/market-listings/MarketSurface.tsx`
- `apps/web/src/features/market-listings/MarketSurface.test.tsx`
- Evidence: this folder (`IMPL.md`, `clone_db.py`, `*.log`)

## Open questions for Warren
- **Q1 (duplicate listings for one product page).** Listings 69 and 73 (customer 20, product 6059, report SKUs 234076925 and 234153078) both point to Takealot PLID101365041. Only one listing per customer can hold a URL. For now, 69 (the lower id) gets the product URL and 73 keeps its old URL, marked unverified with `url_conflict_listing_id = 69`. Options:
  - (a) Keep both listings. Accept that 73 is unverified.
  - (b) Mark 73 `delisted` as a duplicate. The row is kept, not deleted.
  - (c) Two SKUs can be two separate offers on one PLID. If you want both tracked, the unique key would need to include the SKU (a schema change).
- **Q2 (19 Takealot rows with no EAN and no REST 404 yet).** These stay unverified until a poll happens or a steward pastes a real PLID/URL. They are marked `dead_link` only after a real REST 404 with no EAN. Is that the lifecycle you want, or should a steward review them first?
- **Q3 (recovery from dead_link).** This is existing behaviour, not changed here. A `dead_link` listing that later resolves (for example after an EAN is added) does not go back to `active` on its own. Do you want automatic recovery?

## Not done / follow-ups
- No rendered browser check: the web runs a production build that the orchestrator rebuilds. Web behaviour is covered by vitest only.
- The 58 unresolved Takealot rows need a live re-poll to resolve by EAN (36 have an EAN). That was out of scope because it needs network access.
- Evetech (88 rows) was not changed, as DISCOVERY says.

Commit: `fc69fda3` (IMPL.md commit line updated after). Logs (`*.log`) are gitignored and remain on disk in this folder.
