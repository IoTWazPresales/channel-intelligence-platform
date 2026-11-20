# Opus review of merged PRs #123 to #129 (2026-11-20)

Reviewer: Opus (read-only; this file is the only write). Code read at the repo root, `feat/integrate-20261103` @ `4ca70b68`.
Inputs: `terminals/prs-20261120/pr12{3..9}.{json,diff}`, `terminals/rules-20261120.txt`, `docs/BACKLOG.md`,
`.worktrees/live-screen-audit-20261119/docs/audits/LIVE_SCREEN_AUDIT_20261119.md` (the audit the PRs cite; it is not on the
integration branch).
Method: Read, Grep, Glob and git read commands only. Nothing was executed (no pytest, vitest, browser or DB). Wherever a
claim depends on running code or live data, it is marked **UNVERIFIED** and the check that settles it is given.

Requirements used:
- #123 BACKLOG-262 / audit 1.3: line-ups show reporting customers only.
- #124 BACKLOG-263 / audit 1.1 + N9: fast listing intelligence, real counts.
- #125 BACKLOG-254 / audit 1.4 layout + N9: planner layout matches the mock-up, counts never show 0 while loading.
- #126 BACKLOG-264 / audit 1.2: offline pin proposals and steward confirm.
- #127 BACKLOG-265: planner uses sell-through only for every figure.
- #128 T1a and #129 T1b: speed only, same output.

---

## 1. Grok's small-errors list

### G1. `/lineup` overview header and the shipped-vs-plan chart count all customers: **CONFIRMED (in code)**; size on live UNVERIFIED

Evidence:
- `/lineup` is `PlanningChrome` + `PlanningOverview` (`apps/web/src/app/(app)/lineup/page.tsx:6-11`). Both read
  `GET /api/v1/planning/overview` (`PlanningChrome.tsx:26-37`, `PlanningOverview.tsx:22-26`).
- The header meta `"{cases} cases · {lines} lines"` (`PlanningChrome.tsx:34-37`) and the Plan units / Lines not ready
  tiles come from `planning_overview.py:106-161`. Those statements count `commercial_lineup_case` and
  `commercial_lineup_line` with **no reporting predicate**: only superseded, cancelled and row_status are filtered
  (`planning_overview.py:155-157`).
- The "Shipped vs plan by customer" chart (`PlanningOverview.tsx:108-128`) and the "Shipped vs plan" tile use
  `_shipped_vs_plan` (`planning_overview.py:63-97`). It calls `collect_execution_rows`
  (`plan_vs_executed.py:814`), which reconciles every linked active case. Nothing restricts it to reporting
  customers, and `_customer_plan_shipped` (`planning_overview.py:45-60`) buckets every customer.
- #123 added `reporting_plan_items_clause()` only to `fact_lineup_plan_item` reads (`lineup.py:152`,
  `budget_position.py:125`). The shared reader `reporting_customer_ids_select()` is used nowhere in
  `planning_overview.py` or `plan_vs_executed.py` (grep over `apps/api/app`).
- The same gap is on `/lineup/cases`: its "Plan coverage" tile reads `/api/v1/plan-vs-executed`
  (`LineupContainer.tsx:39-47, 151-156`), which is also unfiltered. The "Net requirement" tile is product-level
  ("Master scope") and is outside this rule.

Caveat: audit item 1.3 measured the 1,470 non-reporting rows in `fact_lineup_plan_item`. How many
`commercial_lineup_line` / linked-case rows belong to non-reporting customers on live is **UNVERIFIED** (no DB access).
The code defect stands either way: the page's header and chart do not apply the rule its sub-page now applies.

Fix (Lane A):
1. In `planning_overview.py`, load the reporting ids once (`await db.execute(reporting_customer_ids_select())`).
   Add `AND l.customer_id = ANY(:reporting_ids)` to the `line_row` SQL (`:124-161`). Count cases with
   `EXISTS (a line of the case whose customer is reporting)` (`:106-113`).
