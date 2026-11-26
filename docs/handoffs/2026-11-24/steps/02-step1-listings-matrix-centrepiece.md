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

1. **Which source is SRP (Suggested Retail Price) in the price matrix?** No line-up case covers today (latest is 2026 Q3), there are no commercial plans and no historical line-ups; see the Phase B tables.
   - Option a: the latest non-cancelled, non-superseded line-up case for that customer whose period started on or before today (covers 44/69 Evetech and 23/36 Takealot cells; mixes quarters and VAT evidence).
   - Option b: only a line-up case covering the current quarter (covers 0 cells today; SRP would show "No SRP" until a Q4 line-up is loaded).
   - Option c: another source you name.
   - Default until you answer: "SRP source pending Warren" in the SRP column, no Below SRP flags. D4 (VAT basis check) is done after your answer.
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

## Resume notes

Code and tracker are pushed on the branch. Next: coordinator review (different model), merge to `feat/integrate-20261103`, backup, deploy, live proof of acceptance 1-9 on :3000 (the live API will then serve the branch matrix payload). D4 waits for Warren's SRP answer.

## Doc delta for coordinator

**BACKLOG entry** (new or update the Step 1 / listings matrix entry):

> **Listings: price matrix as centrepiece of Monitored listings (step 1, N-0121)** — Status: built on `fix/listings-matrix-centrepiece-20261125` (`f0874790`, `e6e6d54a`, `<sha>`), pending merge/deploy/live proof. Evidence: Monitored listings restored to the 9abc4716 layout (health panel, caption, tiles, listings table) with the price matrix between the tiles and the table, on `EnterpriseDataGrid`, products by `sales_model_name`, per-cell price age, StatusChip states, no Cheapest-at tiles, no colour literals; API returns `sales_model_name`, `observed_at`, in-stock-only below-SRP, no MAX-ever SRP, no `cheapest_at`; tests: PriceMatrixLens 7, MarketSurface 25, API DB 1 + unit 2; build/tsc/eslint green. TRIGGER: SRP source — Warren picks the source (Phase B table in `docs/handoffs/2026-11-24/steps/02-step1-listings-matrix-centrepiece.md`); then implement D4 (srp/srp_source/srp_reason from that source, same VAT basis as shelf prices) and the Below SRP chip lights up. TRIGGER: health panel on other listing tabs if Warren wants it back there.

**CURRENT.md lines:**

> - Listings (step 1, `fix/listings-matrix-centrepiece-20261125`): Monitored listings shows capture health, last-check caption, the old tiles, the price matrix (EnterpriseDataGrid, sales model names, price age, Out of stock / promo chips) and the old listings table. SRP column reads "SRP source pending Warren" until Warren names the SRP source. Price history unchanged.

**CONTEXT changelog line:**

> - 2026-11-26 `<sha>` Listings: Monitored listings restored to the 9abc4716 page with the price matrix as centrepiece on EnterpriseDataGrid (sales model names, price age, no Cheapest-at, SRP pending Warren) (N-0121).
