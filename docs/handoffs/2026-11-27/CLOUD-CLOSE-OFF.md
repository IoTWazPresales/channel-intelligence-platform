# CIP close-off — CLOUD CODE RUN (27 Nov 2026)

One file for every cloud agent. Each agent is launched with one line naming ONE unit. Do only that unit.
Trunk: feat/integrate-20261103 (origin tip 643b2892 when this was written; confirm with git).
Read first: docs/handoffs/2026-11-26/CURSOR-HANDOVER.md, docs/handoffs/2026-11-24/RULES.md, docs/memory/CURRENT.md,
the step trackers. Warren's words win over every document.
Warren (27 Nov): "I want us to write as MUCH code in the cloud for this as possible, testing can be done later".

## CLOUD LIMITS
- You have the repo only: no cip, no cip_test, no live app, no deploy, no Codex or claude CLI.
- Write the code completely. Run what needs no database: unit tests, lint, type check, web build. Write the database
  tests the unit needs and mark them "NOT RUN (cloud)". Never fake, skip or weaken a test.
- No visual gate, no merge, no deploy, no review. Push your branch and open a PR to feat/integrate-20261103 titled
  "[CODE ONLY] <unit>". Do not merge it. A later local pass runs cip_test, the visual gate, the review, the merge and
  the deploy.
- Any EIF guard denial → STOP and report the exact command and output. A cloud guard denial is a stop condition.

## HARD RULES
1. NO HARDCODING. Tenant conventions (vocabularies, rates, thresholds, timings, domains, customers, sites, labels) are
   tenant config read through existing settings/tenant-profile services, with no code fallback. A constant is allowed
   only if it is a true system invariant. List every constant you add or keep, with the reason it cannot be config.
   No customer, retailer or site names in product code.