2. In `_shipped_vs_plan`, keep only rows whose `customer_id` is a reporting id. Do this before
   `compute_scorecard_from_execution_rows` and `_customer_plan_shipped` (`:82-96`).
3. Decision needed from Warren: the tile's caption claims "same grain as Execution vs plan". Either
   `/stock?lens=execution` gets the same filter, which is better done as an opt-in `reporting_only=True` argument on
   `collect_execution_rows` so both screens use one path, or the caption changes. Rows with no customer
   ("Unattributed") also need a decision: show or hide.
4. Add a unit test like `tests/unit/test_lineup_reporting_reads.py` that asserts the reporting predicate on the
   overview SQL.

### G2. Duplicate `brief/signals` call from FundingChrome: **CONFIRMED**

Evidence:
- `FundingChrome.tsx:95-99` queries `/api/v1/brief/signals` under the key `['brief','signals-meta']`.
- `AppShell.tsx:77` (mounted on every page) reads the same URL through `useBriefSignals()`. That hook's key is
  `briefSignalsQueryKey(choice)` = `['brief','signals',on|off|default]` (`useBriefSignals.ts:25-31`,
  `lib/myAccounts.ts:72-77`).
- The keys differ, so every `/promotions*` page fires the request twice. #129 merged AppShell and OverviewChrome onto
  one key (pr129.diff:2813-2814) but missed FundingChrome.
- Side effect: My-accounts toggling invalidates the prefix `['brief','signals']` (`MyAccountsBar.tsx:21`), and
  `'signals-meta'` does not match it.
- On the planner page `/promotions`, FundingChrome is rendered with `hideDomainHeader`
  (`PromotionPlannerSurface.tsx:390`). Its `briefMeta` and `portfolio` results (`FundingChrome.tsx:90-99, 107-119`)
  only feed the hidden header meta, so on that page both requests are wasted outright.

Fix (Lane B): replace `FundingChrome.tsx:95-99` with `const { data: briefMeta } = useBriefSignals();` (shared key, no
second request). Add `enabled: !hideDomainHeader` to the `portfolio` query (`:90-94`). Add a vitest that counts
`apiGet('/api/v1/brief/signals')` calls with AppShell and FundingChrome mounted together (expect 1).

### G3. `test_application_has_no_declared_site_literals` "fails only in worktrees": **REFUTED as described**. Root cause found.

It is not a worktree property. PR #127 added a test fixture with the marketplace literal `"fixture"`.

Mechanism:
- The test (`tests/unit/test_listing_discovery_review.py:410-428`) builds its forbidden-key set from
  `_declared_site_keys()` (`tests/test_listing_site_autoconfig.py:940-970`).
- That function harvests every `marketplace="..."` / `"marketplace": "..."` literal in **all** test files
  (`:943-951`). It drops only `"test"` and keys shorter than 4 characters (`:936, 969-970`).
- #127 added `tests/test_planner_sellthrough_db.py:79`, `marketplace="fixture"`. So `"fixture"` became a forbidden
  site key.
- The word "fixture" (with non-alphanumeric boundaries) appears in about 25 app lines, for example
  `app/api/v1/endpoints/cpor_cases.py:683,806`, `app/services/cpor/intelligence_scope.py:1`,
  `app/services/customer_test_fixtures.py:1,4,8,25`, `app/services/planning_overview.py:264`
  and `app/services/stock_leaves_honesty.py:4`. So `hits != []`.
- Why it looked worktree-only: #127, #128 and #129 were each tested in a worktree that contained the new test file,
  while the "main checkout" run used the root checkout before #127 was merged there. At `4ca70b68` the root checkout
  contains the file too, so the test is expected to fail there as well. **UNVERIFIED by execution**: run
  `pytest apps/api/tests/unit/test_listing_discovery_review.py::test_application_has_no_declared_site_literals` at the root.
- The DB twin `test_no_site_literals` (`test_listing_site_autoconfig.py:973-1004`) uses the same key set, so it is
  expected to fail on cip_test for the same reason.

