# N-0085 Listing coverage for all eight reporting customers

Feature-definition panel, read-only. cip counts and site checks taken 2026-10-07.

## AS-IS

| Customer | Products sold, last 6 months (all have EAN) | Listings (linked) |
|---|---|---|
| Evetech | 65 | 88 (70; all 65 covered) |
| Computer Mania | 36 | 0 |
| Takealot | 31 | 79 (57; all 31 covered) |
| Makro | 27 (last report 29 Jun) | 0 |
| Game | 15 | 0 |
| Amazon | 0 (31 in its only report, Apr 2025) | 51 (**0**) |
| Incredible / HiFi | 0 (3 and 1, last Jun 2025) | 0 |

- EANs are stored as `4711636287296.0`, so they must be normalised before an exact match.
- The model is not unique: 151 products share 90 model names. The part number and the EAN are unique.
- Nothing has been fetched since 13 Aug. Even so, `capabilities.ts` still says "Checked on a schedule", which is false.
- The poller polls only `active` listings (`registry.py:609`). Nothing sets a listing back to `active`, so a restock is never seen. `consecutive_dead` is never passed in, so the dead-link backoff never fires, and a 403 or 429 does not stop the run.
- Beat runs every 30 min (`celery_app.py:49`), gated by `CIP_LISTING_CAPTURE_SCHEDULE` and `CIP_LISTING_LIVE_FETCH`. The supervisor never sets either (`cip-supervisor.ps1:18`).
- The steward screen is **Feed proposals** (`?tab=proposals`), with 63 Evetech proposals waiting.

Sites (robots.txt plus at most 3 polite requests each):

| Retailer | Platform | Site search |
|---|---|---|
| Takealot | REST API | allowed on `api.takealot.com` |
| Evetech | Next.js; `/api/` disallowed | `/search?q=` allowed; results drawn by script |
| Computer Mania | Shopify | `suggest.json` allowed; EAN found 0 (barcodes not indexed) |
| Game | Walmart; pages `/…/p/<18-digit code>` | allowed, but the page is an empty 21 KB shell; sitemap URLs carry no names |
| Makro | Flipkart Commerce Cloud | **disallowed** |
| Incredible, HiFi | One Magento, identical robots.txt | `/catalogsearch/` blocked, `/*?q=*` allowed; sitemap |
| Amazon | Amazon | `/s?` and `/dp/` allowed by robots.txt |

Every site allows product pages.

## CHALLENGE

1. **Terms.** Amazon's Conditions of Use forbid automated extraction. That comes from general knowledge and was not fetched today. Incredible and HiFi publish `ai-train=no, use=reference`. Our User-Agent should identify CIP and give a contact.
2. **Game and Makro do not share a platform**, so each needs its own reader. Incredible and HiFi do share one.
3. **EAN gaps.** None are sold without one. The risks are the ".0" format and pages that hide the EAN.
4. **Several pages per product** (already 3 cases). A model-only search would hit about 1.7 products, so a page counts only if it shows the EAN or the part number.
5. **Delisted vs moved.** A 404 now goes straight to `dead_link`. Instead it should search again by EAN and propose a "moved" page.
6. **Amazon ASIN vs EAN.** The link can come only from the same feed row, never from the title.
7. **Load.** About 430 listings every 30 min comes to about 20k requests a day, roughly one every 30 s per site. The Windows worker is a single process, so each run needs a time limit.
8. **The active-only filter** (above) is fixed first.

## DESIGN

**Reader contract.** Each site gets `listing_capture/adapters/<site>.py`:
- `find(keys)` returns candidate pages. Keys are the EAN, part number, model and feed id.
- `fetch(listing)` returns a snapshot.
- `parse()` returns price, stock, promo, title, brand, images, description words, specs, seller/buy box, rating, reviews, the page's EAN and part number, the canonical URL and the external id.
- Settings per reader: `spacing_s`, `max_per_run`, `poll_minutes`.

Shared: robots.txt cached daily; UA `CIP-listing-capture/1.0 (+contact)`. A 403 or 429 pauses that site for 1 h, doubling up to 24 h. The fields go into `parse_flags.fields`, which N-0078 uses.

