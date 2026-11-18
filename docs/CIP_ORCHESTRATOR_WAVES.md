# CIP orchestrator wave-order record

Recorded 2026-11-17. This is the repository wave-order record for
`C:\AI\CIP_ORCHESTRATOR_BRIEF.md` (v3, with v3.1 and v3.2 addenda).
**Waves 1, 2 and 3 are unchanged in order and scope.** Their “Work and order”
section is reproduced below from Warren's supplied source excerpt. The operational
brief remains outside this repository and was not edited. References to sections
7 and 8 below refer to that brief; its operational sections and addenda are not
reproduced here.

The **NEW FINAL WAVE follows Wave 3 and is last**. This records the waves being
completed. The nodes list and BACKLOG list remain separate; this document adds
to neither list and does not move, retarget or expand an existing wave unit.

## Existing Waves 1, 2 and 3 — unchanged source section

### Wave 1 (do first; everything independent runs in parallel)

Build a dependency and file-ownership map of all Wave 1 units before launching anything, and print it. Rules:
- Units that touch different files run at the same time.
- Where a new-build unit and an in-progress node touch the same area, close the in-progress node's part first,
  then build on it.
- A charter must exist in the ledger before a node's implementation starts; write missing charters first (docs
  commits, can run in parallel with code lanes).

**W1-A. Store and DC replenishment (N-0117).** Charter, then units:
store sales and stock; customer DC stock; DC to store needs; which distributor supplies which DC, from
distributor stock and learned lead times; slow and unsold stock with a suggested path (promote, move between
stores or customers, return to distributor; builds on the merged aged-stock work and folds in BACKLOG-227);
the store map in the On the water style; store location suggestions by one generic matcher (store label to a
place from a bundled offline dataset, licence recorded; steward confirms; no external geocoding; D-0143 as
amended); N-0108 Cover speed folds in.
Note (corrected 2026-11-18): this was written before the 2026-11-10 N-0118 step 2 apply, which loaded jobs 913 and 912 on `cip` (see `docs/memory/CURRENT.md`; their unresolved lines stay staged). Jobs 900, 906 and 907 were not applied. Reconcile the current data state before any load; do not replay this instruction blindly. Original note: store-level data for several customers is still staged, not loaded on `cip`. Do not load it. Prove the
module on `cip_test` with real staged/archived report files from this PC, and put "load staged store data
(N-0118)" in the WARREN block with its clone-proven steps.

**W1-B. Listings and competition, generic (N-0102 charter; N-0104, N-0105 and N-0106 folded into it).**
Units: the generic discovery and reader pipeline; N-0103 proposed-listings worklist and coverage lens;
N-0076 price-change and promotion-activation alerts; N-0077 competitor monitoring and price position;
suggestions from stock (in stock at a customer but no listing found; our price vs competitor price);
BACKLOG-226 folds in. Acceptance: every flagged reporting customer ends with a working reader plus proposed
listings, or a specific stated reason. Seller names and domains are data Warren supplies; list what is missing.

