# N-0039 Discovery: listing links open the real product page

Discovery seat, read-only. cip measured 2026-09-24.

## Root causes

**RC1: the Takealot URL is built from the wrong ID. VERIFIED.**
`apps/api/app/services/listing_capture/auto_finder.py:15-18` has the template `https://www.takealot.com/PLID{external_id}`. Its own comment says the WEEK "Product ID" is a **SKU** and "SKU URLs 404". `auto_finder.py:46-51` (b17e950 removed the spaces) puts that SKU into the PLID slot. `registry.py:196-238` `confirm_suggested_proposals` bulk-confirms the suggestion as-is (commit cb7660c). Fetch-time recovery (`takealot_fetch.py:199-257`, commit 8db6739, 2026-08-13) finds the real PLID. It writes that PLID only to `meta_json.takealot_plid` (`registry.py:302-305`) and never rewrites `customer_listing.url`.
Evidence: all 79/79 Takealot rows satisfy `url = 'https://www.takealot.com/PLID'||external_id`. For the 21 rows that were resolved, the resolved PLID ≠ the URL ID in 21/21 cases (e.g. id 52: URL PLID222547542, real PLID98174082). 55 of the 79 rows were confirmed on 2026-08-26 by `demo-user`, after 8db6739 had documented the defect.

**RC2: the Takealot URL has the wrong shape (no path segment before the PLID). VERIFIED at routing level; the rendered "doesn't exist" text is ASSERTED from the operator's report.**
Takealot's Next.js router sends the single-segment path `/PLID<n>` to its `seo-landing` route (`slug_path=PLID98174082`), not to the product page. This happens even with a **valid** PLID. `/x/PLID<n>` and `/<slug>/PLID<n>` return the titled product shell. So fixing the ID alone would still leave broken links.

**RC3: dead links are never marked for Takealot. VERIFIED.**
`registry.py:340-342` marks `dead_link` only when `plid_source` is set. This is deliberate, because SKU URLs were known to 404. So the 3 listings that returned a REST 404 (ids 55-57, no EAN, so no fallback) stay `active`. Across all marketplaces, 0 rows have `dead_link`.

## Measured (cip, read-only)

| marketplace | listings | status | source | URL shape | observed | priced obs | resolved PLID |
|---|---|---|---|---|---|---|---|
| amazon | 51 | active 51 | feed_proposal | `/dp/<ASIN>` | 51 | 51 | n/a |
| evetech | 88 | active 88 | feed_proposal | `/asus-laptops/laptops-for-sale/<webid>` | 44 | 44 | n/a |
| takealot | 79 | active 79 | feed_proposal | `/PLID<sku>` (79/79) | 24 | 21 | 21 (meta_json) |

- All 218 rows have a URL; one customer per marketplace.
- `cst_listing_seed`: amazon 51 and takealot 79 confirmed; evetech 88 confirmed, 63 proposed.
- Takealot observations:
  - 200/ok via `ean_search`: 21
  - 200/ok via `url_or_known`: 21 (repeat polls)
  - 200/`price_noise_or_shell`: 24 (pre-REST HTML)
  - 404/`json_no_price`: 6 obs on 3 listings (ids 55-57)
- The last Takealot fetch was 2026-08-13. The 55 rows registered on Aug-26 have never been fetched. Of the 58 unresolved Takealot rows, 36 have a product EAN, so they are resolvable. 22 have none.
- The 44 Evetech rows registered on 2026-08-26 were never observed.

## Sample GET (httpx, Chrome UA, redirects followed, ≥4 s apart; `sample_get.py`, `sample_get2.py`)

| URL | status | final URL | page |
|---|---|---|---|
| takealot.com/PLID222547542 (id 52, SKU) | 200 | same | 15.3 KB shell, empty title (seo-landing) |
| takealot.com/PLID233951759 (id 55, SKU) | 200 | same | same shell |
| takealot.com/PLID203053235 (id 122, SKU) | 200 | same | same shell |
| takealot.com/x/PLID98174082 (real PLID) | 200 | same | 17.5 KB, titled product shell |
| takealot.com/asus-zenscreen-…/PLID98174082 (canonical) | 200 | same | 17.7 KB, titled |
| takealot.com/PLID98174082 (real PLID, no slug) | 200 | same | 15.3 KB shell, routed `seo-landing` |
| amazon /dp/ ×3 (ids 1-3) | 200 | same | product titles: OK |
| evetech …/40354, 40394, 42030 | 200 | same | no `<title>` matched: INCONCLUSIVE |