**Discovery** (`listing_capture.discover`, daily 02:30) looks only at sold pairs with no listing, and at dead links. Per pair it makes one search and up to three page fetches, with a daily cap per site. A page is proposed only when it shows the EAN or the part number. A model-only hit is marked "not corroborated" and can only be confirmed one at a time.

**Worklist.** Feed proposals becomes **Proposed listings**. Each row shows the customer, product, page link, how it was found, and what the page shows (title, EAN, price). **Confirm selected** takes corroborated rows only and lists the skipped ones. Nothing auto-registers.

**Registry.** New marketplaces: `game`, `makro`, `computer_mania`, `incredible`, `hifi`. New status `retired`, set by a steward. New source `site_search`.

| Status | Checked |
|---|---|
| `active`, `out_of_stock` | every 30 min; back to `active` when seen in stock (`restocked`) |
| `dead_link` | daily, then rediscovery |
| `delisted` | weekly |
| `retired` | never |

**Polling.** Each run takes the oldest-due listings first, mixes retailers, and stops at 10 min. Spacing is 2 s, or 5 s for a new retailer.

**Supervisor.** The worker env in `Start-Component` gains `CIP_LISTING_CAPTURE_SCHEDULE='1'` and `CIP_LISTING_LIVE_FETCH='1'`. The comment at line 18 changes to match. Amazon stays off per site until decision 1.

**Coverage lens** (`?tab=coverage`): one row per customer showing sold, watched, awaiting steward, failing, not found and not searched, plus the site's state. Each row drills down to its products.

**When a site refuses**, Monitored listings and Coverage show a chip such as "Game paused: 429 at 14:02, next try 15:02". It never blocks anything.

**Migrations:**
- M1 `cst_listing_seed`: add `proposal_source`, `candidate_url`, `match_key`, `evidence_json`, `found_at`, `decided_by`, `decided_at`.
- M2 new `listing_site_state` and `listing_customer_site`.
- M3 new `listing_discovery_attempt`.
- M4 `customer_listing`: add `next_due_at` and `consecutive_failures`.

**API:** `GET /coverage`, `GET /coverage/{customer_id}/products`, `POST /proposals/confirm-bulk`, `POST /discovery/run`, `GET /sites`.

## WORK SPLIT

| Unit | Content | Size | Acceptance |
|---|---|---|---|
| U1 | Polling on, restock fix, politeness, time limit, supervisor env | S–M | Status shows both flags; a beat run records Takealot and Evetech checks; a restock becomes `active`; a 429 pauses only that site |
| U2 | Reader framework (Takealot, Evetech, Amazon), N-0078 fields, M1–M4, discovery for Takealot and Evetech | M | 168 stored checks re-read with zero fetches and the same price/stock; only corroborated proposals |
| U6 | Proposed listings and Coverage (in parallel after U2) | M | Bulk confirm with evidence; counts match SQL |
| U4 | Computer Mania: search by part number or model, check `products/<handle>.js` sku/barcode | S | Most of the 36 corroborated |
| U3 | Game (a short trial of its search JSON first); Makro per decision 2 | M | Game's 15 proposed |
| U5 | Incredible and HiFi: one Magento reader using the sitemap | S | Per decision 3 |

## DECISIONS FOR WARREN

1. **Amazon:** (a) poll its pages anyway; (b) use ASUS's vendor data, keyed by ASIN; (c) keep the ASINs only. Recommend (b), and (c) until (b) is in place.
2. **Makro forbids site search:** (a) browse allowed category pages; (b) ask Makro for a feed; (c) the steward pastes the 27 URLs. Recommend (c) now, then (b).
3. **Incredible and HiFi feeds have stopped** (4 products): build U5 now, or wait until the feeds resume. Recommend waiting. This narrows "all eight".
4. **Which contact goes in the User-Agent?**

## Seats that sat out

Security and privacy (no personal data), database and accessibility (both at implementation), reliability (U1's acceptance), pricing/GTM/presales (no commercial choice), model evaluation (no AI).
