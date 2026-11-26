# Step 1: Monitored listings keeps its page; the price matrix is its centrepiece

- **Status:** Session 1 done (built, gated, pushed). Waiting for the coordinator's independent review, merge, deploy and live proof. SRP source is a QUESTION FOR WARREN.
- **Branch:** `fix/listings-matrix-centrepiece-20261125` (base `bc396c88`; `origin/feat/integrate-20261103` is now `6d2adc16`, docs-only commits, no overlap with this step's files)
- **Worktree:** `C:\Users\warren_eliason\channel-intelligence-platform\.worktrees\impl-step1`
- **EIF:** node N-0121, run `IMPL_step1_20261125`
- **PR:** not opened (coordinator merges)
- **Commits:** `f0874790` (API), `e6e6d54a` (web), plus the commit that adds this tracker and the column-order/width follow-up (see `git log`)

## Warren's words (verbatim)

- t454u item 1: "No, monitored listings needs to contain the matrix, everyhting else on the page works around it or above it, we can move or remove once its done."
- 25 Nov: "restore the page from 9abc4716 with the matrix as its centrepiece, on our existing grid component, sales model names, health panel kept"
- On the health panel back on the listings tab: "Yes?". On what SRP is: "Suggested Retail price".
- t445u (listings part): "... CHEAPEST AT CUSTOMER X ????? ... The matrix table looks like absolute dog shit. Dont fucking know what table theme you decided to use....but you do know we have components right???"

## Checklist

- [x] Read RULES.md, the step prompt, 00-EIF-FLOW, the audit sections
- [x] Phase A: map (below)
- [x] Phase B: read-only SRP comparison on live `cip` (below). The default rule does NOT give a clear source, so SRP shows "SRP source pending Warren"
- [x] Phase C1: listings lens order = health panel, last-check caption, old tiles, matrix, old listings table, chart row. History lens unchanged
- [x] Phase C2: 9abc4716 tests restored unchanged (they run on Monitored listings and on Price history)
- [x] Phase C3: `PriceMatrixLens` on `EnterpriseDataGrid` (pinned Product = sales model name, SRP column, one column per customer: price, age, StatusChips)
- [x] Phase C4: `PriceMatrixLens.test.tsx` (7 tests)
- [x] Phase D1-D3, D5, D6 (commit `f0874790`). D4 is waiting for Warren's SRP answer (the MAX-ever query is already removed)
- [x] Gates (below)
- [x] Visual gate, dark and light (below)

## Phase A: map (9abc4716 → base bc396c88 → this branch)

| Site | 9abc4716 | base bc396c88 (after f1a561cb/0bd7ed1b/ca8f5f7f) | this branch |
|---|---|---|---|
| imports | `ListingCaptureHealth` | + `PriceMatrixLens`, `customersListUrl`; `ListingCaptureHealth` import removed | all three |
| customers query (L358) | `/api/v1/customers?page=1&page_size=200` | `customersListUrl(true)` (reporting default, t417u) | unchanged from base (A5) |
| health panel (L919) | `pathname.startsWith('/competition') ? null : <ListingCaptureHealth />` (every non-competition lens) | removed | `lens === 'listings' ? <ListingCaptureHealth /> : null` |
| listings lens (L920) | `lens === 'listings' \|\| lens === 'history' ? (old page)` | `lens === 'listings' ? <PriceMatrixLens /> : null` + `lens === 'history' ? (old page)` | `lens === 'listings' \|\| lens === 'history' ? (old page)` with `<PriceMatrixLens />` after the tiles on `listings` only |
| search box (L1201) | `/api/v1/customers?page=1&page_size=25&q=` | `customersListUrl(false, { q })` | unchanged from base (A5) |

Old page elements (test ids): `listing-capture-health` (+ `listing-capture-health-due`), `listing-last-check`, `HeadlineStrip` tiles (Active listings, Promo live at price, Promo not at price, Price moved since first seen, Unlinked listings), the listings `EnterpriseDataGrid` with activation filter chips (`order: 1`), the Observed price chart row (`order: 2`). All present on Monitored listings again.

Tests `0bd7ed1b` rewrote: the `describe('MarketSurface real counts and the intelligence read (BACKLOG-226)')` block (set `nav.search = 'tab=observations'`), and the first `MarketSurface` test (asserted `price-matrix-lens` present and `listing-capture-health` absent). On this branch:
- the BACKLOG-226 block runs through `describe.each` on Monitored listings (search `''`, as at 9abc4716) AND on Price history (`tab=observations`, as 0bd7ed1b). Test bodies and assertions are byte-for-byte unchanged; only the `beforeEach` sets `nav.search` from the table.
- the first test is back to its 9abc4716 assertions (last-check caption, health panel due count 3, empty sites and link-pattern texts) plus `market-listings-lens`.
- kept: `shows price history lens with last-check caption, not capture health` (base), `leaves capture health off the competitor lenses`.
- added: `puts the price matrix on Monitored listings between the old tiles and the listings table (step 1)`.
- `within(...)` scoping changes: none needed (`PriceMatrixLens` is mocked in `MarketSurface.test.tsx`, as it was at base).
- Diff of the test file against 9abc4716 is additive only (`git diff 9abc4716 -- apps/web/src/features/market-listings/MarketSurface.test.tsx`).

## Phase B: SRP data mapping (read-only on live `cip`, 26 Nov 2026)

Run: `.step1-scratch/srp_profile.py` (untracked), one `SET TRANSACTION READ ONLY` transaction, rolled back, `current_database()` = `cip`. Nothing written.

Facts:
- Today is 2026-11-26 (2026 Q4). Live, not-cancelled, not-superseded line-up cases have `inferred_period_start` from 2025-01-01 to 2026-07-01 (2026 Q3). **No line-up case covers today.** Two cases have no period (`NV\Q4`, `PF\Q4`, draft_imported).
- `commercial_plan`: 0 rows. `historical_lineup_import_header`: 0 rows (0 MSRP lines).
- Reporting customers (`reports_expected`): 8. Matrix cells with an active/out-of-stock listing: 105 (Evetech 69, Takealot 36). The other 6 reporting customers have no monitored listings.

Coverage per customer (cells with a value per source):

| Customer | cells | (1) MAX msrp ever | (2) line-up case covering today | (2b) latest case started ≤ today | (3) plan target SRP | (4) historical line-up | (5) sell-through unit price | (6) listing price |
|---|---|---|---|---|---|---|---|---|
| Evetech | 69 | 57 | 0 | 44 | 0 | 0 | 0 | 69 |
| Takealot | 36 | 27 | 0 | 23 | 0 | 0 | 33 | 36 |

Before/after sample (sales model name; (2b) is shown because (2) is empty everywhere):

| Customer | Model | (1) max ever | (2b) latest case ≤ today (case, status, period, vat_pct_evidence) | (5) sell-through (vat_basis, period) | (6) listing (observed) |
|---|---|---|---|---|---|
| Evetech | E1504GA-I382B1W | 7499 | 7499 (145 po_pending 2025 Q4, 0.15) | — | 8499 (2026-11-24) |
| Evetech | FA401UM-716512G0W | 28999 | 27999 (127 po_pending 2026 Q1, null) | — | 20999 (2026-11-26) |
| Evetech | FA506NCQ-78512G0W | 19999 | 19999 (146 po_pending 2026 Q3, 0.15) | — | 17999 (2026-11-26) |
| Evetech | FA608PP-91610G0W | 44999 | 44999 (146 po_pending 2026 Q3, 0.15) | — | 39999 (2026-11-26) |
| Evetech | FX608JHI-I716512G0W | 36999 | 36999 (146 po_pending 2026 Q3, 0.15) | — | 20999 (2026-11-24) |
| Evetech | FX608JHR-I716512G0W | 27999 | 26999 (127 po_pending 2026 Q1, null) | — | 22999 (2026-11-24) |
| Takealot | E1504FA-382B0W | 10999 | 6499 (145 po_pending 2025 Q4, 0.15) | 6499 inc_vat (2025-12-29) | 7664 (2026-11-04) |
| Takealot | E1504FA-382B1W | 11999 | 9999 (123 po_pending 2026 Q3, 0.15) | 11369 inc_vat (2026-07-27) | 9900 (2026-11-04) |
| Takealot | E1504FA-58512B1W | 8999 | 8999 (145 po_pending 2025 Q4, 0.15) | — | 9999 (2026-11-04) |
| Takealot | E1504GA-N82B0W | 4999 | 4999 (145 po_pending 2025 Q4, 0.15) | 4999 inc_vat (2025-12-29) | 6999 (2026-11-04) |
| Takealot | E1504TA-N82B0W | 9999 | 8999 (123 po_pending 2026 Q3, 0.15) | 8799 inc_vat (2026-07-27) | 6872 (2026-11-04) |
| Takealot | E510KA-C42B1W | 5999 | 5999 (117 po_pending 2025 Q2, 0.15) | 4349 inc_vat (2025-09-22) | 7199 (2026-11-04) |

Reading: the prompt's default rule (line-up case covering today) gives 0 of 105 cells. Falling back to "latest case started before today" mixes 2025 Q2 to 2026 Q3 cases and VAT evidence that is 0.15 on some and null on others. That is not one clear source, so per the coordinator override no rule is invented: the API returns `srp: null`, `srp_reason: "srp_source_pending"` and the grid shows "SRP source pending Warren"; `below_srp_count` is `null` and no "Below SRP" chip can show.

## ASSUMPTIONS (not decisions)

- A1: Monitored listings order, top to bottom: `ListingCaptureHealth`; last-check caption and the old tiles (9abc4716); the price matrix (full width, 1224 px of 1224 px lens width at 1440 px viewport); the old listings table; the chart row. Nothing removed.
- A2: "Yes?" = `ListingCaptureHealth` returns to Monitored listings. It also stays on Data health → Sources. At 9abc4716 it showed on every non-competition lens; this branch restores it on Monitored listings only, and Price history stays as it is today (step prompt: "The `history` lens stays exactly as it is now").
- A3: "Cheapest at" tiles removed; no new KPIs; the old tiles are the summary.
- A4: SRP = Suggested Retail Price from the source Warren confirms; never max-ever. Pending (Phase B).
- A5: reporting-customer defaults from `ca8f5f7f` kept (customers query, search box, matrix customer picker).
- A6: highlights are `StatusChip` only (Out of stock = neutral, Below SRP = warning, promotion type = info); no cell fills (rendered: every matrix `.ag-cell` background is `rgba(0, 0, 0, 0)`).
- A7: no existing listing-capture freshness rule was found, so each priced cell shows its age (shared `attentionAge(observed_at)`, e.g. "Last data 22 days ago") with no stale flag; the full timestamp is in the cell tooltip.
- A8 (new, this session): customer columns are ordered by number of monitored listings, most first (stable, so ties keep the API's reporting order); every scoped customer keeps its column. Reason: in reporting order the first four customers (no listings) filled the visible width with dashes and pushed Evetech and Takealot off screen.
- A9 (new): the matrix uses the shared ops-list pagination (`OPS_LIST_GRID_PAGINATION`, 25 rows, selector 25/50/100) instead of `PAGINATED_GRID_PAGE_SIZE` (15), because AG Grid logs error #94/#95 when the page size is not in the selector. Grid height follows the row count up to one page.
- A10 (new): customer columns have `minWidth` 240 (was 200) so the age text and one chip fit side by side without ellipsis.

## QUESTION FOR WARREN

1. ANSWERED 26 Nov (see "SRP rule" below). Open sub-question: **the line-up price VAT basis.** The code uses line-up `msrp_local` as stored (treated as VAT inclusive, matching the line-up price chain). Phase B showed VAT evidence is 0.15 on some cases and null on others. If line-up MSRP is ex-VAT on any case, say so and the tier will gross it up. Default: as stored.
2. **Health panel on the other listing tabs?** At 9abc4716 it also showed on Price history, Promotion activation and Feed proposals. This branch shows it on Monitored listings only (A2). Default: leave it there only.

## STOP items (live writes)

None. All live `cip` access was read-only (`SET TRANSACTION READ ONLY`, rolled back): `srp_profile.py`, `matrix_payload.py`, `model_check.py` (untracked scratch).

## Gates run (26 Nov 2026)

| Gate | Command | Result |
|---|---|---|
| web tests | `node node_modules\vitest\vitest.mjs run src/features/market-listings/PriceMatrixLens.test.tsx` (from `<worktree>\apps\web`) | 7 passed |
| web tests | `node node_modules\vitest\vitest.mjs run src/features/market-listings/MarketSurface.test.tsx` | 25 passed |
| eslint | `node node_modules\eslint\bin\eslint.js` on the 4 touched web files | 0 errors, 2 warnings (`MarketSurface.tsx` L394, L855 `react-hooks/exhaustive-deps`, lines not touched, already at base) |
| tsc | `node_modules\.bin\tsc.cmd --noEmit -p .` | exit 0, 0 errors |
| build | `pnpm --dir <worktree> --filter @cip/web build` | exit 0 (run twice; second after the final web edit) |
| API DB test | `pytest tests/test_price_matrix_db.py -q` on `cip_test` (db name path printed `/cip_test`) | 1 passed |
| API unit | `pytest tests/unit/test_price_matrix.py -q` | 2 passed |
| hardcoding scan | `git diff origin/feat/integrate-20261103 -- apps` added lines vs hex/rgba, retailer names, domains, URLs, country, VAT | product code: none. Hits only in tests: `https://shop.example.test/...` fixtures and `vat_rate=0` in the DB test sample. `PriceMatrixLens.tsx` has no `rgba(`/hex (also asserted by a test) |

## Visual gate (26 Nov 2026)

Method: worktree `next dev -p 3101` proxying to the running API on :8001 (GET only), Playwright (Python, `apps/api/.venv`), sign-in via the proof-script login block, 1440 px wide, dark and light via the `cip-ui` store. The live API still runs the pre-branch matrix code, so the one `price-matrix` request was answered with the BRANCH payload built read-only from live `cip` by the branch's `build_price_matrix` (`.step1-scratch/matrix_payload.py`). Every other request (health, listings, tiles) was real :8001 data. Screenshots stayed in `.step1-scratch` (not sent). 5xx responses seen: none.

Page (both themes identical):

| Element (19 Nov baseline / 9abc4716) | Present | y (px) |
|---|---|---|
| Capture health panel (Listings due 218, Skipped 130, Sites ready 1 of 3, Link patterns 1, site table, Link discovery) | yes | 245 |
| Last-check caption | yes | 841 |
| Old tiles (Active listings 109 of 218, Promo live, Promo not at price, Price moved, Unlinked) | yes | 889 |
| Price matrix (Panel "Price comparison", 93 products × 8 customers, AG Grid `.ag-root-wrapper`) | yes, widest (1224 px = lens width) | 985 |
| Old listings table (AG Grid, filter chips) | yes (1222 px) | 2379 |
| Observed price chart row | yes | below table |
| "Cheapest at" text | absent | — |

Matrix content: Product column shows `sales_model_name` with SKU · name below; 5 rows checked against read-only SQL on `dim_product` (ids 94, 683, 1388, 1410, 2154: M1607GA-716512S0W, GU606AW-U93220G0W, CM1402CM2A-NK0242, FX608JMI-I71610G0W, PM1503CDA-R716512G0X): 5/5 match. Every priced cell shows an age (Evetech "today"/"1 day ago"; Takealot "Last data 22 days ago" = observed 2026-11-04). SRP column: "SRP source pending Warren". Chips: Out of stock (15 on page 1), no Below SRP (no SRP), no promo on page 1.

Computed styles, matrix grid vs the listings grid on the same page vs `/admin/audit-log` (another `EnterpriseDataGrid` page):

| Property | Dark: matrix / listings / audit-log | Light: matrix / listings / audit-log | Match |
|---|---|---|---|
| header background | rgba(255,255,255,0.06) ×3 | rgba(0,0,0,0.04) ×3 | yes |
| header border-bottom | 1px solid rgba(120,160,190,0.22) ×3 | 1px solid rgba(32,52,72,0.14) ×3 | yes |
| header text colour | rgba(186,198,210,0.82) ×3 | rgba(40,54,68,0.82) ×3 | yes |
| header font | 12px / 600 ×3 | 12px / 600 ×3 | yes |
| header height | 41 ×3 | 41 ×3 | yes |
| row height | 40 ×3 | 40 ×3 | yes |
| row/wrapper background | rgb(34,38,46) ×3 | rgb(255,255,255) ×3 | yes |
| row border-bottom | 1px solid rgba(120,160,190,0.22) ×3 | 1px solid rgba(32,52,72,0.14) ×3 | yes |
| cell text | rgba(245,247,250,0.96), 13px ×3 | rgba(16,22,30,0.94), 13px ×3 | yes |

Matrix panel vs mock-up `.panel` (`docs/design/dashboard-v2/index.html`; the mock-up has no table, so the table comparison is against existing grids above):

| Property | Dark mock-up / live | Light mock-up / live | Match |
|---|---|---|---|
| background | rgb(34,38,46) / rgb(34,38,46) | rgb(255,255,255) / rgb(255,255,255) | yes |
| border | 1px solid rgba(120,160,190,0.22) / same | 1px solid rgba(32,52,72,0.14) / same | yes |
| radius | 12px / 12px | 12px / 12px | yes |
| title size | 13px / 13px | 13px / 13px | yes |
| title weight | 650 / 600 | 650 / 600 | no (shared `Panel` component, all panels app-wide; not changed in this step) |
| shadow | 0 8px 28px rgba(0,0,0,.25) / none | 0 4px 20px rgba(20,35,50,.08) / none | no (shared `Panel`; theme step's scope) |

Observations (not fixed, not in scope): the last matrix row is partly under the horizontal scrollbar when 8 customer columns overflow (grid still scrolls); one Takealot cell shows price 229 (out of stock), which looks like a capture parse issue (data, not this step).

## EIF

- Lease on N-0121 reacquired this session (rev 2932) after the previous session's lease expired. Control-plane files under `.eif/` (CURRENT.md, PROGRAM.md, ROADMAP.md, WORK_ITEM.md, program/PROGRAM.yaml, program/PROGRAM_LOG.ndjson, runs/IMPL_step1_20261125/) are left uncommitted in the worktree. `.step1-scratch/` is scratch, never committed.
- Guard events this session: first call `SESSION_CLOSURE_REQUIRED` (verifier run, `SESSION_CLOSURE_OK`); `git add` with a PowerShell variable path denied `SECRET_STAGE` ("cannot show ... fail closed"), re-run as a plain literal-path command; `TaskStop` denied `SHIM_TOOL_UNMAPPED`, so the dev server I started was stopped with `taskkill /T /F /PID` per the step procedure.
- **Not recorded in the ledger (coordinator to do):** `evidence.add` (this tracker, commits `f0874790`/`e6e6d54a`/this commit), `node.stage_note`, and `node.lease.release` for N-0121. An early Bash test call used `cd <worktree>\apps\web` and the session's working directory stayed there; the programme CLI then no longer resolved as `python .eif/runtime/programme/program.py` from the root, and the absolute-path form was denied `CONTROL_PLANE_PROTECTED`. Per the rules that denial was not routed around. The lease (run `IMPL_step1_20261125`, rev 2932) expires on its own about 30 minutes after acquisition. Node stage is still `discovery` in the ledger.
- Proposed stage note: "Session 1 built and pushed (f0874790 API, e6e6d54a web, follow-up + tracker). Gates green (vitest 7+25, API DB 1 + unit 2, tsc 0, eslint 0 errors, build exit 0). Visual gate dark/light: matrix grid styles equal existing EnterpriseDataGrid pages; panel matches mock-up except shared Panel title weight/shadow. SRP pending Warren (no line-up covers today). Self-verification only; GOV-008 independent review pending."

## Resume notes

Code and tracker are pushed on the branch. Next: coordinator review (different model), merge to `feat/integrate-20261103`, backup, deploy, live proof of acceptance 1-9 on :3000 (the live API will then serve the branch matrix payload). D4 waits for Warren's SRP answer.

## Doc delta for coordinator

**BACKLOG entry** (new or update the Step 1 / listings matrix entry):

> **Listings: price matrix as centrepiece of Monitored listings (step 1, N-0121)** — Status: built on `fix/listings-matrix-centrepiece-20261125` (`f0874790`, `e6e6d54a`, `<sha>`), pending merge/deploy/live proof. Evidence: Monitored listings restored to the 9abc4716 layout (health panel, caption, tiles, listings table) with the price matrix between the tiles and the table, on `EnterpriseDataGrid`, products by `sales_model_name`, per-cell price age, StatusChip states, no Cheapest-at tiles, no colour literals; API returns `sales_model_name`, `observed_at`, in-stock-only below-SRP, no MAX-ever SRP, no `cheapest_at`; tests: PriceMatrixLens 7, MarketSurface 25, API DB 1 + unit 2; build/tsc/eslint green. TRIGGER: SRP source — Warren picks the source (Phase B table in `docs/handoffs/2026-11-24/steps/02-step1-listings-matrix-centrepiece.md`); then implement D4 (srp/srp_source/srp_reason from that source, same VAT basis as shelf prices) and the Below SRP chip lights up. TRIGGER: health panel on other listing tabs if Warren wants it back there.

**CURRENT.md lines:**

> - Listings (step 1, `fix/listings-matrix-centrepiece-20261125`): Monitored listings shows capture health, last-check caption, the old tiles, the price matrix (EnterpriseDataGrid, sales model names, price age, Out of stock / promo chips) and the old listings table. SRP column reads "SRP source pending Warren" until Warren names the SRP source. Price history unchanged.

**CONTEXT changelog line:**

> - 2026-11-26 `<sha>` Listings: Monitored listings restored to the 9abc4716 page with the price matrix as centrepiece on EnterpriseDataGrid (sales model names, price age, no Cheapest-at, SRP pending Warren) (N-0121).

## Review fixes (26 Nov)

Independent review returned READY_WITH_FIXES. Fixed: below-SRP rule now lives in one API constant (`BELOW_SRP_TOLERANCE`) and each cell carries `below_srp`; the UI reads the flag. Added API tests (in-stock, out-of-stock, boundary) and a component test for the chip. User-facing text is "SRP source not yet chosen" (reason code `srp_source_pending` kept). The promotion chip renders only when the API gives a promotion type: the web app has no production label helper, so no literal fallback. Column minWidths stay: `gridDensity` has row-height tokens only, no width tokens.

## SRP rule (26 Nov follow-up, commit d5c904b0)

Warren's words, verbatim: "use sell out price, fall back to Line up price, fall back to website off promo price."

Resolved per customer and product (`price_matrix.py`: `_sell_out_srp`, `_lineup_srp`, `_website_srp`, `resolve_srp`). Each cell returns `srp`, `srp_source` (`sell_out_price` | `lineup_price` | `website_off_promo_price`), `srp_reason`, and `below_srp` (in-stock only, `BELOW_SRP_TOLERANCE`). The highest price ever recorded is never used.

- ASSUMPTION 1 (sell-out): the latest period with a positive `unit_sell_price` on the customer's sell-through rows for that product; when several sites report that period, the row with the most units. Ex-VAT rows are grossed up with the tenant's VAT rate; unknown basis or unset rate = tier skipped (same rule as `planner_sellthrough.srp_from_price`). All tiers are stated VAT inclusive, the shelf basis.
- ASSUMPTION 2 (line-up): `msrp_local` of the customer's latest non-cancelled, non-superseded case whose period started on or before today; used as stored (VAT inclusive). Open sub-question above.
- ASSUMPTION 3 (website off-promo): the listing has no separate column for a regular price. The only stored regular price is the site's struck-through price in the latest good observation's `parse_flags.rrp_listing_price` (with `vat_basis`). That is what tier 3 reads; a site that publishes none gets nothing here. The shelf price itself is never used (it may be promotional).
- Product-level SRP column: the figure when every customer agrees, else "Varies by customer". "SRP source not yet chosen" shows only when no cell has an SRP from any tier.
- UI: each priced cell carries a caption `SRP <value> · <source label>` (Typography caption, no fills, no literals beyond the three source labels); row height factor 1.5 for the third text line.
- Tests (all pass): API DB on `cip_test` 11 (each tier winning, fallback order, VAT gross-up, ex-VAT skipped without a rate, cancelled/superseded/future line-ups skipped, website flag, in-stock-only below_srp, pending wording) + unit 2; `PriceMatrixLens` 11; `MarketSurface` 25.
- Gates: eslint clean on touched web files; `tsc --noEmit` no errors; `pnpm --filter @cip/web build` exit 0.
- Live read-only coverage (one READ ONLY transaction, rolled back, `current_database()` = cip): 100 cells with a listing (not 105; the matrix now shows scoped products only), 93 products. Sell-out 30, line-up 45, website 1, no SRP 24 (all Evetech, `no_srp_for_product`). 21 cells below SRP (42 in-stock cells have an SRP). By customer: Evetech line-up 43, none 24; Takealot sell-out 30, line-up 2, website 1.
- Observation for Warren: a Takealot cell shows listing price 229 against a sell-out SRP of 21,999 (out of stock, so not flagged). That listing price looks wrong at source; not changed here.
- Visual gate for the SRP caption (26 Nov, after the layout fix; worktree `next dev` :3101, branch matrix payload built read-only from live cip, dark and light): the first render truncated the source label ("Line-up ...") because the chip shared the line; the caption now sits on its own full-width line and the row factor is 1.75. Measured: row 70px, SRP caption 11px, colour equal to the age caption (dark rgba(186,198,210,.82), light rgba(40,54,68,.82)), 0 truncated SRP captions, 0 vertically clipped cells, every matrix cell background rgba(0,0,0,0) (no fills), 93 products x 8 customers, Below SRP 8 and Out of stock 15 chips on page 1. Mock-up comparison for the new caption: no mock-up element exists for per-cell SRP; it follows the existing age caption. Screenshots untracked in `.step1-scratch/`.
## Review fixes 2 (26 Nov)

Independent Opus review returned READY_WITH_FIXES. Warren's answers, verbatim. To "should an unaccepted draft line-up count as an SRP?": "NO". To "show the period the sell-out price came from, e.g. 'Sell-out · Jul 2026'?": "Yes please". Earlier Warren said about line-up price: "Can you not see that Line up has price ex VAT and including vat and Margin?"

1. Line-up tier ignores unaccepted cases. `_lineup_srp` now excludes by the promo path's own `_EXCLUDED_CASE` words (cancelled, rejected, superseded, draft, proposed) through `_case_status_excluded`, which also matches the stages of those words (`draft_imported`); the second status list is gone. Tests: a newer `draft_imported`, `proposed` and `rejected` case never supplies an SRP and the older accepted case does; a product priced only by a draft has no SRP. The existing fixtures now create their line-up cases as `accepted` (the model default is `draft_imported`, which is now excluded by design); no assertion was changed. ASSUMPTION: `validated` and `pending_review` still count, because Warren said "unaccepted draft" and the instruction named draft and proposed only. See QUESTION FOR WARREN below.
2. Period on the tier label. Cells carry `srp_period` (ISO start date: the sell-through period start for sell-out, the case's `inferred_period_start` for line-up, null for the website tier, which is the current price). The UI formats it with the new shared `formatMonthYear` (`lib/formatMonthYear.ts`, UTC so a date never slips a month), so the caption reads `SRP 8,499 · Sell-out · Jul 2026` and `SRP 8,499 · Line-up · Oct 2026`. The source words are now `Sell-out` and `Line-up`; no period or an unreadable one leaves the bare word. Line-up uses the month of the case start; there is no quarter key on the case, only free text `period_label`, so no "2026 Q3" form. Component tests (period shown, absent, unreadable) and API tests (sell-out, line-up, website, no SRP).
3. Line-up VAT. The tier reads `pricing_chain_json -> inputs -> srp_inc_vat_local` first and falls back to `msrp_local` when it is missing or unusable (`n/a`, 0). The ex-VAT figure (`outputs.calc_srp_ex_vat_local`) is never used. Test covers the explicit figure, an unusable value, and a chain with outputs only. Currency: no currency check is possible. Listings, customers and sell-through rows carry no currency; only the case has `currency_code`, and there is no helper to compare it with. Not skipped, not guessed; noted as a limit.
4. `BELOW_SRP_TOLERANCE`. New tenant-profile key `below_srp_tolerance` (same file mechanism as `stock_gap_highlight_units`, no table, no migration): `below_srp_tolerance(tenant_id)` returns 1.0 when unset or unusable; save refuses negatives and non-numbers, accepts 0. `price_matrix.BELOW_SRP_TOLERANCE` remains as the default alias, `is_below_srp` takes a `tolerance`. Tests on `cip_test`: default 1.0, override 100 (a price exactly 100 under is not below) and 99 (below); profile save/read/snapshot/reject tests. The key is file-editable like `soh_tolerance_pct`; it is not added to the settings API body.
5. Row height. `GRID_THREE_LINE_ROW_FACTOR` (1.75) and `gridThreeLineRowHeight(density)` now live in `theme/gridDensity.ts` beside the row metrics; the matrix uses it. New `gridDensity.test.ts`.

Live read-only coverage re-run (one READ ONLY transaction, rolled back, `current_database()` = cip): 744 matrix cells (93 products x 8 customers), 100 with a listing. Sell-out 30, line-up 45, website 1, no SRP 24 (all `no_srp_for_product`); 21 below SRP. Unchanged from before this round: the 213 `draft_imported` priced lines on live are not the latest case for any listed cell. Live priced lines by status: `po_pending` 1,948, `draft_imported` 213, `po_issued` 126; every one carries `srp_inc_vat_local`. 75 cells now carry `srp_period` (30 sell-out, 45 line-up).

Gates (worktree paths): `test_price_matrix_db.py` 15 passed (cip_test, db path `/cip_test`); `unit/test_price_matrix.py` 2 passed; `test_commercial_tenant_profile_p6_persistence.py` 13 passed; `test_auth_tenant_commercial_profile_api.py` 4 passed; vitest `PriceMatrixLens` 12, `MarketSurface` 25, `gridDensity` 2, `formatMonthYear` 3 passed; eslint exit 0 on touched web files; `tsc --noEmit` exit 0; `pnpm --filter @cip/web build` exit 0. Hardcoding scan of the diff against `origin/feat/integrate-20261103`: no colour literals, URLs, tax rates, customer names or currency codes in added source or tests. The change is text and a row-height token, so no new visual render; the caption wording was checked by component tests.

QUESTION FOR WARREN: should `validated` and `pending_review` line-up cases count as an SRP, or only accepted ones and later (`accepted`, `po_pending`, `po_issued`, ...)? Default now: they count (only draft, proposed, cancelled, rejected, superseded are out). On live there are no `validated` or `pending_review` priced lines, so nothing changes today.

Process note: one of my shell commands ran in the session root (the main checkout) and wrote two test additions there; I removed exactly those (one tracked file edited back, one untracked file deleted) and confirmed `git status` and `git diff` in the main checkout match what they were at the start.