Secondary, latent, and a real worktree-only difference: `_CONFIG_SKIP_DIRS` contains `.worktrees` (`:937`) and is
tested against the **absolute** `path.parts` (`:961`). Inside `.worktrees/<lane>/` every scripts or docs config file is
therefore skipped. No tracked or ignored config declares a `site_key` today (grep over `scripts`,
`apps/api/scripts` and `docs` `*.json|*.yaml|*.yml`), so this changes nothing yet. It will once one does.

Fix (Lane C, tests only):
1. Change `test_planner_sellthrough_db.py:79` to a key already in the declared set, such as `marketplace="shop-a"`.
2. In `_declared_site_keys`, test `path.relative_to(root).parts` instead of `path.parts` (`:961`).
3. Re-enable the test in every lane's check list. See R-10.

---

## 2. Findings per PR

Severity: **blocker**, **major** or **minor**. "pre-existing" means the defect is older than #123 but sits on a path
these PRs touched or rely on.

| ID | PR | File:line | Sev | Finding and evidence | Concrete fix |
|---|---|---|---|---|---|
| R-01 | #123 | `apps/api/app/services/planning_overview.py:106-161, 63-97`; `apps/web/src/features/lineup/LineupContainer.tsx:39-47` | major | G1 above. The `/lineup` header, Plan units tile, shipped-vs-plan chart and the `/lineup/cases` Plan coverage tile ignore the reporting-only rule. | G1 fix steps 1-4. |
| R-02 | #129 (missed) / #125 | `apps/web/src/features/promotions-funding/FundingChrome.tsx:90-99` | minor | G2 above. Duplicate `brief/signals` on every Promotions page; the portfolio and brief queries are wasted when `hideDomainHeader` is set. | `useBriefSignals()`; `enabled: !hideDomainHeader` on portfolio; a call-count test. |
| R-03 | #127 | `apps/api/tests/test_planner_sellthrough_db.py:79`; `apps/api/tests/test_listing_site_autoconfig.py:961` | major | G3 above. The site-literal guard is red on the integration branch, so it no longer protects the "no hard-coded site" rule. | G3 fix 1-3. |
| R-04 | #127 | `apps/api/app/services/cpor/planner_sellthrough.py:344-353`; `promo_plan_builder.py:633, 1303-1304`; `store_dc/stock_actions.py:347-366` | major | The planner and aged-stock Promote now put the sell-through `unit_sell_price` into `CporCaseLine.srp`. The waterfall treats `srp` as **VAT-inclusive** and divides by `1 + vat_rate` (`cpor/waterfall.py:20-27`). The price read does not select `ST.vat_basis`, although the cost read does (`:357`), and the model stores it (`fact_customer_sellthrough.py:58`). #127's own fixture uses `vat_basis="ex_vat"` (`test_planner_sellthrough_db.py:99`). Where a customer reports ex-VAT prices, dealer price is understated by the VAT factor and support per unit is overstated. Live mix of `vat_basis` on price rows is UNVERIFIED. | Select `ST.vat_basis` in the price read and return `price_vat_basis`. Before using a price as `srp`, gross an `ex` basis up by the tenant `vat_rate_pct` (tenant profile key, `commercial_tenant_profile.py:165`). Leave `inc` as is. For an unknown basis, return the price as unavailable with reason `price_vat_basis_unknown`. Reuse `_vat_kind` (`cpor/customer_soh_check.py:53-60`). Add DB tests for each basis. |
| R-05 | pre-existing (rule) | `apps/api/app/services/cpor/promo_plan_builder.py:1304`; `cpor/customer_soh_check.py:45`; `store_dc/place_name.py:27` | major | Country-specific hard-codes on paths #126 and #127 extend: `vat_rate=0.15` on every planner-written line, `VAT_INCL_DIVISOR = Decimal("1.15")`, and a South-Africa-only gazetteer `data/za_populated_places.csv` (added in `b2c5be6e`, before #126). Violates "nothing country-specific; tenant country from tenant settings". | Line VAT comes from the tenant profile `vat_rate_pct`. The places file is chosen from the tenant's country setting (`data/<country>_populated_places.csv`). With no file for that country, return `_manual("no_gazetteer_for_country")` instead of matching ZA names. |
| R-06 | #123 (pre-existing endpoints) | `apps/api/app/api/v1/endpoints/lineup.py:396-406, 241-273, 382-393` | major | `POST /lineup/items/clear-all` deletes **every** `fact_lineup_plan_item` row: no tenant filter, no role check, and no reporting clause. After #123 the 1,470 non-reporting rows are invisible on screen but still deleted by this button. `group-approval` and `PATCH`/`DELETE /items/{id}` act on non-reporting rows when called directly. BACKLOG-262 lists these as "Left open (3)". | Apply `reporting_plan_items_clause()` and the tenant filter to `clear-all`, plus `require_roles(Role.STEWARD)`. In `group-approval`, `PATCH` and `DELETE`, refuse a non-reporting customer with `REASON_NOT_REPORTING` / `REFUSAL_MESSAGE` (reuse `services/lineup/reporting_gate.py`). The deletion of the 1,470 rows stays the separate, approved data step. |
| R-07 | #125 | `apps/web/src/features/promotions-funding/PromotionPlannerSurface.tsx:409` | minor | The "Create promotion plan" tooltip says "Uses that customer's lineup or their own history". After #127 the proposal comes from sell-through only (`promo_plan_builder.py:95-133`). The "Low stock risk" queue caption ("no source feeds it yet") is also out of date: #127 now gives customer cover from sell-through. | Tooltip: "Propose lines from the customer's own sell-through (products, price, run rate); never other customers." Check the Low stock risk caption against `planner_sellthrough.figures_from_rows` `cover_weeks`. |
| R-08 | #127 | `apps/api/app/services/lineup/budget_position.py:106-125` vs `promo_plan_builder.py:166-195` | minor (needs decision) | The Planned reservation is now "Not available" in the planner, while the line-up budget-position screen still derives one from line-up units and SKU assumptions, so two screens disagree on the same figure. | Warren decides: either the budget position also shows "Not available (being rebuilt on sell-through)", or the planner caption names the budget-position figure as the line-up-based one. |
| R-09 | #123, #127 | `docs/BACKLOG.md` BACKLOG-262 / 263 / 264 rows | minor | BACKLOG-262 "Left open (2)" (the reservation fallback to `CommercialLineupLine`) is obsolete after #127. #127 removed the reporting clause #123 added to `derive_planned_reservation_sync`, because the function no longer reads plan items. The DoD lines cite "390x844", but mobile is out of scope (rules). | Update the BACKLOG rows: drop the 390x844 requirement and mark 262 (2) superseded by 265. |
| R-10 | #127, #128, #129 | PR bodies ("1 deselected ... environment-only") | major (process) | Three PRs deselected a failing guard test as "environment-only" without a root cause. That masked R-03, which violates "DONE means proven". | The orchestrator re-runs the full unit suite at the root on the integration head. A deselect needs a written root cause in the PR body. |
| R-11 | #129 | `apps/api/app/services/brief_swr_cache.py:31, 46` | minor | `StaleWhileRevalidate._store` never evicts. `query/shared_reads.py:27,43-50` keys it by sha256 of tenant, args and scope (role, product lines, My-accounts ids), so every distinct widget filter or user scope stays in memory for the life of the worker. | On `get`, drop the entry when `age >= stale`. Cap the store (for example 1,024 keys, oldest out first). |
| R-12 | #129 | `apps/api/app/services/brief_signals.py:42-43, 248-274, 513-544` | minor | Sell-through attention and promo-not-activated badges are served up to 30 min stale (`stale_seconds=1800`), and nothing clears them when an import or listing poll finishes. After a load, the badge can contradict the screen it links to. | Expose `invalidate(tenant_id)` on both caches and call it from import-job completion and the listing poll. Or lower `stale_seconds` to 300. |
| R-13 | #124 | `apps/web/src/features/market-listings/MarketSurface.tsx` (`LISTINGS_PAGE_SIZE`/`LISTINGS_MAX_PAGES` loop); `apps/api/app/services/listing_capture/intelligence_v1.py:192-235` | minor | The grid still pulls every listing client-side in up to 25 sequential requests, and each request re-runs the two count statements (`listing_capture.py` `listing_counts`). The intelligence window functions sort the whole `listing_observation` table twice. This is fine at 218 listings / 150k readings (3.3 s measured by the author) but grows linearly. | Short term: send `include_counts=false` on pages 2 and up. Check that an index on `listing_observation (listing_id, fetched_at DESC, id DESC)` exists, and add one if it does not. Longer term: server-side grid paging. |
| R-14 | #126 | `apps/api/app/services/store_dc/map.py:264-282` | minor | `_write_pin` sets `confirmed_at`/`confirmed_by` only when it **creates** a `CustomerLocation`. A steward confirming a proposal on an existing location row records no confirmer, so the new steward-confirm path has an audit gap. | Set `match.confirmed_at = now` and `match.confirmed_by = actor` on every coordinate write. |
| R-15 | #128 | `apps/api/app/services/commercial_planner/lineup_po_reconciliation.py:167-170`; `apps/web/src/features/plan-vs-executed/PlanVsExecutedView.tsx:242-252, 276-289` | minor | `_reconcile_case_inner` now has no production caller; only `tests/test_shipment_strict_pair.py:879` calls it. The seeded PvE key repeats the 9-part `queryKey` literal by hand, so a future key change silently brings the second request back. | Move the test to `reconcile_case` and delete `_reconcile_case_inner`. Extract `pveQueryKey(from, to, …)` and use it in both places. |
| R-16 | pre-existing | `apps/web/src/features/lineup/LineupTrendInstrument.tsx:6-15`; `LineupReadStrip.tsx:60` | minor | Dead components (no importers, grep over `apps/web/src`): hard-coded fake plan/ship bars and a hard-coded "26Q3 lineup" string. They are not on screen, but they would show fake data if remounted. | Delete both files. |