**W1-C. Account-manager planning: N-0088** promotion planner suggested quantities (and its plan export in the
company's own template, not per-retailer layouts).

**W1-D. Defects found 2026-11-12/13:**
- the listing polling regression/config issue reported in `LISTING_CAPTURE_CHECK_20261113.md`;
- the "Link discovery" panel rendering on every page (mount it only in Market & Listings);
- the catalogue-gap scan (truth audit L1): `scan_open_gaps_for_matches` loads every unresolved shipment row into
  Python; rewrite as SQL on the current evidence shape, parity-tested;
- row security disabled on `budget_ledger_entry` (truth audit): migration prepared and proven on `cip_test`,
  queued for Warren;
- the three stale doc pointers from the truth audit.

**W1-E. Close the in-progress nodes.** For each: independent Codex review of what is on the trunk against its
charter, fix rounds, then you record the stage in the ledger. Do not build on an unverified node.
N-0114, N-0115, N-0116 (dashboards, with the BACKLOG-217 items), N-0110, N-0111, N-0112, N-0113, N-0095,
N-0080, N-0082, N-0083, N-0096, N-0089 (only what its charter scopes for this stage).
Any of these whose remaining step is a `cip` write: prove it on `cip_test`, queue it for Warren, record the node as
waiting on that step.

### Wave 2: verify on the running web app (after Wave 1 is merged and deployed)

1. Deploy (section 8).
2. Start the test instance (section 7) on `cip_test` with the uploaded real files and any migrations still queued
   for `cip`.
3. Browser pass with Playwright, at 1280x800 and 390x844, on every route Wave 1 touched, on BOTH the live app
   (read-only use, no form submissions that write) and the test instance (full use):
   - every figure checked against a read-only SQL query on the same database;
   - every control, filter, click-through, empty state, loading state and error state exercised;
   - lab/spec comparison where a lab or spec exists: every difference listed and classified
     MIGRATE / CORRECT / BLOCKED.
4. Each defect becomes a fix unit (Wave 1 rules, Codex review, merge), then the pass is repeated for the routes
   it touched. Wave 2 ends when the pass is clean.
5. Write `docs/audits/WEBAPP_VERIFICATION_<date>.md` with screenshots referenced by path, the figure checks, and the
   defects found and fixed.

### Wave 3: then by importance and priority (Warren 2026-11-13)

1. **Phase B, straight after Wave 2:**
   - B1 CI gate on GitHub: tsc, web lint (fix BACKLOG-231 first), a fast API test subset on an ephemeral
     Postgres, on every PR into the trunk; merges require it green.
   - B2 scripted deploy step (section 8) run after every merged batch, output recorded in CURRENT.md.
   - B3 promotion to `main` on a cadence: N-0099 independent second look at self-verified closed nodes, then a
     tagged release. Warren says "promote to main" each time.
2. **Phase C:** N-0089 operations and data health (service flapping, data freshness, missing weekly reports against
   the Monday-due rule); backups (confirm nightly `cip` backups run per BACKUP_AND_DR.md, retention, a periodic
   restore test).
3. **Then remaining nodes by importance**, proposing the order to Warren first:
   real login and roles (BACKLOG-136, D-0029 Q3, N-0100) and the D-0141 starting screen and BACKLOG-229 — built
   and tested with `cip_test` users only, no accounts added to `cip`; customizable Brief/Attention; N-0097;
   N-0098; N-0072; N-0094; held DB items (NB2 index, D-0034 cleanup, BACKLOG-214 follow-ups, BACKLOG-212);
   blocked or data-gated N-0060, N-0081, N-0084, N-0063, N-0045; N-0070; N-0074 external access last.

## NEW FINAL WAVE — after Wave 3; last

Warren's instruction, 2026-11-17: these items come at the end unless a current
task has already completed and an item can fit there, or future wave tasks would
benefit from an item or would need changing because of it. This applies to the
waves being completed; nodes and backlogs are separate. The section below flags
such overlaps for Warren's consideration only. It makes no scheduling changes;
all five items remain in this Final Wave.

All items are generic platform capabilities. Nothing is built for one customer,
retailer, distributor, site or product.

- **(a) Reporting-customer line-ups and new-customer approval.** Line-ups pull
  only for reporting customers (`reports_expected`). A new customer gets a
  line-up created from database SKUs, with on-screen approval.
- **(b) Customer and period views of the master line-up.** Group the Line-up
  cases page by customer and period, with approve and reject at line-up level.
  Clicking through opens that customer's slice in the workbench, including plan
  lines and economics, as a view of the master line-up, never a copy. Keep the
  master all-customer line-up openable as it is today.
- **(c) Aged/slow stock duplication and product grouping.** Find and fix why
  the promotion planner duplicates aged/slow stock lines. Then show one line per
  product, with aged/slow reason badges and the sites folded underneath.
- **(d) Customer promotion timeline calendar.** Show our promotions alongside
  customer campaign or pillar calendars, per customer. Upload those calendars
  through the existing mapping-profile upload and show clash warnings.
- **(e) Planner layout and useful cards.** Redesign the planner using Warren's
  mock-up (timeline, case side panel, action queue) in the current CIP theming.
  Replace the top cards that duplicate the Budget ledger or other pages with
  planner-specific cards: awaiting approval, campaigns starting in the next
  4 weeks, unplanned aged-stock value, and calendar clashes.

## Read-only overlap flags — FLAGS ONLY; no moves or retargeting

Evidence checked 2026-11-17 in this worktree at
`2cb728f59b8a014e67aeadf79e9984bed1827676`, branch
`docs/final-wave-planner-lineup-feedback`: local git ancestry, current source,
the local W1-C branch diff, and GitHub PR metadata/open-PR search. PRs
[#91](https://github.com/IoTWazPresales/channel-intelligence-platform/pull/91),
[#93](https://github.com/IoTWazPresales/channel-intelligence-platform/pull/93) and
[#96](https://github.com/IoTWazPresales/channel-intelligence-platform/pull/96)
are merged and present in this HEAD; PRs
[#92](https://github.com/IoTWazPresales/channel-intelligence-platform/pull/92) and
[#95](https://github.com/IoTWazPresales/channel-intelligence-platform/pull/95)
are open. These are code/merge observations, not runtime verification or whole
wave/node completion claims. No services, database checks or implementation were
run. Programme ledgers and other worktrees were not inspected or changed.

| Existing wave work / observed state | Final Wave overlap | Flag for consideration only |
|---|---|---|
| **W1-A: merged aged-stock foundation and stock-action fixes.** Lane B #86 is in ancestry (`2d8d5796`); #96 merged at `d70c49c8`. Current `apps/api/app/services/store_dc/stock_actions.py` has `_merged_promote_lines`, grouping by product with `site_labels`, and open-action checks/locking. `apps/web/src/features/promotions-funding/AgedStockPanel.tsx` renders rows keyed by customer, product and site. | **(c), (e)** — completed subunits touch the same aged-stock code. | Strongest completed-work fit point for the duplication investigation, product grouping and unplanned aged-stock card. Existing product aggregation and duplicate-create protection do not prove the reported planner duplication is fixed. Distinguish repeated site display from duplicate persisted lines and trace the actual trigger before a future fix. No root cause or PASS is claimed here; #96 covers only its stated sub-items. |
| **W1-B: merged site onboarding #91; discovery #95 open.** `apps/api/app/services/listing_capture/autoconfig.py`, `site_onboarding.py` and `coverage.py` already read `CustomerReportConfig.reports_expected`. #95 targets reporting-customer discovery and latest reported-stock products. | **(a)** — upcoming work benefits from consistent customer eligibility. | Preserve the same reporting-customer meaning when line-up pulling is later added. Listing discovery's stock-based product set is not the database-SKU line-up creation required for a new customer. No line-up work is added to #95 or to onboarding. |
| **W1-C: quantity/export #92 open**, head `2ff65298` (`cursor/w1c-promo-qty-export-cdc2`). Its diff touches `apps/api/app/services/cpor/promo_plan_builder.py`, `apps/web/src/features/promotions-funding/PlanWorkspace.tsx`, `PromotionPlannerSurface.tsx`, `PlanTemplatesSurface.tsx` and the historical-import page. | **(c), (d), (e)** — active work touches the planner, quantities and mapping-profile surfaces. | Direct file overlap with the merged stock-action fixes and future layout work. Future product grouping must retain quantity/evidence semantics; the new timeline and side panel must retain quantity/export actions. Calendar uploads should build on the existing mapping-profile route. #92's template export does not implement campaign-calendar ingestion, clashes or the new layout. Keep #92's current quantity/export scope. |
| **W1-C product-source path; W1-E N-0080 economics review.** Current `promo_plan_builder.py` reads active master line-up rows for the customer/period before customer history. `apps/web/src/features/commercial-planner/CurrentLineupSection.tsx` groups cases by period/product line and opens case-scoped working rows. `apps/api/app/services/commercial_planner/calculator.py` imports `profit_definition.compute_profit`; `LineEconomicsWaterfall.tsx` exposes those economics. | **(a), (b)** — existing shared code and upcoming review would benefit from the master-view requirement. | Future customer/period grouping, approval and new-customer generation must preserve master row identity and the shared economics path. A customer slice must not become a second line-up or pricing calculation. Existing case browse is not proof of customer-level grouping/approval. No N-0080 stage is changed or declared complete. |
| **W1-E dashboard reviews (N-0114/15/16); Wave 3 starting screen and customizable Brief/Attention.** The source plan includes these upcoming reviews/features; current planner `PromotionPlannerSurface.tsx` has Drafts to finish, Ended, Settled book, Planned reserve and Actual support headline cards. | **(e)** — upcoming surface design benefits from the planner-specific card requirement. | Keep ownership of budget/settlement/dashboard figures in mind when designing later work. The Final Wave planner cards are awaiting approval, campaigns starting in the next 4 weeks, unplanned aged-stock value and calendar clashes. Do not turn dashboard reviews or Brief/Attention into the planner redesign. |
| **Wave 2 running-app verification** remains after Wave 1 merge/deploy, with its original routes, viewports and clean-pass exit. | **(a)–(e)** — later changes will affect overlapping routes and figures. | Its evidence can supply a before-change baseline for the Final Wave. Final Wave UI/data changes will need verification of their resulting behaviour when delivered; they do not delay, redefine or become prerequisites for the existing Wave 2 pass. |
| **Wave 3 operations/data health (N-0089) and login/roles/account visibility (N-0100).** Upcoming as ordered in the source. | **(a), (b), (d), (e)** — reporting eligibility, customer slices, approvals and calendars share customer scope. | Health work benefits from a consistent `reports_expected` definition. Login/roles work should account for customer-scoped views and approval permissions when assessing its existing scope. Future line-up approval and calendar visibility must respect that work. No account creation, permission change or expansion of either unit is made here. |

The rest of W1-D (listing polling/panel placement, catalogue-gap SQL and stale
pointers) and W1-A's map/location work have no direct Final Wave fit identified
by this check. W1-A's map subunit #93 is merged (`5bce57c1`); that does not close
W1-A as a whole. W1-D budget row security is merged in ancestry (`c1633203`);
it remains a security dependency for future approval/budget reads, not a place
to implement planner cards. Wave 3 CI, deploy, release, backups, held DB work
and the remaining named nodes retain their existing order and scope; no direct
code fit was established for them here. This check does not certify any node's
charter or completion and does not fold Final Wave work into nodes or BACKLOG.
