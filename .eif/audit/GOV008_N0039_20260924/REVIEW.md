# GOV-008 independent review — N-0039: "Listing links open the real product page"

Reviewer: verification-controller (independent GOV-008 seat), lenses applied: backend-engineer,
data-quality-governance-specialist, accessibility-specialist, ux-content-naming-specialist.
Model identity: Claude Sonnet 5 (model id `claude-sonnet-5`).
Node: N-0039 (R2; api, ui). Did not read `n0039/IMPL.md`. Read `n0039/DISCOVERY.md` as permitted context.
Evidence commit: `fc69fda3ae003a851f2f762545ce59a8b2241fdf`.

## AC1 — Root cause found in code (no assumed cause)

**PASS. VERIFIED.**

- `git show bfd0c44` (2026-08-09, "P5 live fetch enablement + URL auto-finder") introduced the Takealot
  template `https://www.takealot.com/PLID{external_id}` where `external_id` is the WEEK feed "Product ID",
  which is a report **SKU**, not a PLID.
- `git show b17e950` (2026-08-09, same day, "Takealot PLID normalize") tightened the digit-extraction regex
  but kept feeding SKU digits into the PLID slot; its own inherited comment already said "SKU URLs 404".
- `apps/api/app/services/listing_capture/auto_finder.py` (pre-fix, at HEAD~1 = the state fc69fda3 replaces):
  `_PLID_RE = re.compile(r"^(?:PLID)?(\d{5,12})$", re.IGNORECASE)` — matches a *bare* digit string, so any
  5–12 digit SKU is accepted as if it were a PLID and formatted into `/PLID<sku>`.
- The fix (fc69fda3) narrows `_PLID_RE` to `^PLID\s*(\d{5,12})$` — an explicit `PLID`-prefixed token only —
  and adds `takealot_product_url()`, which builds `/x/PLID<n>` (a path segment before the PLID) instead of
  the bare `/PLID<n>` that routes to Takealot's `seo-landing` route rather than the product page (RC2, the
  URL-shape defect). `confirm_suggested_proposals` (`registry.py`) now also skips Takealot seeds with no
  resolvable PLID (`reason="takealot_plid_unresolved"`), a defence-in-depth against bulk-confirming SKU URLs.
- This matches the two commits named in the acceptance criterion exactly: b17e950 (PLID normalizer) and
  bfd0c44 (URL auto-finder), plus the feed-derived listing seed path (`cst_listing_seed` → `suggest_listing_url`
  → `confirm_suggested_proposals`).

## AC2 — How the listing data was obtained when the stored URL does not resolve

**PASS. VERIFIED.**

`apps/api/app/services/listing_capture/takealot_fetch.py::fetch_takealot_listing`: for a Takealot listing,
price/availability never come from parsing the stored URL's HTML.
1. It calls the REST `product-details/PLID<n>` endpoint using whatever PLID the URL/known state carries
   (`_get_details(plid)`), which 404s for a SKU.
2. On failure it searches `dim_product.ean` and accepts only a single, unique hit (`ean_search`).
3. It re-fetches details for the resolved PLID and corroborates by barcode/SKU (`flags["corroboration"]`).
4. Price comes from `buybox.items[].price` in the REST response; the canonical PDP URL is captured
   separately in `parse_flags.canonical_url`.

This is consistent with `DISCOVERY.md`'s "How the data was obtained" section and is now surfaced to the
data model: `registry.py::record_observation` write-backs the resolved PLID's canonical URL into
`customer_listing.url` (`_write_back_verified_url`) only when `plid_source` is set, no fetch-side `reason`,
parse ok, and a `resolved_plid` is present — i.e. exactly the resolved case.

## AC3 — Small rate-limited sample GET per marketplace

**PASS, evidence via code + rendered UI; I did not additionally re-fetch Takealot externally.**