2. Merge nothing. Never main. Commit means push. git add -- <explicit paths> only. Never commit .eif/**, .tmp/,
   scratch, proof builds, apps/web/.next-*, next-env.d.ts, tsconfig.json edits, .env*.
3. Never remove a screen. Never rewrite a test to make it pass. A test changes only when the requirement changed,
   and the report names the requirement.
4. A schema/migration need → write nothing for that item, STOP that item and report. No migration without Warren.
5. Reuse existing components and services (workbench-ui, EnterpriseDataGrid, Panel, ModuleDataSection, existing
   APIs). Use established libraries wherever they fit instead of hand-built code. Check licences and pin versions.
6. .eif/** and .cursor/** are governed: no edits, and never import, run or copy code from .cursor/hooks.
   NO LEDGER WRITES (N-0120..N-0124 already collide at seq 2929). Record node events in the unit's step tracker.
   On "EIF unresolved executed mutation failure: repair or resolve it": reply with one line and run nothing.
7. Label every claim FACT (seen in code, git or output) or ASSUMPTION. Quote Warren. Never invent a "Decision:".
   Open questions go in the WARREN block; never answer them yourself.
8. Every Python call is python -B. No git grep/grep/rg exit-1 searches in the shell; use the editor's search tools.

## FILE OWNERSHIP (units run in parallel; stay inside your files)
- U1 owns MarketSurface.tsx, PriceMatrixLens*, ListingCaptureHealth*, the capture-health endpoint, and in
  autoconfig.py only capture_health() / _site_health().
- U2 owns the planner web files (apps/web/src/features/promotions-funding/**, PromotionPlannerSurface.tsx included).
  Web only: the API part of Step 2 is done; do not touch cpor_cases.py.
- U3 owns listing_capture/discovery.py, web_discovery/**, autoconfig_schedule.py, the discovery settings, the worker
  task and schedule files, and a new SiteConfirmBar component. In autoconfig.py it does NOT touch capture_health() or
  _site_health(). It does not edit MarketSurface.tsx.
- U4 owns commercial_tenant_profile.py, promotion_type_vocab.py, profit_reservation.py, the vat_rate default in
  cpor_cases.py, and the readers of those values. Its hardcode sweep is REPORT-ONLY for files other units own.
- U5 owns the theme (cipTheme.ts and its test), PageHeader*, DomainHeader*, Panel*, the nav rail, and
  CapabilityDirectory.tsx. It does NOT touch PromotionPlannerSurface.tsx (U2 owns it; its title is done after U2).

## UNITS
U1 MONITORED LISTINGS — branch fix/listings-health-and-filters-20261126 from the origin trunk.
 - FACT: "Cheapest at" first appears in f1a561cb (24 Nov), the commit that created PriceMatrixLens. The pre-matrix
   page 9abc4716 has none of it. Warren: "cheapest at is NOT supposed to be in there". Do NOT restore it,
   "Products monitored" or "Prices below SRP".
 - Show ListingCaptureHealth on Discover sites and Feed proposals only, not on Monitored listings
   (MarketSurface.tsx:919). ASSUMPTION to report: both tabs.
 - Access scope: GET /listing-capture/capture-health (listing_capture.py:283) opens a plain SessionLocal(). From code,
   establish whether its counts honour the caller's product-line access the way other listing endpoints do. If not,
   fix it the way those endpoints do, and write the cip_test test with a product-line-scoped user (NOT RUN).
   If the w1d-listing-poll work is needed, its files are only on Warren's PC: say so instead of guessing.
 - Matrix grid through EnterpriseDataGrid, the way other grids do it: floating filters, quick search, a sales model
   number column, spec columns from dim_product where present. Inventory existing grid features first.
   SRP chain, labels and below-SRP tolerance (tenant profile) unchanged.
U2 STEP 2 PLANNER — continue on origin/fix/planner-sellthrough-calendar-20261125 (tip 5444352f). No new branch.
 Merge the origin trunk in. Finish the web work to the mock-up (docs/design/planner/) and the brief
 (docs/handoffs/2026-11-24/briefs/step2.md). Where the mock-up answers one of the open questions in the step 2
 tracker, follow it. Otherwise keep current behaviour and list the question for Warren. Promotions are sell-through
 only. No closed/settled/ended cases by default. Push to the same branch and open the PR.
U3 STEP 3 DISCOVERY — continue on origin/feat/discovery-autodiscover-20261125 (tip 5f2d6971).
 - SCHEDULED_RUN_DEBOUNCE (24 h) and CONFIRM_COALESCE_SECONDS (120) become tenant settings in the existing Discovery
   settings (next to the saved pacing values), required when the schedule is on, with no code fallback. If that needs
   a migration → STOP that item and report.
 - FACT: web_discovery/ uses crawlee+playwright, ddgs, extruct, price-parser, tldextract, protego.
   discovery.py (product-page discovery) uses none of them: html.parser plus regex for sitemaps (_sitemap_urls) and
   search forms, and its own site_fetch. Move it onto the same stack: Crawlee fetching (robots via protego, pacing
   kept), ultimate-sitemap-parser, selectolax, courlan/w3lib, Babel for tenant-locale prices
   (docs/audits/LIBRARY_REVIEW_20261124.md). trafilatura and curl_cffi only if a named site fails without them.
 - Auto-discover whenever services are up. Customers added on the matrix (outside reporting) are discovered too.
   Domain/site detection per Warren: search by sales model, part code and description, take the top 2-3 results,
   compare the domain to the customer name and the tenant country/domain endings, use that domain's URL patterns.
   Free search only. No seeded defaults (the old listing_seed design is not a source). Exact barcode/model match.
   No fuzzy linking.
 - Build SiteConfirmBar as a component with its tests. Do NOT mount it (U1 owns MarketSurface.tsx). Write the exact
   mount instruction in the step 3 tracker.
 - Run apps/api/scripts/ops/prove_discovery_libraries.py with python -B if the cloud machine can. Label the output
   "cloud Linux, not the real runtime". The Windows proof is local, later.
 - The before/after proposal counts on cip_test are a local task: write the script, mark it NOT RUN. NO live writes.
U4 HARDCODE REMOVAL — branch fix/tenant-config-hardcodes-20261126 from the origin trunk.
 - FACT: 15% VAT still built in at commercial_tenant_profile.py:183 and :1103-1108 (silent fallback),
   cpor_cases.py:501, profit_reservation.py:56, and the column default at commercial_planner.py:52.
   Rule (R-05): tenant rate only, no implied 15%; unset → the existing vat_rate_not_configured flag path.
   The column default is a schema change → STOP that item and report.
 - CPOR promotion types and channels (promotion_type_vocab.py) become tenant config with today's values as this
   tenant's saved config. If that needs a migration → STOP and report. Case statuses stay code (system lifecycle).
 - Sweep the trunk for other tenant conventions in code. Fix them inside U4's files; list the rest.
U5 STEP 4b THEME — branch fix/theme-shared-components-20261126 from the origin trunk.
 - PageHeader renders a real h1. Warren approved the test change (26 Nov, "Yes"): PageHeader.test.tsx asserts h1
   because the requirement changed (the dashboard-v2 mock-up title is an h1), not to make a test pass.
 - Dead data-cip-tone selector (and its cipTheme.test.ts assertion, for the same reason).
 - /directory (CapabilityDirectory.tsx) title through PageHeader/the theme h1. /promotions waits for U2.
 - Panel title weight and shadow to dashboard-v2 (weight 650, var(--shadow)) through the theme, not per page.
 - Rail count-chip overflow: a three-digit count beside "PROMOTIONS & FUNDING" must not overflow the 244px rail.

## REPORT (in the PR description and the agent's final message)
Branch, sha, PR number, files, every constant kept or added (with reason), tests run and output, tests NOT RUN,
anything stopped and why, and a "LOCAL FINISHING" list: the cip_test runs, the visual gate, the review, the merge,
the deploy. Then one WARREN block with only the decisions he must make.