Checked and clean (no finding):
- **`@pytest.mark.anyio`**: every new async DB test is marked. `test_lineup_reporting_filter_db.py` 3/3,
  `test_planner_sellthrough_db.py` 4/4, `test_t1a_reconcile_batch_db.py` (module `pytestmark`, `:37`), and all five
  `test_t1b_*_db.py` (1-2 each).
- **New UI or chart libraries**: no `package.json` change in any of #123-#129. #125 reuses MUI and workbench-ui.
- **Fuzzy joins**: none added to data joins. #126's fuzzy place match is a proposal only. Confirm recomputes the
  proposal server-side (`map.py:368-384`). "Select high confidence" excludes ambiguous proposals and anything below 0.8
  (`pinProposals.ts:60-66`), and the maximum fuzzy confidence is 0.75 (`place_name.py:249`), so fuzzy proposals always
  need a person. The routes are steward-only (`store_dc.py:259-284`). The `.like(` hits in #129 are test teardown only.
- **Hard-coded customers, retailers or sites**: none added in non-test code. The #126 matcher removes customer words
  taken from the data (`place_name.py:89-110`).
- **#128 batch reconcile**: a fixed query count, chunking at the 100-id cap on the client
  (`useCaseReconciliations.ts:13-38`), and single-case 404 semantics kept (`reconcile_case`, `:123-129`).