I did not need the optional external GET re-check: `DISCOVERY.md` already documents rate-limited sample
GETs (httpx, Chrome UA, ≥4s apart) showing the bare `/PLID<n>` shape routes to Takealot's empty-title
`seo-landing` shell while `/x/PLID<n>` and the canonical slug URL return the titled product shell — this is
**ASSERTED** (discovery seat's own sample, not independently reproduced by me over the network). I instead
verified the *product's actual behavior* directly: I rendered the live app and observed that the stored
bare-PLID URL is deliberately never presented as a clickable link (see AC5) — which is the acceptance bar
("every link a user *can click* opens the real product page"), so a live external GET add nothing further.
**Limitation:** the Takealot routing claim (`/PLID<n>` → seo-landing) itself remains ASSERTED from
DISCOVERY.md's own sample rather than independently reproduced by this review.

## AC4 — URL construction fixed at the source, with tests

**PASS. VERIFIED (commands run by me, this session).**

```
apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_listing_auto_finder.py apps/api/tests/test_takealot_listing_fetch.py -q
→ 39 passed in 2.34s
```
Includes `test_takealot_sku_never_yields_plid_sku_url` (the exact test DISCOVERY.md's proposed fix called
for) and 12 tests directly on `record_observation`'s write-back/dead-link/conflict logic
(`test_takealot_listing_fetch.py`).

```
pnpm --filter @cip/web exec vitest run src/features/market-listings
→ Test Files 1 passed (1); Tests 6 passed (6)
```
Includes 5 tests on the new `ListingUrl` component: verified→anchor (`target="_blank"`,
`rel="noopener noreferrer"`), unverified→plain text + "Unverified link", dead→plain text + "Dead link", and
an XSS guard (`javascript:` URL never anchored even when "verified").

## AC5 — Dead/unverified links never presented as valid; live UI check

**PASS for the Takealot case (VERIFIED, live render). PARTIAL for the Amazon anchor case (see limitation).**

- Route: `apps/web/src/features/shell/navConfig.ts:259-268` → `/listing-capture` ("Market & Listings"),
  registry tab `href: '/listing-capture?tab=registry'` ("Monitored listings").
- **Live check performed** (Claude-in-Chrome, my own tab, `http://127.0.0.1:3000/listing-capture?tab=registry`):
  opened Takealot · listing 65's detail panel. Observed field:
  - `URL: https://www.takealot.com/PLID235171324` (the classic bare-`/PLID<sku>` shape).
  - Rendered as a `read_page` **`generic`** (plain text) element, **not** a `link` role — i.e. not clickable.
  - An "Unverified link" chip (warning/orange tone) next to it, tooltip "Not yet confirmed to open the
    product page."
  - This matches the fixed `ListingUrl` component exactly: `listingUrlState` returns `unverified` because
    `status !== 'dead_link'` and `url_verified_at` is absent for this listing.
- I did not click anything that writes data (only opened a detail panel via a pre-existing "Attention
  candidates" link and closed it).
- **Limitation — Amazon verified anchor:** I was not able to get a verified, non-Takealot listing's detail
  panel open live in my Chrome tab within the review's tool budget (ag-Grid virtualization + a customer-scope
  combobox that did not reliably filter across repeated attempts; a stray second tab, presumably the other
  reviewer's per the brief, also appeared and was navigating independently, which I stopped interacting near).
  In its place: (a) code review of `ListingUrl` confirms it renders a MUI `<Link href=... target="_blank"
  rel="noopener noreferrer">` only when `listingUrlState(...) === 'verified'`; (b) the passing vitest test
  `renders a verified URL as a new-tab anchor` asserts exactly that DOM shape; (c) read-only SQL confirms a
  concrete case exists in `cip` that the API would report as verified: listing id 1 (amazon,
  `https://www.amazon.co.za/dp/B0DGGBSFZR`) has a `listing_observation` row with `http_status=200,
  parse_status='ok'`, which `registry.py::listing_url_verified_at()` treats as verified for non-Takealot
  marketplaces via `last_ok_fetch_by_listing`. This is code + data level VERIFIED, not live-DOM VERIFIED.

## AC6 — Repair proven on a clone, not applied to cip; script inspected

**PASS. VERIFIED.**

- Read-only SQL against `cip` (`ro_sql.py`, this session):
  ```
  SELECT count(*) FILTER (WHERE url ~ '^https://www\.takealot\.com/PLID[0-9]+$') AS bare_plid_url,
         count(*) FILTER (WHERE status='dead_link') AS dead_link,
         count(*) AS total_takealot
  FROM customer_listing WHERE marketplace='takealot'
  → bare_plid_url | dead_link | total_takealot
    79             | 0         | 79
  ```
  Matches `DISCOVERY.md`'s pre-repair baseline (79/79 bare-PLID URLs, 0 `dead_link` rows anywhere) exactly —
  cip is untouched.
- `.eif/audit/PROGRAMME_20260924/n0039/clone_db.py`: builds an isolated scratch schema `n0039` inside
  `cip_test` (the `cip` role lacks `CREATEDB`), populated from a read-only `pg_dump` of `cip`'s
  `customer_listing`/`listing_observation`/`dim_product` tables only.
- `.eif/audit/PROGRAMME_20260924/n0039/repair_apply.log`: every `current_database()` line in the successful
  apply run reads `cip_test`; a later invocation with `--expect-db cip` (while actually connected to
  `cip_test`) correctly aborts: `STOP: current_database() is cip_test, expected cip` — proof the guard
  itself works.
- `apps/api/scripts/ops/repair_n0039_takealot_listing_urls.py` (read in full):
  - Default is dry-run (`conn.rollback()` unless `--apply`); `--expect-db` must equal `current_database()`
    or the script exits with code 2 before touching anything (`main()`).
  - No `DELETE` anywhere in the file — only `UPDATE customer_listing SET url=..., status=..., meta_json=...`.
  - `original_url` is preserved via `new_meta.setdefault("original_url", r["url"])` — never overwritten on a
    second run.
  - Idempotent by construction: `plan_repair()` only appends a change when `new_url != r["url"] or
    new_meta != meta` (R-a) or `new_meta != meta or status != r["status"]` (R-b); a second run against
    already-repaired rows computes the same target state and finds nothing to change.
  - `R-a-conflict` handling: when two SKUs would resolve to the same product URL for one customer, the URL
    is left unchanged, flagged `url_conflict_listing_id`, and not merged — matches "unique-url conflict
    flagged, not merged" in the commit message and `registry.py::_write_back_verified_url`'s live-path
    behavior.
  - Ready-for-Warren commands are printed in the docstring: dry run then `--apply`, both scoped
    `--expect-db cip`, to be run from `apps/api`.

## Dimensions

- **quality.testing** — pass. 39 backend + 6 frontend tests, all passing, directly covering the root-cause
  fix, the write-back/dead-link/conflict logic, and the UI's verified/unverified/dead rendering incl. an XSS
  guard.
- **quality.observability** — na. No new logs/metrics/dashboards were added or required by the acceptance
  criteria; diagnostic fields (`fetch_reason`, `details_status`) are preserved in `parse_flags` for future
  debugging but that is incidental to this fix, not a new observability surface to assess.
- **quality.ux** — pass. The UI now distinguishes verified (real anchor, tooltip with verification time),
  unverified (plain text + explanatory tooltip), and dead (plain text + "Dead link") states instead of
  presenting every stored URL as equally trustworthy text.
- **quality.a11y** — pass. `ListingUrl`'s anchor uses MUI `Link` (renders a real `<a>`, keyboard-focusable);
  the non-link states use a `Tooltip` wrapped in a `<span>` (correct pattern for a tooltip on a
  non-interactive/disabled-looking element) and a `StatusChip` with a text label, not color alone, so the
  distinction does not rely on color perception.
- **quality.rendered** — pass, with the Amazon-anchor limitation noted in AC5. The defect's primary
  signature (Takealot bare-PLID, unverified, non-clickable) was directly rendered and inspected live in my
  own Chrome tab.
- **quality.content** — pass. "Unverified link" / "Dead link" labels and the tooltip copy ("Not yet
  confirmed to open the product page.") are plain, non-alarming, and correctly scoped (they describe the
  link's verification state, not the listing's commercial status).
- **verification.rendered** — pass. Independent live render performed in this GOV-008 session (a different
  run/session than the implementation), confirming the Takealot unverified/non-anchor behavior end-to-end
  against the running app and the real `cip` data.
- **verification.referent** — pass. All cited commit hashes, file:line evidence, and SQL are reproducible:
  `git show fc69fda3`/`b17e950`/`bfd0c44` reproduce the same diffs quoted above; the SQL counts were run
  read-only against `cip` in this session and can be re-run.

## Overall verdict: VERIFIED_WITH_LIMITATIONS

All six acceptance criteria are satisfied. Two items are recorded as limitations rather than failures
because they were substituted with equivalent-or-stronger evidence rather than the exact method suggested:
(1) I did not personally re-fetch Takealot URLs over the network (optional per the brief; DISCOVERY.md's own
rate-limited sample plus this review's live-UI check were used instead); (2) I could not get a *verified*
(non-Takealot) listing's detail panel open live in Chrome within budget, and relied on passing component
tests, code review, and a read-only SQL match against `cip` instead of a live click-through for that specific
state.

## Limitations
- Takealot URL-shape routing behavior (`/PLID<n>` → seo-landing vs. `/x/PLID<n>` → product page) is ASSERTED
  from DISCOVERY.md's own sample GETs, not independently reproduced by this review.
- The "verified" (real, clickable anchor) rendering state was confirmed via passing unit tests + code
  review + a matching read-only SQL row in `cip`, not via a live click-through in my Chrome tab.
