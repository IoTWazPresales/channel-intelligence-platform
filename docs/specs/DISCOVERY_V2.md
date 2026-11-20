# Discovery V2: find customer web shops, their product pages, and link them

Status: DESIGN (Opus planner, 2026-11-20). Base: `feat/integrate-20261103` @ `4ca70b68`. Merges to `feat/integrate-20261103` only.
Depends on: the `tenant_setting` PR (worktree `sched-off-20261120`, migration `20261120_0064`). This spec's migration is `20261121_0065`.

Rules this design keeps (Warren): it reuses existing code and adds no parallel systems. Nothing that names a customer, site, retailer or country goes in code or migrations. A link is made automatically only on exact evidence; anything less goes to a steward queue with that evidence. Preview writes nothing. Apply saves. Robots.txt is respected, and the #100 spacing and 403/429 back-off apply to every host, search engines included.

---

## 1. Inventory (verified in code at 4ca70b68)

### 1.1 Discovery and site configuration (reused)
| What | Where | Notes for V2 |
|---|---|---|
| Catalogue-page discovery for reporting customers | `services/listing_capture/discovery.py:119` `discover_reporting_customers(session, tenant_id, http_get, apply, product_limit, run_store, fetch_policy)` | `apply=False` already skips writes (dry run). Rotation and cursor live in the run-state store (`:146-196`, `:329-396`). |
| Per-site search for one product | `discovery.py:419` `_find_and_propose`, `:583` `_search_candidates`, `:621` `_capture_url` | Order: remembered link, then site search URL (`{query}`), then `/sitemap.xml`. Mixes fetching with writes, so V2 splits out a pure finder (S3). |
| Learn a site's search URL from its home-page form | `discovery.py:719` `_discover_search_pattern`, `:748` `_search_form` (inputs `q`/`query`/`search`) | Stored into `listing_site.search_url_pattern` when blank (`:458-462`). V2 adds OpenSearch and common patterns. |
| Sitemap | `discovery.py:772` `_sitemap_urls` | Reads only `<origin>/sitemap.xml` plus the first 2 child maps. It does **not** read `Sitemap:` lines in robots.txt. |
| Page-pattern learning | `discovery.py:797` `_patterns_for`, `:810` `_derived_patterns` → `url_pattern.derive_listing_url_pattern` | Reused for "learn URL patterns from confirmed hits". |
| Products searched per customer | `discovery.py:856` `_catalogue_product_ids` | Products with `reported_soh > 0` in the latest reported period. |
| A customer's site keys | `discovery.py:926` `_site_keys` | Seed `marketplace`, else seed domain, else `customer_listing.marketplace`. V2 adds confirmed `customer_web_site` rows. |
| Site key from a host | `discovery.py:1060` `_site_key_from_origin` | Reused when Apply creates a site. |
| Autoconfigure (beat + steward button) | `autoconfig.py:122` `autoconfigure_sites`; beat `worker/celery_app.py:50-53` `listing-capture-autoconfigure` at `crontab(hour=5, minute=20)`; task `worker/tasks.py:862-903`; steward POST `endpoints/listing_capture.py:230` | Poll: `celery_app.py:55-58` every 30 min. The sched-off PR gates the beat on `discovery.schedule_enabled`. |
| Steward site onboarding | `site_onboarding.py:64` `record_customer_site`; `POST /listing-capture/sites/onboard` (`endpoints/listing_capture.py:163`) | Refuses non-reporting customers (`:92-96`, code `not_reporting`). It writes `customer_report_config.feed_profile_json.listing_seed.site.domain`. `normalize_domain` (`:48`) is reused. |
| Site CRUD | `sites.py:211` `create_site`, `:227` `update_site`, `:236` `set_site_seller` | `set_site_seller` requires at least one seller name or id, so it cannot be the customer↔site association. |
| Live HTTP | `observation.py:199` `default_http_get` (urllib, browser UA `:20`, `Accept-Language` `:24`, 20 s timeout `:25`); switch `listing_live_fetch_enabled()` `:188` (`CIP_LISTING_LIVE_FETCH`) | Follows redirects silently and returns no final URL. |
| #100 pacing and back-off | `site_fetch.py:59` `FetchPolicy` (shared clock, budget, `last_request_at`), `:102` `SiteFetchGate` (spacing `:147-154`, 403/429 pause `:165-171`, time budget `:137`), `STEWARD_RUN_TIME_LIMIT_SECONDS=45` `:39`; `observation.py:29` default 5 s, `:36` `{403,429}`, `:41` 600 s run budget | The gate key is any lower-cased string, so it works for search hosts and candidate hosts too. |
| Pause and run-state store | `site_pause.py:163` `pause_site` (1 h doubling to 24 h); `:229` `default_run_state_store` (Redis, key prefix includes DB name); `:239` `save_run_state`, `:250` `load_run_state` | V2 keeps preview plans, the HTTP cache and robots records here. |
| Robots.txt | none (grep `robots` over `apps/api/app` returns 0 hits) | New in V2 (S1). |

### 1.2 Identity, links and steward queues (reused)
- `identity.py:25` `barcode_key` (digits, leading zeros dropped), `:29` `model_key` (A-Z0-9 upper), `:49` `product_barcodes` (`ean`, `upc`), `:53` `product_models` (`part_number`, `model_name`, `sales_model_name`, length ≥ 4), `:62` `page_facts_from_html` (JSON-LD `gtin*`, `mpn`, `model`; **`sku` deliberately not read: it is a stock code**), `:104` `corroboration(page, product)`. It checks a page against one known product. Nothing checks that a model is unique across the catalogue.
- `links.py:81` `queue_case`, `:118` `remember_link`, `:189` `learn_link` (skips listings with no product: `:198-200`), `:403` `decide_queue` (`confirm`/`reject`/`not_on_site`).
- Tables: `listing_link` (`models/listing_link.py:21`, one confirmed per site+product) and `listing_link_queue` (`:41`, **`product_id` NOT NULL** `:56`, one open row per site+product `:50`). Endpoints: `GET /listing-capture/link-queue` (`endpoints/listing_capture.py:721`), `POST /link-queue/{id}` (`:734`). UI: `ListingLinksLens.tsx`.
- Proposals: `cst_listing_seed` (`models/cst_listing_seed.py:12`). `registry.py:202` `confirm_proposal` ("Never auto-create"). `:231` `confirm_suggested_proposals` registers the seeds that have a remembered confirmed link.
- `ListingLinkQueue` and `ListingSite` are tenant-scoped ORM classes (`core/tenant_scope.py:69-101`). Any new tenant table must be added there.

