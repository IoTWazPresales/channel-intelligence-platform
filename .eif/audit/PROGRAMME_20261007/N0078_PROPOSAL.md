# N-0078 Listing quality checks: proposal for D-0050

Read-only panel (PM, GTM, market, architecture, interaction). Counts are from cip, 2026-10-07.

## What is stored today
- **218 listings**, all `active`, all from feed proposals: Takealot 79 (57 linked to a product), Evetech 88 (70), Amazon 51 (0).
- **168 checks** from 119 listings, every one with its snapshot. All of them date from 9–13 Aug 2026; **nothing has been fetched for 8 weeks.**
- **Parse results:** 138 ok and 30 failed. All 30 failures are Takealot: 24 old pages where only the page shell came back, and 6 that returned 404.
- **What each snapshot holds:**
  - Takealot: the full product data from Takealot's own feed, usable for only **21 listings**.
  - Evetech: the full page, including its structured product and breadcrumb data.
  - Amazon: the full page.
- The parsers pull out only price, stock and badge (`observation.py`, `takealot_fetch.py`). `reparse_observation` can re-read stored snapshots without fetching again.

## The checks

| Check | From what is stored? | Recommend |
|---|---|---|
| Price shown and in stock | Yes, already extracted | **YES** |
| Title has brand and model | Yes: Takealot `core.title`/`brand` and Evetech product data, compared with the product master's model and marketing name (107–108 of 114) | **YES** |
| Image count | Takealot yes (`gallery.images`, 5–12). Evetech's product data lists only 1 image, so it needs a page parser | **YES**, 6 or more |
| Description present and long enough | Takealot yes (381–951 words). Evetech's product-data description is 37 words; the full text needs a page parser | **YES**, 150 words or more |
| Key specs present | Takealot yes (`product_information`, 12–34 fields) | **YES**: CPU, RAM, storage, screen, OS |
| Buy box held by the expected seller | Takealot yes. `seller_detail` appears only when a marketplace seller holds the buy box: **4 of 21 today** (TECHNOLAB ×2, Microhard, MWO) | **YES**, the strongest signal |
| Rating and review count | Takealot yes (5 of 21 have 0 reviews). Evetech has none | **YES**, information only; flag 0 reviews |
| Category / breadcrumb | Shown, but checking it needs an expected category per product line per marketplace | Optional |
| Specs agree with our master | Possible: `specs_json` has CPU and screen for 107 of 114. Needs a field map. Real case: listing 53 (ROG Ally X) gives the CPU as "AMD A-Series" | Optional, flag only |
| Indexable by search engines (`seo.x_robots_tag`) | Yes, free | Optional |
| Search position for named terms | No, this needs new fetches | Optional, Takealot only, as a second step |

Amazon: **defer**. No listing is linked to a product, its price comes from a loose page match, and no seller block was found.

## Search position
- Takealot's search endpoint is already in use (`ean_search_url`), so this is a new poll, not new technology.
- Limits: up to 25 terms, daily, top 50 results, 2-second spacing, stop on 403 or 429. About 25 fetches a day, in its own table.
- **Warren supplies the terms** (blocker BL-0016).
- Evetech and Amazon search: no.

## Where findings show
- **`/listing-capture?tab=quality`**, the lens that shows "Planned" today (`MarketSurface.tsx:1435`). It becomes one row per listing, with a column per check, a flag count and the time of the last check.
- **The listing drawer** shows what was actually seen, for example "Buy box: TECHNOLAB (marketplace seller), not Takealot".
- **A failing check** shows an amber **Flag** chip with the reason. It never blocks anything.
- **Grey "No data"** appears when there is no snapshot or it failed to parse. Missing is never a failure.

## Build
- Add `listing_capture/quality.py`: one pure function per marketplace.
- Results go into `parse_flags.quality` with a `rules_version`. No migration.
- Back-fill the 168 stored snapshots with zero fetches.

## Before deciding
1. **Polling has been stopped since 13 Aug.** Restarting it is a separate environment decision.
2. The poller skips anything not marked `active` (`registry.py:609`), so a restock is never seen.
3. Most Takealot rows will show "No data" until polling resumes.
4. Spec §8 named SEO a non-goal for v0. Record the change of mind as a decision.

## Ask (D-0050)
**Yes** or **adjust** each:
- the 7 checks;
- the limits: 6 images, 150 words, five key specs, Takealot retail as the expected seller;
- the extras;
- search position: Takealot-only and daily, plus your terms.