- **#129**: the shared-read keys include tenant, role, product lines and My-accounts (`query/shared_reads.py:31-50`).
  `gather_reads` sessions inherit the product-line row-security scope through the global `after_begin` listener
  (`core/product_line_scope.py:128-169`). Handlers copy rows and do not mutate the shared payload
  (`a1_pve.py:126-146`, `a2_cpor.py:117-126`).

---

## 3. Could not verify

1. Live magnitude of R-01: the share of `commercial_lineup_line` / linked-case rows that belong to non-reporting
   customers. Needs a read-only count on a cip clone. Not run (rule: never touch live cip).
2. R-03's predicted failure at the root checkout and on cip_test. Not executed (read-only brief).
3. R-04's live impact: the split of `fact_customer_sellthrough.vat_basis` on rows with `unit_sell_price > 0`.
4. Any rendered-screen claim: nothing was rendered at 1280x800. The **map date/filter bar overlap (Lane 1, store
   map)** was not seen because nothing was rendered. It stays with Lane 1.
5. Whether `sell_through_attention` applies My-accounts internally. The cache key includes the ids
   (`brief_signals.py:261`), so it is correct either way; only the cache hit rate differs.

---

## 4. CONFIRMED defects ready for fix lanes (grouped so files do not overlap)

| Lane | File area (exclusive) | Defects | Sev | Notes |
|---|---|---|---|---|
| A: Planning overview reporting-only | `apps/api/app/services/planning_overview.py`; `apps/api/app/services/commercial_planner/plan_vs_executed.py` (opt-in `reporting_only` arg only); new `apps/api/tests/unit/test_planning_overview_reporting.py` | R-01 (G1) | major | Needs Warren's call on Execution vs plan and "Unattributed" (G1 step 3) before the PvE part. The overview filter can ship first. |
| B: Promotions chrome | `apps/web/src/features/promotions-funding/FundingChrome.tsx` (+ test); `PromotionPlannerSurface.tsx` (tooltip/caption only) | R-02 (G2), R-07 | minor | Web only. |
| C: Site-literal guard | `apps/api/tests/test_planner_sellthrough_db.py:79`; `apps/api/tests/test_listing_site_autoconfig.py:961` | R-03 (G3), R-10 (re-enable) | major | Tests only. Then re-run the full unit suite at the root. |
| D: Planner price VAT basis | `apps/api/app/services/cpor/planner_sellthrough.py`; `cpor/promo_plan_builder.py` (srp + `vat_rate` from tenant profile); `store_dc/stock_actions.py` (`_srp_for_line`); `cpor/customer_soh_check.py` (helper reuse only) | R-04, R-05 (VAT part) | major | One lane, because the srp and vat_rate fixes touch the same lines. Add DB tests per basis on cip_test. |
| E: Line-up write endpoints reporting-only | `apps/api/app/api/v1/endpoints/lineup.py` (write routes only); `apps/api/app/services/lineup/reporting_gate.py` | R-06 | major | Must land before or with the approved deletion of the 1,470 rows. |
| F: Store pins | `apps/api/app/services/store_dc/map.py` (`_write_pin`); `apps/api/app/services/store_dc/place_name.py` (country-from-tenant gazetteer) | R-14, R-05 (gazetteer part) | minor / major | Overlaps the Lane 1 store-map **web** files, not these API files. Coordinate with Lane 1, which owns the date/filter bar overlap. |
| G: Caches | `apps/api/app/services/brief_swr_cache.py`; `apps/api/app/services/brief_signals.py` (cache wiring only); the import-completion hook call site | R-11, R-12 | minor | |
| H: Cleanup | `apps/api/app/services/commercial_planner/lineup_po_reconciliation.py` (`_reconcile_case_inner`), `apps/api/tests/test_shipment_strict_pair.py`; `apps/web/src/features/plan-vs-executed/PlanVsExecutedView.tsx` (key helper); delete `LineupTrendInstrument.tsx` and `LineupReadStrip.tsx` | R-15, R-16 | minor | Lane A touches `plan_vs_executed.py` (API) only; H touches the PvE **web** file only. |
| I: Market paging | `apps/web/src/features/market-listings/MarketSurface.tsx`; `apps/api/app/api/v1/endpoints/listing_capture.py` (`list_listings` counts flag) | R-13 | minor | Index check is a migration decision: escalate rather than add one silently. |
| Docs | `docs/BACKLOG.md` (262/263/264/265 rows) | R-08 (decision record), R-09 | minor | Orchestrator or docs lane, after the decisions. |

Summary of Grok's list: G1 CONFIRMED (code; live size unverified). G2 CONFIRMED. G3 REFUTED as "worktree-only": the
real cause is #127's `marketplace="fixture"` test literal, with a latent absolute-path skip bug as a secondary issue.