Takealot renders client-side and returns 200 for every path, so the route or title is the not-found signal, not the status code. Evetech's stored 2026-08-10 snapshots (ids 76-78) have product titles and canonical links, so those links resolved on that date. Today's result is unverified because the request budget was used up. No rendered-browser check was done (UNABLE_TO_RENDER).

## How the data was obtained without a working URL

Takealot prices never come from the stored URL:
1. `takealot_fetch.py` calls the REST `product-details/PLID<n>` endpoint with the URL's ID, which 404s for SKUs.
2. It then searches by `dim_product.ean` and accepts only a single unique hit.
3. It re-fetches the details and corroborates by barcode or SKU.
4. Price comes from `buybox.items[].price`. The canonical `desktop_href` is kept only in `parse_flags.canonical_url`.

Amazon and Evetech fetch the stored URL itself (HTML parse).

## Lifecycle and UI

- Statuses (`marketplace_vocab.py:11-16`): active, out_of_stock, delisted, dead_link. These are varchar, not a DB enum.
- `create_listing` always writes `active` (`registry.py:74`). Status changes only in `record_observation` (`registry.py:340-344`); no seed "observed" state exists on the listing.
- UI: `apps/web/src/features/market-listings/MarketSurface.tsx` renders `url` as **plain text**, not an anchor, in three places: :472 (grid caption), :1348 (panel subtitle) and :1441 (URL row). It maps `dead_link` to a "Dead link" danger tone (:138, :173) and lists dead links in problems (:847-864).
- The UI has no verified or unverified distinction. It never shows the resolved PLID or `canonical_url`.
- Proposals prefill `suggested_url` (:1112, :1147), which carries RC1 into every new confirmation.

## Proposed fix (not implemented)

1. **Source**
   - `auto_finder`: stop emitting a Takealot URL from a SKU. Return None, or a URL only when the input is an explicit `PLID`-prefixed token. Always use the `/x/PLID<n>` shape, or the canonical slug when it is known.
   - `confirm_suggested_proposals` must not bulk-confirm Takealot seeds that have no resolved PLID.
2. **Resolution write-back**
   - When `plid_source` is set and `canonical_url` is present, set `customer_listing.url` to `canonical_url`.
   - Keep the original value in `meta_json.original_url`, and stamp `meta_json.url_verified_at`.
3. **Dead link**
   - For Takealot, mark `dead_link` when the REST details call returns 404 and EAN resolution fails, i.e. reasons `plid_not_found` or `ean_not_unique_or_missing`. The current rule requires `plid_source`, which excludes exactly these cases.
   - Keep the 3-strike backoff.
4. **UI**
   - Make the URL an `<a target="_blank" rel="noopener">` only when the link is verified: canonical written back, or a 200 parse ok for non-Takealot marketplaces.
   - Show "Unverified link" for others and "Dead link" with no anchor for dead ones.
   - Test: a Takealot SKU never yields `/PLID<sku>`.

## Repair scope (NOT run)

- **R-a (URL rewrite):** 21 rows.
  - Predicate: `marketplace='takealot' AND meta_json ? 'takealot_plid'`.
  - Set `url` to the latest `listing_observation.parse_flags->>'canonical_url'`, falling back to `'https://www.takealot.com/x/PLID'||(meta_json->>'takealot_plid')`.
  - Keep the old URL in `meta_json`.
- **R-b (flag as unverified, pending re-poll):** 58 rows.
  - Predicate: `marketplace='takealot' AND NOT coalesce(meta_json ? 'takealot_plid', false)`.
  - 36 of these are resolvable by EAN on the next poll.
  - Of the rest, ids 55-57 are REST-404 with no EAN, making them `dead_link` candidates. That is 3 rows, so 19 remain unresolvable without an EAN.
- **Out of scope:** Amazon (51 rows, sample OK). Evetech (88 rows) needs a rendered check or re-poll before any change; its 63 `proposed` seeds are not listings.

Artifacts: `sample_get.py`, `sample_get2.py`, `tkl_valid_plid_noslug.html`, `evetech_snap.py` (same folder).