### 1.3 Data sources for candidate sites
- **Website on file:** there is no `website` column (`DimCustomer`, `models/dimensions.py:99-120`). The only stored domain is `customer_report_config.feed_profile_json.listing_seed.site.domain` (and its URL patterns), read by `discovery._seed_origin` (`discovery.py:1027`), plus hosts of the customer's `customer_listing.url`.
- **Contact domains:** `customer_contact.email` (`dimensions.py:181-192`). Mailbox ingest has only an env-level sender allow-list (`mailbox_ingest/config.py:120`), not tied to customers, so it is not used.
- **Products a customer bought or has on line-ups:** `fact_customer_sellthrough` (latest reported period), `fact_lineup_plan_item.customer_id/product_id` (`models/lineup.py:29-40`), `commercial_lineup_line.customer_id/product_id` (`models/commercial_lineup.py:59-68`), `fact_sales_sellout` (`models/facts.py:11-22`).
- **Product identity columns:** `dim_product.ean`, `upc` (GTIN), `sales_model_name`, `part_number`, `model_name`, `name` (`dimensions.py:203-215`).
- **Name normaliser:** `services/imports/dsi_customer_name_normalization.py:55` `normalize_customer_name_for_similarity` (legal suffixes, T/A, punctuation) and `:98` `customer_similarity_lookup_keys` (full, legal part, trade part). V2 uses **exact equality** of these keys only. It never uses the fuzzy scorers in that file.

### 1.4 The 51 unlinked listings
`docs/audits/LISTING_CAPTURE_CHECK_20261113.md:207,247`: customer 299, site key `amazon`, 51 `customer_listing` rows, all with `product_id` NULL. `learn_link` skips them (`links.py:198-200`) and coverage cannot count them. V2 handles them with the generic "listings with no product" path (§4.5). Nothing in code names that site.

### 1.5 Web UI
- `/listing-capture` page. Lenses come from `features/market-listings/MarketChrome.tsx:17-42` (`MarketLens` union + `LENSES`) and are rendered in `MarketSurface.tsx:1650-1653`.
- `ListingSitesLens.tsx:123-209` has the "Customer with no site" onboarding form, `EntitySearchAutocomplete` customer picker, and `fetchCustomers` from `/api/v1/customers`. `ListingLinksLens.tsx` is the link queue.
- Settings page: `app/(app)/settings/page.tsx`, with panels from `features/settings/*` mounted at `:459-468`.
- UI stack: MUI 6 + TanStack Query (`apps/web/package.json:24-30`). Libraries rule (Warren, 2026-11-20): prefer a well-established, maintained, permissively licensed library over hand-built code for anything non-trivial, name it in the PR, one library per job, and never use fuzzy-matching libraries to link records.

### 1.6 Playwright
- **Web:** `@playwright/test ^1.49.0` (`apps/web/package.json:42`) is installed (`apps/web/node_modules/@playwright/test`). Config: `apps/web/playwright.config.ts` (Desktop Chrome, `e2e/`, live API via `CIP_E2E_API_URL`/`CIP_E2E_LIVE_API`).
- **API:** Python `playwright` is **not** in `apps/api/.venv/Lib/site-packages` and not in `apps/api/requirements.txt`. `httpx` is present (`requirements.txt:20`) but the fetch path uses urllib. A browser fallback in the API therefore needs a new dependency (decision D-W3).

### 1.7 Pre-existing country-specific constants (finding, out of scope)
`observation.py:24` `Accept-Language: en-ZA`, `:45` `PARSED_PRICE_CURRENCY = "ZAR"`, and the `R 12,999` regex (`:138`) are country-specific constants in code. V2 does not touch them. Follow-up: derive them from `tenant.country` plus a `tenant.currency` key.

---

## 2. Tenant settings (no seeded defaults)

The keys are registered in `app/services/tenant_settings.py` `SETTING_VALIDATORS`, edited after the sched-off PR merges. No migration inserts rows. A missing key means **not set**.

| Key | Type / validator | Used for | If unset |
|---|---|---|---|
| `tenant.country` | `{"code": "^[A-Z]{2}$", "name": 1-64 chars}`; both required | Country match; the country name is appended to search queries | Discover and Add-a-site previews refuse with `settings_missing` |
| `tenant.domain_endings` | list, 1-20 items, each `^\.[a-z0-9-]+(\.[a-z0-9-]+)*$`, lower-cased, de-duplicated, order kept | Domain guesses (in order); "ending matches" evidence | Discover refuses with `settings_missing`. Add-a-site still runs, with ending evidence shown as "not set". |
| `discovery.search_providers` | ordered list ⊆ `{"ddg_html","ddg_lite","searxng"}`, max 3 | Web search, primary then fallback | Search is **off**. The preview says so and continues with the other sources. |
| `discovery.searxng_url` | `https://` URL, no query string | The `searxng` provider | Required when `searxng` is in the provider list (validator cross-checks on PUT of either key) |
| `discovery.excluded_domains` | list ≤ 200 hosts, validated with `site_onboarding.normalize_domain` | Hosts never proposed (for example the tenant's own brand site or a marketplace the user does not want) | Nothing excluded |
| `discovery.browser_fallback_enabled` | bool | The real-browser fallback (§4.4) | Off |
| `discovery.schedule_enabled` | bool (reserved by the sched-off PR) | The 05:20 beat | Off |

The Settings UI may show a "recommended" provider order (DuckDuckGo HTML, then DuckDuckGo Lite) as helper text. It is never saved unless the user presses Save.

---

## 3. Free web search (no API key)

### 3.1 Research (2026-11-20)
| Engine | URL pattern | robots.txt for the result path (`User-agent: *`, fetched 2026-11-20) | ToS / behaviour | Verdict |
|---|---|---|---|---|
| DuckDuckGo HTML | `https://html.duckduckgo.com/html/?q=<q>` (GET; POST form also works) | `html.duckduckgo.com/robots.txt`: `Allow: /` → **allowed** | Rate-limits with HTTP 202 and/or an "anomaly" challenge page (`anomaly-modal`, `challenge-form`, "bots use DuckDuckGo too"), as community parsers report. ToS on automated queries **not reviewed** (open question D-W1). | **Primary** |
| DuckDuckGo Lite | `https://lite.duckduckgo.com/lite/?q=<q>` | `lite.duckduckgo.com/robots.txt`: `Allow: /` → **allowed** | Same block signals | **Fallback 1** |
| `duckduckgo.com/html` | `https://duckduckgo.com/html/?q=` | `Disallow: /html`, `Disallow: /lite` → **disallowed** | | Never use this host |
| SearXNG instance | `{base}/search?q=<q>&format=json` (or HTML) | Varies per instance. Public instances' default robots policy was not verified. The robots checker decides at run time. | Public instances: JSON often disabled, and the limiter allows few non-HTML requests per IP (docs.searxng.org, `searx.botdetection`). A self-hosted instance is free and keyless. | **Fallback 2**, only with the tenant's own instance URL |
| Bing | `https://www.bing.com/search?q=` | `Disallow: /search` | | Excluded (robots) |
| Brave | `https://search.brave.com/search?q=` | `Disallow: /search` | Proof-of-work captcha; Brave points scrapers to its paid API | Excluded |
| Mojeek | `https://www.mojeek.com/search?q=` | `Disallow: /search` | ToS expressly prohibits scraping without consent | Excluded |
| Google | `/search` | `Disallow: /search`, `Disallow: /?` | | Excluded |
| Startpage | `https://www.startpage.com/sp/search` | Fetch failed (could not verify) | | Excluded until verified |

Sources: robots.txt files fetched directly. DDG selectors and block signals come from open-source parsers (for example docs.rs `a3s-search`, `webtools-search`, `duckduckgo-core`) and are **community-observed, not official**: the parser must be fixture-tested and must fail soft. SearXNG limiter: https://docs.searxng.org/src/searx.botdetection.html. Mojeek terms: https://mojeek.com/about/terms.html.

### 3.2 Parsers (S2), stdlib `html.parser` only
- **`ddg_html`**: result anchors are `<a class="... result__a ..." href=...>` inside a `.result` block; the snippet is `.result__snippet`. Skip ads: blocks whose class contains `result--ad`, or an href to `duckduckgo.com/y.js`.
- **`ddg_lite`**: anchors with class `result-link`; snippets are `<td class="result-snippet">`, paired by order.
- **Redirect unwrapping (both DDG providers):** if the href's path is `/l/` (scheme-relative `//duckduckgo.com/l/?uddg=…&rut=…` or relative `/l/?…`), the target is `parse_qs(query)["uddg"][0]`. Otherwise use the href as is. Keep only `http(s)` targets.
- **Block detection (both DDG providers):** HTTP 202, **or** body containing `anomaly-modal`, `challenge-form` or `anomaly.js` → outcome `blocked`. The provider calls `site_pause.pause_site(store, "search:<host>", http_status=202 or the actual status, now=…)`, so the same 1 h → 24 h back-off applies. 403/429 already pause through `SiteFetchGate`. "No results" markup → `empty`.
- **`searxng`**: GET `format=json` → `results[].url/title/content`. On non-JSON or 403/429, parse HTML (`article.result h3 a[href]`).
- **Result:** `SearchResult(url, host, title, snippet, rank)`, with host lower-cased and `www.` stripped. Drop the search engine's own hosts. Keep the top 10 per query.

### 3.3 Orchestration and politeness
`web_discovery/search.py`: `web_search(query, *, providers, getter, cache) -> SearchOutcome(status: "ok"|"empty"|"unavailable"|"off", provider: str|None, results: list[SearchResult], attempts: list[{"provider","status","http_status","reason"}])`.
- Providers are tried in the tenant's order. A provider that is paused, robots-disallowed, blocked or erroring moves on to the next. If every provider fails, the outcome is `unavailable`. A preview **never fails** because of search.
- Every request goes through the polite getter (§4.1). The gate key is `search:<host>`. Spacing is `SEARCH_SPACING_SECONDS = 10` (a generic constant, higher than the 5 s site default). Robots.txt of the search host is checked.
- Cache: a successful (`ok`/`empty`) outcome is cached 7 days in the run-state store, keyed `wd:search:<provider>:<sha256(query)>`. Blocked and unavailable outcomes are never cached.
- Volume: at most 4 queries per customer (3 product queries + 1 name query).

---

## 4. Pipeline

New package `apps/api/app/services/listing_capture/web_discovery/`. Pure functions take an injected `getter` and `resolve` (DNS), so unit tests never touch the network.

### 4.1 Polite getter (S1, `polite.py`)
`PoliteGetter(policy: FetchPolicy, cache: HttpCache, robots: RobotsCache, raw_get=fetch_with_final_url)` with `.get(url, *, gate_key, spacing) -> Fetched(status, body, final_url, refused: str|None)`.
1. **Robots:** fetch `<scheme>://<host>/robots.txt` once per host per 24 h (cached at `wd:robots:<host>`), through the same gate. Use an **own RFC 9309 matcher** (`robots.py`); `urllib.robotparser` does not support `*`/`$` wildcards or longest-match. Rules:
   - Use the group for `*`. A longer path match wins; on a tie, `Allow` wins.
   - 2xx: parse. 4xx (including 404): allow all. 5xx, unreachable or timeout: disallow all for this run.
   - `Crawl-delay` raises spacing (capped at 60 s). `Sitemap:` lines are kept for §4.4.
   - A disallowed URL returns `refused="robots"` and sends no request.
2. **Gate:** one `SiteFetchGate(site_key=gate_key, spacing_seconds=…, policy=policy)` per key, created lazily and shared for the run. Keys: an existing site's `site_key`; `host:<host>` for candidate hosts; `search:<host>` for search engines. 403/429 pause the key exactly as today (`site_fetch.py:165-171`).
3. **Redirects:** `fetch_with_final_url` lives in `polite.py`. It is urllib with the same UA, headers and timeout constants as `observation.default_http_get`, and a no-auto-redirect handler. Each hop (max 5) is checked against robots and the gate. It returns the final URL. Body read capped at 2 MB.
4. **Cache:** 200 responses are kept gzip-compressed (reuse `observation.compress_snapshot`) at `wd:http:<sha256(url)>` for 24 h when under 1 MB.

The getter only runs when `listing_live_fetch_enabled()` is true. Otherwise preview creation refuses with `live_fetch_off`.

### 4.2 (a) Candidate sites per customer (S1, `candidates.py`)
`gather_candidates(session, customer, settings, getter, search, resolve) -> list[Candidate]`. Each `Candidate(host, sources: set, evidence: dict)` is de-duplicated by host (lower-cased, `www.` stripped). Sources:
1. `on_file`: `discovery._seed_origin(seed)` host; hosts of this customer's confirmed `customer_web_site` rows; hosts of `customer_listing.url` for the customer. A host already tied to a `listing_site` the customer uses → outcome `already_monitored`.
2. `email`: domain part of active `customer_contact.email`. **Data-driven exclusion:** a domain that appears on contacts of two or more different customers in the tenant is not proposed (this removes shared webmail without a hard-coded list). Evidence shows the domain only, never an address (PII).
3. `product_search`: up to 3 products, chosen in this order of sources, de-duplicated, then by `(sales_model_name is not null desc, product_id asc)`:
   - `_catalogue_product_ids`
   - `fact_lineup_plan_item`
   - `commercial_lineup_line`
   - `fact_sales_sellout` for this customer

   Query: `"<sales_model_name>" <country name>`, else `"<part_number>" <country name>`, else `<dim_product.name[:80]> <country name>`. The first 3 distinct result hosts per query become candidates. Evidence: `{"product_id","query","rank"}`.
4. `name_search`: `"<customer name>" <country name>`, first 3 distinct hosts.
5. `guess`: name keys (§4.3) × `tenant.domain_endings` in order (max 3 keys × 6 endings). `resolve(host)` (`socket.getaddrinfo`, 3 s timeout) on `<key><ending>`, then `www.<key><ending>`. Only resolving hosts are kept.
6. `user`: the "Add a site" domain (`normalize_domain`). This scope starts from that domain only; sources 1-5 are skipped.

Excluded before scoring: `discovery.excluded_domains`, search engine hosts, and the tenant's existing `listing_site` hosts that belong to **other** customers. Those are shown, not proposed.

For every remaining candidate, the home page `https://<host>/` is loaded through the polite getter. A candidate that is unreachable, robots-disallowed or non-200 → outcome `dropped` with a reason (shown in Preview, never saved). A redirect to a different registrable host replaces the candidate host, with evidence `redirected_from`.

### 4.3 (b) Scoring and decision (S1, `scoring.py`, pure)
- `customer_keys(name)`: `[re.sub(r"[^a-z0-9]", "", k) for k in customer_similarity_lookup_keys(name)]`, empties dropped.
- `domain_key(host, endings)`: strip `www.`. Strip the longest matching configured ending, else the last label. Take the last remaining label. Remove `-`.
- **name_exact** = `domain_key ∈ customer_keys`. Exact string equality only.
- **ending_match** = the host ends with a configured ending (the evidence names which one).
- **country_match** = (the matched ending's last label is 2 letters and equals `tenant.country.code.lower()`), **or** the home page declares the country: JSON-LD `addressCountry` equal to the code or name (case-insensitive), or `<html lang>` / `og:locale` region equal to the code. The evidence records `how`.
- **homepage_match** = `og:site_name`, a JSON-LD `Organization.name`, or any `<title>` segment split on `| – - : ·` whose normalised key is in `customer_keys`.
- **found_by_product_search** = at least one product-search hit (§4.2 source 3).

**Decision:**
- `auto_accept` ⇔ name_exact ∧ country_match ∧ found_by_product_search ∧ home page 200 ∧ robots allowed ∧ no `rejected` `customer_web_site` row for (customer, host).
- A previous reject → `already_rejected` (shown, not saved).
- A user-entered domain → `user_confirmed` (the user's own act), still with full evidence shown.
- Everything else that loaded → `steward_queue`, at most 5 per customer, ranked by the tuple (name_exact, country_match, product hits, homepage_match, on_file, email). This ranking is display order, not a score.

### 4.4 (c) Product pages on accepted sites (S3, `pages.py`, pure)
`find_product_pages(site: SiteConfig, origin: str, products: list[DimProduct], getter, learned: dict, *, limit) -> SiteFindings`. It runs for sites that are `auto_accept`, `user_confirmed`, `already_monitored` or previously confirmed. In Preview `limit = 5` products per site; the regular discovery run continues the rest with its existing cursor.

1. **Robots + sitemaps:** `Sitemap:` URLs from robots, then `/sitemap.xml`. This generalises `_sitemap_urls` to take a URL list.
2. **Site search, in order:**
   - stored `search_url_pattern`
   - OpenSearch: `<link rel="search" type="application/opensearchdescription+xml">` → `<Url type="text/html" template>` with `{searchTerms}` → `{query}`
   - the home-page form (`_discover_search_pattern`)
   - generic platform patterns, in order: `/search?q={query}`, `/?s={query}&post_type=product`, `/catalogsearch/result/?q={query}`, `/search?query={query}`

   The first pattern whose result page yields a corroborated product link is **learned**: it is returned in `learned["search_url_pattern"]` and reused for the remaining products. Apply stores it only if the column is blank (existing rule, `discovery.py:459`).
3. **Page facts:** extend `identity.page_facts_from_html`:
   - microdata `itemprop="gtin8|gtin12|gtin13|gtin14|gtin|mpn|model"` (`content` or text)
   - embedded JSON: `<script type="application/json">`, `__NEXT_DATA__`, `application/ld+json` arrays and `@graph`, walked for the keys `gtin*`, `ean`, `mpn`, `model`, `manufacturerPartNumber`
   - `brand.name` → `facts["brand"]`
   - `sku` / `productID` → `facts["stock_codes"]`: **evidence only, never a match** (keeps `identity.py:62-66`; D-W4)
4. **Browser fallback:** a page that has none of the facts above and looks like a client-rendered page (visible text < 500 chars, ≥ 3 scripts) → if `discovery.browser_fallback_enabled` and `importlib.util.find_spec("playwright")`, render it in headless Chromium with the same UA through the same robots check and gate (one tab, 20 s). Otherwise the page outcome is `needs_browser`. Python Playwright is not installed today (§1.6); see D-W3.
5. **Patterns:** after two or more confirmed hits on a site, `_derived_patterns(urls)` → `learned["product_url_pattern"/"page_id_pattern"]`.

### 4.5 (d) Linking (S4, `linking.py`, pure, plus writes in `apply.py`)
- `CatalogueIndex.load(session, tenant_id)` builds `{barcode_key → {product_id}}` from `ean`/`upc`, and `{model_key → {product_id}}` from `sales_model_name`, `part_number` and `model_name` (length ≥ 4, same as `identity._MIN_MODEL`).
- `decide(facts, index, expected_product_id=None) -> LinkDecision(outcome, product_id, how, candidates)`:
  1. A page barcode maps to exactly **one** product → `auto_link`, `how="gtin"`.
  2. Otherwise a page model maps to exactly **one** product → `auto_link`, `how="model"`.
  3. Any key mapping to more than one product → `steward_queue`, reason `ambiguous_identity`, `candidates` = those ids.
  4. No usable facts → `steward_queue`, `no_identity_on_page`.
  5. With `expected_product_id` set (the page was found by searching for product P), an auto-link to a product other than P → `steward_queue`, `identity_mismatch`.
- **Pages on sites:** `auto_link` → `remember_link(status=confirmed, evidence={"how","facts","source":"discovery_v2"})`. If the capture is complete (`discovery._complete_capture`), also add a `cst_listing_seed` proposal via the existing `_store_proposal`. Registering a monitored `customer_listing` stays the existing one-click **Confirm suggested** (`registry.py:231`; D-W2). `steward_queue` → `queue_case` with candidates and evidence. **Change to existing behaviour:** an exact, unique identity with an incomplete price/stock/seller capture is now linked rather than queued as `capture_incomplete`; it simply produces no proposal yet. The existing tests asserting the `capture_incomplete` queue are updated in S3.
- **Listings with no product** (`customer_listing.product_id IS NULL`, any site, tenant-scoped): `link_unlinked_listings(session, tenant_id, customer_id|None, getter, index)`:
  1. **Feed mapping:** a `cst_listing_seed` with the same (customer, marketplace, external_id) and a non-null `product_id` → `auto_link`, `how="feed_seed"` (D-W5).
  2. Otherwise fetch `listing.url` through the polite getter (gate key = the listing's site key) and run `decide`.
  3. Refused, robots-disallowed or unreadable → `steward_queue`, `page_unreadable`, with the page title and HTTP status as evidence.

  Apply: `auto_link` sets `listing.product_id` and calls `remember_link(confirmed)`. `steward_queue` creates a `listing_link_queue` row with `product_id NULL`, `listing_id` set, `reason ∈ {ambiguous_identity, no_identity_on_page, page_unreadable}`, `candidates=[{"product_id", "label"}]`, `evidence={"facts","http_status","title"}`. The steward action `link_product` (§6.4) completes it.

### 4.6 (e) Safety rules (all slices)
- Robots.txt is always respected. Spacing and 403/429 pauses apply per host and per search engine. The run time budget is `POLL_RUN_TIME_LIMIT_SECONDS` (600 s) per preview.
- No CAPTCHA solving, no proxy or IP rotation, no fingerprint evasion (D-0063, `observation.py:16-18`). A block is a stop, not a retry.
- Preview runs only on the worker, one preview per tenant at a time (`SET NX` key `wd:running:<tenant>`, 900 s).

---

## 5. Preview and Apply

### 5.1 Preview is write-free (provable)
The Celery task `listing_capture.discovery_preview(tenant_id, preview_id, request)` opens `SessionLocal()` and **first** executes `SET TRANSACTION READ ONLY`. Postgres then rejects any INSERT, UPDATE or DELETE (`ReadOnlySqlTransaction`). The task ends with `session.rollback()`. It calls only pure functions and the existing `discover_*` paths with `apply=False`.

Allowed non-DB side effects, all in Redis and all operational rather than product data:
- the plan (`wd:preview:<tenant>:<id>`, TTL 24 h)
- the HTTP, search and robots caches
- site pause records (politeness, which must persist)

The test is described in §8.1.

### 5.2 Apply reuses the previewed result (decision)
`POST …/previews/{id}/apply` loads the stored plan and writes it in one transaction. It does **not** recompute.

Why:
- Apply must save exactly what the user reviewed.
- Recomputing would repeat minutes of polite network traffic, and DuckDuckGo or the sites could answer differently.
- Apply then needs no network, so it runs synchronously in the API and finishes quickly.

Safeguards:
1. The plan stores `tenant_id` and a `settings_fingerprint` (sha256 of the discovery keys). A mismatch returns **409 `settings_changed`**.
2. Each item is **re-validated deterministically** against current DB state before writing. Examples: the domain is already confirmed or rejected; the listing now has a product; an open queue row exists; the product link is now confirmed elsewhere. A stale item is skipped and reported as `changed_since_preview`.
3. Auto-decisions are re-derived from the stored evidence by the same pure `scoring.decide` and `linking.decide`. Tampering with Redis cannot upgrade an item to `auto_*`.
4. An expired plan returns **410 `preview_expired`**.

### 5.3 Idempotency
- Apply takes `pg_advisory_xact_lock(hashtext('wd_apply:'||preview_id))`. After commit it stores `applied_at` and the result in the plan. A second Apply returns the stored result with 200 and writes nothing.
- DB guards:
  - `uq_customer_web_site_tenant_customer_domain`
  - the open-queue partial unique indexes (existing site+product, new listing)
  - `listing_link` one-confirmed index
  - the deterministic `cst_listing_seed.external_id` hash (`discovery.py:532`)

---

## 6. Database, API, worker

### 6.1 Migration `apps/api/alembic/versions/20261121_0065_web_discovery.py` (revises `20261120_0064`)
Idempotent (`IF NOT EXISTS`), no data rows, and grants as in 0064.

```sql
CREATE TABLE IF NOT EXISTS customer_web_site (
  id serial PRIMARY KEY,
  tenant_id text NOT NULL,
  customer_id integer NOT NULL REFERENCES dim_customer(id),
  domain varchar(253) NOT NULL,
  site_id integer NULL REFERENCES listing_site(id) ON DELETE SET NULL,
  status varchar(16) NOT NULL CHECK (status IN ('proposed','confirmed','rejected')),
  source varchar(16) NOT NULL CHECK (source IN ('auto','steward','user')),
  evidence jsonb NOT NULL DEFAULT '{}',
  preview_id varchar(36),
  decided_by varchar(256), decided_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_customer_web_site_tenant_customer_domain UNIQUE (tenant_id, customer_id, domain)
);
CREATE INDEX IF NOT EXISTS ix_customer_web_site_tenant_status ON customer_web_site (tenant_id, status);
ALTER TABLE listing_link_queue ALTER COLUMN product_id DROP NOT NULL;
ALTER TABLE listing_link_queue ADD CONSTRAINT ck_listing_link_queue_target CHECK (product_id IS NOT NULL OR listing_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS uq_listing_link_queue_open_listing ON listing_link_queue (listing_id)
  WHERE status = 'open' AND product_id IS NULL;
```

- **Downgrade:** delete `listing_link_queue` rows with NULL `product_id` (documented loss of open "needs product" items), restore NOT NULL, drop the constraint, index and table.
- `customer_web_site` is the customer↔domain association **and** the site-candidate steward queue (`status='proposed'`). It works for any customer, reporting or not, so it does not need `customer_report_config` (D-W6).
- It has an FK to `dim_customer`, so `customer_fk_discovery.py` will find it for merges. Merge repoint can collide on the unique key; the repoint must keep the keeper row. This is noted for the merge owner.

**Models:**
- `app/models/customer_web_site.py` `CustomerWebSite`, registered in `models/__init__.py` and in `core/tenant_scope.py` (tenant-scoped list).
- `models/listing_link.py`: `ListingLinkQueue.product_id: Mapped[int | None]`, plus the new index and check in `__table_args__`.

**Discovery reads confirmed sites:** `discovery._site_keys` gains a third source, the `listing_site.site_key` of the customer's `customer_web_site` rows with `status='confirmed'` and `site_id` set. `_seed_origin` falls back to `https://<domain>`. This lets the 05:20 run and the steward autoconfigure button continue page discovery for confirmed sites. There is **no** scheduled domain discovery: new domains are only ever saved by Apply or a steward.

### 6.2 Apply writes for sites
- `auto_accept` and `user_confirmed`:
  - Find a `listing_site` whose stored URL patterns use this host (same check as `discovery._site_keys:945-951`). Otherwise `create_site(site_key=_site_key_from_origin(...))`, with `-2`, `-3`… on a key collision; `display_name` = homepage org name or the host.
  - Upsert `customer_web_site(status='confirmed', source='auto'|'user', site_id, evidence, preview_id)`.
  - Then write the page and link items for that site.
- `steward_queue`: upsert `customer_web_site(status='proposed', source='auto')`. An existing `confirmed` or `rejected` row is never downgraded.
- Every Apply records `steward_audit.record_steward_audit_sync(user, action='discovery_apply', importer='listing_discovery', payload={preview_id, counts})`.

### 6.3 API: new router `app/api/v1/endpoints/listing_discovery.py`
Mounted in `router.py` at `/listing-capture/discovery`. All routes are tenant-scoped via `tenant_id_from_user`; writes require `Role.STEWARD`.

`GET /capabilities` → `{"live_fetch": bool, "browser_available": bool, "providers": [{"id":"ddg_html","label":"DuckDuckGo (HTML)","needs_url":false}, …], "settings": {"missing": ["tenant.country", …]}}`

`POST /previews` (steward). Body is one of:
```json
{"scope": "customer", "customer_id": 123}
{"scope": "reporting"}
{"scope": "domain", "customer_id": 123, "domain": "shop.example.test"}
{"scope": "unlinked_listings", "customer_id": null}
```
- **202** `{"preview_id": "uuid", "status": "queued"}`
- **409** `{"code": "settings_missing", "missing": ["tenant.country","tenant.domain_endings"], "message": "Set the tenant country and domain endings in Settings → Discovery."}`
- **409** `live_fetch_off`
- **409** `preview_running` (with the running `preview_id`)
- **422** `domain_invalid`, `customer_not_found`

Required settings: `customer`/`reporting` need country and endings; `domain` needs country; `unlinked_listings` needs none.

`GET /previews/{id}` → `{"preview_id","status":"queued|running|done|failed|expired","progress":{"done":2,"total":8},"applied":null|{…},"result":<PreviewResult|null>}`

**PreviewResult:**
```json
{
  "scope": "customer", "created_at": "…", "finished_at": "…", "stopped": null,
  "settings": {"country": {"code": "XX", "name": "…"}, "domain_endings": [".x"], "search_providers": ["ddg_html","ddg_lite"]},
  "search": {"status": "ok|empty|unavailable|off", "provider_used": "ddg_html",
             "attempts": [{"provider": "ddg_html", "status": "blocked", "http_status": 202, "reason": "anomaly_page"}]},
  "customers": [{
    "customer_id": 123, "customer_name": "…", "reporting": true, "notes": ["No products on record for this customer"],
    "candidates": [{
      "item_id": "c-1", "domain": "example.x", "outcome": "auto_accept|user_confirmed|steward_queue|already_monitored|already_rejected|dropped",
      "drop_reason": null, "proposed_site_key": "example-x",
      "evidence": {
        "sources": ["guess","product_search"],
        "name_match": {"exact": true, "customer_keys": ["example"], "domain_key": "example"},
        "ending_match": ".x", "country_match": {"value": true, "how": "cctld|page_locale|address_country"},
        "homepage": {"http_status": 200, "final_url": "https://www.example.x/", "title": "…", "org_name": "…", "match": true},
        "product_search_hits": [{"product_id": 9, "product_label": "…", "query": "\"ABC123\" …", "rank": 2}],
        "robots": "allowed"
      }
    }],
    "sites": [{
      "domain": "example.x", "site_key": "example-x", "state": "existing|would_create",
      "search_pattern": {"value": "https://example.x/search?q={query}", "how": "stored|opensearch|form|common_pattern|none"},
      "fetch": {"stopped": null, "requests": 14},
      "pages": [{"item_id": "p-1", "product_id": 9, "product_label": "…", "url": "…",
                 "outcome": "auto_link|steward_queue|already_linked|rejected_before|not_found|needs_browser",
                 "how": "gtin|model|null", "reason": null, "candidates": [],
                 "facts": {"barcodes": [], "models": [], "stock_codes": [], "brand": null},
                 "capture": {"price": 0, "availability": "in_stock", "seller": "…"}}]
    }]
  }],
  "listings": [{"item_id": "l-1", "listing_id": 7, "customer_id": 299, "customer_name": "…", "url": "…",
                "outcome": "auto_link|steward_queue", "product_id": null, "how": "feed_seed|gtin|model|null",
                "reason": "page_unreadable", "candidates": [{"product_id": 1, "label": "…"}], "facts": {}}],
  "totals": {"sites_auto": 1, "sites_review": 3, "pages_auto": 4, "pages_review": 1, "listings_auto": 0, "listings_review": 51}
}
```
Customer labels show the **name only** (entity code display rule).

`POST /previews/{id}/apply` (steward). No body.
- **200** `{"sites_confirmed": 1, "sites_queued": 3, "sites_created": 1, "pages_linked": 4, "proposals_created": 3, "pages_queued": 1, "listings_linked": 0, "listings_queued": 51, "skipped": [{"item_id": "c-2", "reason": "changed_since_preview"}]}`
- **409** `settings_changed`; **410** `preview_expired`; **409** `preview_not_done`

`GET /site-candidates?status=proposed` → `{"items": [{"id","customer_id","customer_name","domain","evidence","created_at"}]}`
`POST /site-candidates/{id}` `{"action": "confirm"|"reject"}`:
- `confirm` runs the same site write as Apply (§6.2) with `source='steward'`.
- `reject` is allowed on `proposed` or `confirmed`. It never deletes `listing_site` or listings, only stops future proposals and discovery for that customer.

### 6.4 Link queue extension (S4, `endpoints/listing_capture.py` + `links.py`)
- `QueueDecision` gains `product_id: int | None`.
- `decide_queue(action="link_product", product_id=…)` is valid only on rows with `product_id IS NULL`. The product must be in the tenant. It sets `customer_listing.product_id`, calls `remember_link(confirmed, url=listing.url)` and sets status `confirmed`. Action `not_on_site` closes the row.
- `GET /link-queue` adds `customer_name`, `listing_url`, `product_label`, and candidate labels.
- `ListingLinkQueue.product_id` may now be NULL. Audit every reader: `coverage.py`, `discovery.py:985` `_queue_exists`, `links.py` `_open_queue`, the endpoint (grep `ListingLinkQueue`, 7 files).

### 6.5 Worker
- `worker/tasks.py`: `@celery_app.task(name="listing_capture.discovery_preview")`. It calls `web_discovery.preview.run_preview(...)`, saves progress after each customer, and marks the plan `failed` with an error class name (never a message containing secrets) on exception. It always releases the `wd:running` lock.
- No beat entry. **Restart the worker after deploy** (standing rule).

---

## 7. UI (S5). MUI and TanStack only, desktop at 1280×800

- **New lens** `discovery`, labelled "Discover sites", in `MarketChrome.tsx` (`MarketLens` union + `LENSES` entry `href: '/listing-capture?tab=discovery'`, `marketLensFromLocation` maps `tab=discovery`). Rendered in `MarketSurface.tsx` next to `:1651`.
- **`features/market-listings/DiscoveryLens.tsx`:**
  - **Settings banner:** reads `GET /capabilities`. When `settings.missing` is not empty, shows `Alert severity="warning"`: "Discovery needs the tenant country and domain endings. Set them in Settings → Discovery." with a `Button href="/settings#discovery"`. `live_fetch=false` → info Alert; the Preview buttons are disabled.
  - Four action rows (steward or admin only, same `canEdit` rule as `ListingSitesLens.tsx:60`):
    1. **Discover for one customer:** `EntitySearchAutocomplete` (reuse `fetchCustomers` from `ListingSitesLens`) + "Preview".
    2. **Discover for all reporting customers:** "Preview".
    3. **Add a site to monitor:** any customer + "Domain" `TextField` (helper "Host name only, such as shop.example.test") + "Preview".
    4. **Link listings with no product:** "Preview".
  - **Site candidates waiting for review:** `SiteCandidatesQueue.tsx` (list + Confirm/Reject, evidence chips).
- **`DiscoveryPreview.tsx`:**
  - Polls `GET /previews/{id}` with `refetchInterval: 2000` while `queued|running`, showing a `LinearProgress` and "Checked N of M customers".
  - If `search.status` is `unavailable` or `off`: `Alert` "Web search was unavailable, so results come from sites on file, contact email domains and name guesses only." with the attempts listed.
  - Per customer, an `Accordion`:
    - **Candidates table** (`Table` size small): Domain | Outcome `Chip` ("Will be added" success / "Goes to review" warning / "Already monitored" / "Rejected before" / "Not usable: reason") | Evidence chips: Name matches, Country matches (how), Found by product search (n), Home page matches, On file, Contact email, Guess.
    - **Pages table:** Product | Page link | Outcome ("Will be linked (barcode / model)", "Goes to review: reason", "Needs a browser") | Price/stock.
  - **Listings table** for the unlinked scope.
  - Footer: totals, then **Apply** (contained; disabled until `done`; confirm dialog "Save N sites, link N pages, queue N for review?") and **Discard** (clears local state only).
  - The Apply result appears in a success `Alert`; it invalidates the `['listing-capture', …]` queries.
- **`ListingLinksLens.tsx`:** rows with `product_id == null` show "Listing {url} has no product · {reason}", one-click buttons per candidate product ("Link to {label}"), a product `EntitySearchAutocomplete` (builder confirms the products search endpoint used elsewhere in `features/`), and "Not on this site". Reason labels are added for `ambiguous_identity`, `no_identity_on_page`, `page_unreadable`, `identity_mismatch`.
- **`features/settings/DiscoverySettingsPanel.tsx`**, mounted in `settings/page.tsx` with `id="discovery"`, visible to steward and admin:
  - Country code (2 letters) + country name
  - Domain endings (multiline, one per line, order = guess order)
  - Search providers: checkboxes with Up/Down order buttons; helper text "Recommended: DuckDuckGo (HTML), then DuckDuckGo (Lite)"
  - SearXNG URL (shown when ticked)
  - Excluded domains (multiline)
  - Browser fallback switch (disabled with "Not installed on the server" when `browser_available=false`)
  - Scheduled discovery switch, only if the sched-off PR did not already add one

  Each field saves with `PUT /api/v1/tenant-settings/{key}`. Validation errors (422 detail) show inline. Empty fields show "Not set". Nothing is pre-filled.
- **Shared types and fetchers:** `features/market-listings/discoveryApi.ts`.

---

## 8. Tests

### 8.1 Preview is write-free (S1, `apps/api/tests/test_web_discovery_preview_write_free.py`, `@pytest.mark.anyio`, test DB only)
1. Seed tenant fixtures with synthetic names on the `.test` domain: two customers (one reporting, one not), products with ean/model, a `customer_contact`, one listing with NULL product, and tenant settings rows.
2. Snapshot `count(*)` and `max(updated_at)` of `customer_web_site, listing_site, listing_site_seller, listing_link, listing_link_queue, cst_listing_seed, customer_listing, customer_report_config, tenant_setting, steward_audit_event`.
3. Attach a SQLAlchemy `before_cursor_execute` listener that records statements.
4. Run `run_preview` for every scope with a fake getter (URL → fixture body) and a fake `resolve`.
5. Assert:
   - no recorded statement matches `^\s*(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE)`
   - the snapshot is unchanged
   - the first statement is `SET TRANSACTION READ ONLY`
6. **Enforcement proof:** monkeypatch one pure step to call `session.add(CustomerWebSite(...)); session.flush()` and assert `sqlalchemy.exc.InternalError` wrapping `ReadOnlySqlTransaction`, so the read-only guard is real and not just untested code.

### 8.2 Unit tests, no live network
`conftest` fixture `no_network` patches `socket.getaddrinfo`, `socket.create_connection` and `urllib.request.urlopen` to raise. It is autouse in all `test_web_discovery_*` files.

Fixtures in `apps/api/tests/fixtures/web_discovery/` are synthetic HTML with `.test` hosts and invented names:
- **S2 search:** `ddg_html_results.html` (organic + ad + `uddg` redirect with `rut`), `ddg_html_anomaly.html`, `ddg_html_202_empty.html`, `ddg_html_no_results.html`, `ddg_lite_results.html`, `searxng_results.json`, `searxng_results.html`
- **S1 robots:** `robots_wildcards.txt` (`Disallow: /*?` + `Allow: /?*`, longest match, `$`), `robots_crawl_delay.txt`, `robots_sitemaps.txt`
- **S3 pages:** `home_org_jsonld.html`, `home_title_segments.html`, `home_locale.html`, `product_jsonld.html`, `product_jsonld_graph.html`, `product_microdata.html`, `product_next_data.html`, `product_sku_only.html`, `spa_shell.html`, `opensearch.xml`, `home_search_form.html`, `sitemap_index.xml`

Tests by slice:
- **S2** `test_web_discovery_search.py`: parse each fixture; `uddg` unwrap; ad skipped; anomaly or 202 → `blocked` and a pause record on `search:<host>`; fallback order; all providers fail → `unavailable` (no exception); cache hit sends no request; robots-disallowed provider skipped.
- **S1:**
  - `test_web_discovery_robots.py`: RFC 9309 cases, 404 = allow, 503 = disallow, crawl-delay raises gate spacing.
  - `test_web_discovery_scoring.py`: exact keys (T/A legal/trade); near-miss (one letter off) is **not** a name match; auto-accept truth table (all 8 combinations of name/country/product); rejected-before.
  - `test_web_discovery_candidates.py`: shared email domain excluded; excluded domains; product choice order; guesses × endings with fake DNS.
  - `test_web_discovery_apply.py` (anyio, DB): apply writes the expected rows; a second apply writes nothing and returns the same body; `settings_changed` 409; expired 410; `changed_since_preview` skip; a tampered plan cannot create an `auto_*` write.
  - `test_web_discovery_api.py`: roles, tenant isolation, `settings_missing` payload.
- **S3** `test_web_discovery_pages.py`: OpenSearch → pattern; form; common pattern learned once and reused; sitemap from robots; sku-only page is not a match; SPA → `needs_browser` when the fallback is off. Update `test_listing_discovery*` for the capture-incomplete change (§4.5).
- **S4** `test_web_discovery_linking.py`: gtin unique → auto; model shared by 2 products → queue with both candidates; `identity_mismatch`; feed-seed path; `link_product` decision (DB, anyio); queue rows with NULL product do not break `coverage.py`.
- **S5** vitest: `DiscoveryLens.test.tsx` (settings banner, disabled buttons), `DiscoveryPreview.test.tsx` (outcome chips, search-unavailable alert, Apply dialog), `DiscoverySettingsPanel.test.tsx` (no pre-fill, 422 inline), `ListingLinksLens.test.tsx` (no-product row).

### 8.3 Clone test with Playwright (orchestrator, never against live `cip`)
- **Setup:** a restored clone DB; API and worker pointed at the clone with `CIP_LISTING_LIVE_FETCH=1`; worker restarted.
- **CI spec:** `apps/web/e2e/discovery-v2-mocked.spec.ts` runs with `page.route` mocks.
- **Clone spec:** `apps/web/e2e/discovery-v2-clone.spec.ts` (`CIP_E2E_LIVE_API=1`, `viewport 1280×800`). Customers are picked at run time from API data (for example the first reporting customer whose capture-health reason is `no_site_key`); no names in the spec.
  1. Settings → Discovery: set the country, endings and providers; reload and see them saved.
  2. Discover sites → one customer → Preview → wait `done` → screenshot. Assert the candidates table has evidence chips and the search status is shown.
  3. Apply → assert the counts Alert. The site-candidate queue shows the queued rows. Confirm one → Sites & sellers shows the site.
  4. Link listings with no product → Preview → the listings table shows one row per unlinked listing (51 expected on the current clone) with an outcome. Apply → Link queue shows the queued rows. Link one with "Link to …" → the row leaves the queue.
  5. Re-press Apply on the same preview → identical counts and no new rows (DB check by the orchestrator via read-only SQL on the clone).
- **Write-free check on the clone:** row counts of the §8.1 tables before and after a Preview are equal.

---

## 9. Build slices and file ownership

Builders **BE-A** (S1 → S4), **BE-B** (S2 → S3) and **FE** (S5) work in parallel. A file has one owner. Interfaces are fixed here, so stubs unblock work.

| Slice | Owner | Files (create unless marked *edit*) | Depends on |
|---|---|---|---|
| **S1 core** | BE-A | `alembic/versions/20261121_0065_web_discovery.py`; `models/customer_web_site.py`; *edit* `models/__init__.py`, `models/listing_link.py`, `core/tenant_scope.py`, `services/tenant_settings.py` (keys §2), `api/v1/router.py`, `worker/tasks.py`; `web_discovery/__init__.py`, `settings.py` (`load_discovery_settings(session, tenant) -> DiscoverySettings(missing=[…])`), `robots.py`, `cache.py`, `polite.py`, `candidates.py`, `scoring.py`, `preview.py` (`run_preview`, plan store), `apply.py` (sites part); `endpoints/listing_discovery.py`; *edit* `discovery.py` **only** `_site_keys`/`_seed_origin` (§6.1); tests `test_web_discovery_{settings,robots,scoring,candidates,preview_write_free,apply,api}.py`; fixtures `fixtures/web_discovery/robots_*`, `home_*` | tenant_setting PR merged |
| **S2 search** | BE-B | `web_discovery/search.py`, `web_discovery/search_parsers.py`; fixtures `fixtures/web_discovery/{ddg_*,searxng_*}`; `tests/test_web_discovery_search.py` | `polite.PoliteGetter` interface (stub until S1 lands) |
| **S3 pages** | BE-B | `web_discovery/pages.py`; *edit* `identity.py` (fact extraction only; `corroboration` and keys unchanged), `discovery.py` (except the S1 functions: extract the pure finder from `_find_and_propose`/`_search_candidates`/`_sitemap_urls` and call it); fixtures `product_*`, `opensearch.xml`, `sitemap_index.xml`, `spa_shell.html`, `home_search_form.html`; `tests/test_web_discovery_pages.py`; *edit* existing `test_listing_discovery*` | S2 (getter usage), S4 `linking.decide` signature (stub) |
| **S4 linking** | BE-A | `web_discovery/linking.py`; *edit* `links.py` (`link_product`, `queue_listing_case`), `endpoints/listing_capture.py` (`QueueDecision`, `/link-queue` payload), `coverage.py` (NULL product guard), `web_discovery/apply.py` (pages + listings part); `tests/test_web_discovery_linking.py` | S1 |
| **S5 UI** | FE | *edit* `MarketChrome.tsx`, `MarketSurface.tsx`, `ListingLinksLens.tsx`, `app/(app)/settings/page.tsx`; new `DiscoveryLens.tsx`, `DiscoveryPreview.tsx`, `SiteCandidatesQueue.tsx`, `discoveryApi.ts`, `features/settings/DiscoverySettingsPanel.tsx`; vitest files §8.2; `e2e/discovery-v2-mocked.spec.ts`, `e2e/discovery-v2-clone.spec.ts` | API contract §6.3 (mock until S1 lands) |

**Order to merge:** tenant_setting PR → S1 → S2 → S4 → S3 → S5. Then the clone test (§8.3). DONE means the orchestrator shows the live screen at 1280×800 with real clone data.

**Gates per slice:** `pytest` for the touched tests plus the existing `test_listing_*`; `ruff check`; web `tsc --noEmit` (no NEW errors) and vitest.

---

## 10. Risks
1. **DuckDuckGo blocks automated queries** (202 or anomaly page). Mitigation: low volume (≤ 4 per customer), 10 s spacing, 7-day cache, pause on block, ordered fallback, graceful "search unavailable". Discovery still works from on-file, email and guess sources.
2. **Terms of service** for automated DDG queries have not been reviewed (D-W1). Public SearXNG instances may disallow queries in robots.txt; a self-hosted instance is the dependable keyless fallback.
3. **False auto-accept:** another company with the same normalised name in the same country that sells the same products. This needs three independent exact signals; a steward can reject a confirmed site later.
4. **Selector drift** in DDG markup makes parsers return empty. Fixture tests cover only the known shape. Mitigation: `attempts[]` and `empty` versus `blocked` are visible in Preview. Refresh fixtures from a clone run.
5. **Robots parsing errors** could fetch disallowed paths. Mitigation: own RFC 9309 matcher with wildcard fixtures; 5xx or unreachable robots = disallow.
6. **Stale preview at Apply:** re-validation, settings fingerprint, 410 on expiry.
7. **Redis unavailable:** the plan store is unavailable, so preview creation fails with `store_unavailable`. There is no silent in-process fallback, because the API and worker could not share it.
8. **Nullable `listing_link_queue.product_id`** may break readers that assume an int. Mitigation: S4 audits the 7 files that reference it; check constraint; tests.
9. **The listing pages for the 51 may refuse** (403 pauses that site for the poll as well) or show no identity facts. Those items go to the queue as `page_unreadable`, and a steward links them in one click.
10. **Time budget:** an all-reporting-customers preview can hit 600 s. The result is partial with `stopped: "time_limit"`. Run it again; caches make repeat runs cheap.
11. **Behaviour change:** an exact identity with an incomplete capture is now linked rather than queued (§4.5). Existing tests change in S3.
12. **Privacy:** contact emails are reduced to domains in evidence; full addresses never appear in plans, logs or UI.
13. **Merges:** `customer_web_site` is found by FK discovery; the unique key can collide on repoint (owner of `customer_full_repoint.py` to handle).
14. **Pre-existing** country-specific constants in `observation.py` (§1.7) remain until a follow-up.

## 11. Decisions for Warren (open; recommendation first)
- **D-W1:** Accept DuckDuckGo HTML, then Lite, as the keyless primary and fallback after reviewing DDG's terms. *Recommend yes, low volume, robots-allowed hosts only.* Optionally run a self-hosted SearXNG as a further fallback.
- **D-W2:** On exact links, keep registration as **Confirm suggested** (one click) rather than auto-creating `customer_listing`. *Recommend keep* (matches `registry.py:209`).
- **D-W3:** Add Python `playwright` and Chromium to the API/worker for the browser fallback. *Recommend defer.* Ship with `needs_browser` reporting; it needs a dependency grant.
- **D-W4:** A page `sku` equal to our part code stays evidence only. *Recommend yes* (keeps `identity.py:62`).
- **D-W5:** Treat a feed seed's `product_id` (same customer, site and external id) as exact evidence for unlinked listings. *Recommend yes.*
- **D-W6:** Use the new `customer_web_site` table (any customer) instead of widening `site_onboarding` to non-reporting customers through `customer_report_config`. *Recommend new table*; `site_onboarding` is unchanged.
