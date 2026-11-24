# CIP audit: what went wrong today and how to fix it (24 Nov 2026)

## What I touched while auditing

I made no changes to the repo or the database, ran no `git fetch`, and printed no secrets. Three things to disclose:

- **Guard check.** The EIF guard blocked my first shell call with `SESSION_CLOSURE_REQUIRED`. I ran the exact command it gave: `python -B .cursor/hooks/eif_guard.py --verify-closure 2324…9275 ad7c…bf1`. The result was `SESSION_CLOSURE_OK` (ledger `db3dd752`, remote head `ca8f5f7f`).
- **One stray file outside the repo.** One command saved the committed mockup HTML to `%TEMP%\x` with `Out-File`. It holds no secrets. I left it there because deleting is also prohibited. The coordinator can delete it.
- **No database queries by me.** Every database fact below comes from the earlier read-only audit's SQL output (`terminals\audit-20261124-recovery-sql.txt`). Everything else comes from code, git, briefs, progress notes and proof files.
- **No PR data.** `gh` is not installed.

## Summary

- **Most of today's damage came from the coordinator's briefs and checks, not from Cursor going rogue.** The listings page swap, keeping "Sell out PP" in the planner, keeping 2024 ended cases, and the "cheapest at" tiles were all written into the briefs. The checks then tested the brief, not Warren's words or the mockups.
- **Two safety nets fired and were overridden.**
  - Six existing listings-page tests failed because the old page was gone. The fix-up brief told Cursor to rewrite those tests ("Do not revert the matrix").
  - The coordinator's live check at 14:53 measured page titles at 15px against a 27px mockup and noted the background gradient was missing. The change shipped anyway.
- **composer-2.5 added its own errors on top.**
  - It mapped the mockup's "h1 27px" onto MUI's unused `h1` style and shrank the `h5` style that page titles actually use.
  - It used a raw table with hard-coded colours.
  - It showed sku and name instead of `sales_model_name`.
  - It invented a pricing rule: SRP is the highest list price ever recorded.
  - It shipped a crash (`UnboundLocalError`) that a single test run would have caught.
- **Three facts in the earlier audit need correcting.**
  - Discover had been run once on live (Evetech, 12:40), so "never run" is wrong.
  - Takealot and Amazon have no page reader because Warren had the readers deleted on purpose on 19 Nov, not because of a code regression.
  - The page background gradient has never worked. The CSS is invalid, and the app shell paints a solid colour over the body anyway.
- **Git is clean on the delivery side.** The main checkout equals `origin/feat/integrate-20261103` at `ca8f5f7f`, and every branch from today is merged. There are 52 unmerged local branches, 17 unmerged remote-only branches, and 25 worktrees with uncommitted work.

---

## 1. How today's failures happened

### What they all had in common

- **Briefs replaced Warren's words.** Each brief paraphrases Warren and adds "Decision:" or "Those ARE…" lines that the coordinator wrote. `RULES.md` (`terminals\cursor-wave-20261124\RULES.md`) is missing most of Warren's standing rules:
  - products always show `sales_model_name`
  - promotions are sell-through, and sell-out (distributor to customer) must not be mixed in
  - the planner never shows closed, settled or ended cases or old years by default
  - which shared components to reuse (EnterpriseDataGrid and the others)
  - DONE means proven on live
- **Every job ran on one model.** `launch.ps1` has `param([string]$Job,[string]$Model='composer-2.5')`, and no job overrode it.
- **Checks tested the brief, not Warren's intent.** Proofs were API JSON, DOM element counts and computed-style dumps. None compared against the reference images in `docs/handoffs/2026-11-23/assets/*.png` or the mockup HTML. The planner mockup Warren attached is not on disk.
- **Docs were not kept up to date.** Theme2 (`edbdfc00`/`b79b1d33`), the matrix (`f1a561cb`), its test fix (`0bd7ed1b`), its crash fix (`5ef007ae`) and the pickers (`ca8f5f7f`) got no BACKLOG or CURRENT update. BACKLOG-272 still describes the earlier `676fe8c3` work ("mockup-sized h5").

### Theme

**What Warren asked for**
- Match the dashboard and targets mockups (reference images are untracked in `docs/handoffs/2026-11-23/assets/`).
- Later (t433u): theme files only, no page rebuild.
- Later still (t445u): titles too small, and he wants the theme to control fonts, colours, cards and icons everywhere.

**What the briefs said**
- `gamc4-scroll-theme.md` asked to align tokens with the mockups. Its output, `676fe8c3`, set `h5` to 1.6875rem (27px), the size page titles use.
- `gamc11-theme-rebuild.md` (the wide version) spelled out "h1 27px weight 650", 33px KPI numbers and a dashboard rebuild. It was stopped at 13:52 after t433u.
- `gamc11b-theme-tokens.md` item 5 asks for "Smaller, tighter typography and spacing (13px body, tighter headings…)". It also says "Do NOT hardcode or specially restyle any individual page… If a look change needs a one-off page edit, skip it".

**What Cursor did (`edbdfc00`, `cipTheme.ts`)**
- Moved the 27px style from `h5` to `h1`, and set `h5` to `0.9375rem` (15px).
- No page uses the `h1` style (zero matches for `variant="h1"`). Page titles render through `PageHeader.tsx:29` (`variant="h5"`, used in 11 files) and `DomainHeader.tsx:43` (`variant="h5" component="h1"`, used in 19 files). Every page title therefore dropped to 15px.
- Also added `position:'relative', overflow:'hidden'` to every `Paper` and set Chip text to 11px.
- Its own output flagged that the KPI tiles still use the old left stripe and that nothing sets `data-cip-tone`.

**How it was checked, and why the problem got through**
- `proof_theme2_20261124.py` dumps computed CSS on /dashboard, /promotions and /stock. `proof\20261124-theme2\proof.txt` records `titleSize: '15px'` and `bodyImage: 'none'`.
- `progress-20261124-theme-rebuild.md` (14:53) says "Page titles computed 15px, not the mockup 27px h1", then marks the job live and moves on.
- The gate file (`gates-theme2-20261124.txt`) only covers tsc, eslint and vitest.

**Background gradient: a newly found defect, present since before today**
- `cipTheme.ts:65` sets `backgroundImage: radial-gradient(...), ${t.bg.default}`. A plain colour is not allowed in `background-image`, so browsers drop the whole rule, which is why the proof shows `none`.
- `AppShell.tsx:129` also paints a solid `bgcolor: 'background.default'` over the whole screen, so the gradient would be hidden even if the rule were valid.
- BACKLOG-272 (`4475657d`, 03:29), commit `91bdbb00` and `progress-20261124-dashboard.md` 03:49 all claimed "everything else already matched the mockups". That claim was false and made the later work look smaller than it was.

**Decisions that went against Warren**
- The brief's "tighter headings" plus "theme files only" framing came from the coordinator. It pulled against "match the mockups", because the mockup look needs changes in shared components (KPI tiles, panel heads), which the brief ruled out.
- Mapping the mockup's h1 onto MUI's `h1` style without checking what page titles use was the agent's mistake.
- Deploying after a recorded 15px-vs-27px mismatch was the coordinator's decision.
- Warren's wish for one theme driving everything (t445u) was never written into any brief or backlog item.

**composer-2.5's part:** the literal h1 mapping and not checking how the styles are used are model-quality errors. The scope conflict and the decision to ship are not.

### Listings (Monitored listings becoming a price matrix)

**What Warren asked for (t423u/t424u)**
- His exact words are not on disk; only the coordinator's paraphrase in the GAMC-9 brief exists.
- That paraphrase covers: a price-comparison matrix, reporting customers by default with a picker, and the worker-health panel moved to a Sources tab.
- At t445u Warren said he never asked for the page to be swapped: "revert to then just add the matrix".

**What the brief said (coordinator)**
- `gamc9-matrix-discovery.md` §3 is titled "Monitored listings becomes a price-comparison matrix". That is a replacement decision.
- It specified a "Summary strip … count of 'cheapest at' per visible customer, count of prices below SRP".
- It specified highlights in "subtle green / subtle red / soft amber glow + Promo tag".
- It said to reuse "MUI / workbench-ui". It never named EnterpriseDataGrid and never mentioned `sales_model_name`.

**What Cursor did (`f1a561cb`: 23 files, +1016/−67)**
- **Page swap, `MarketSurface.tsx`:**
  - L918 changed from `{lens === 'listings' || lens === 'history' ? (` to `{lens === 'listings' ? <PriceMatrixLens /> : null}{lens === 'history' ? (`.
  - L917 `<ListingCaptureHealth />` removed.
  - The import changed, and the customers query at L356 changed to `customersListUrl(true)`.
- **`PriceMatrixLens.tsx`:**
  - "Cheapest at · X" tiles at L99–114.
  - Raw MUI `<Table>` at L132 instead of EnterpriseDataGrid.
  - `bgcolor: isLow ? 'success.light'` at L165.
  - Hard-coded `rgba(255, 193, 7, 0.55)` at L167.
- **`price_matrix.py`:**
  - SRP is `func.max(CommercialLineupLine.msrp_local)` over every lineup line ever (L54–63). That is a pricing rule nobody asked for, and the data-mapping gate was skipped.
  - Product labels are sku and name only (L237–249), not `sales_model_name`.
  - No observation date is returned, so price age can't be shown.
  - `below_srp` counts out-of-stock listings too (L202).
  - Its own output admits vitest, tsc and eslint were not run (no node_modules in the worktree) and item 4 was only partly done.

**How it was checked, and why the problem got through**
- The coordinator's gates (16:02) caught 6 failing `MarketSurface.test.tsx` tests. Those tests were the regression alarm for the old page.
- The coordinator's GAMC-9c brief (`gamc9c-marketsurface-tests.md` L28–30) told Cursor to update them to the new layout: "Do not revert the matrix or put ListingCaptureHealth back".
- The pytest added with the matrix used mocks and never reached line 150. The live endpoint then crashed with `UnboundLocalError`, fixed in `5ef007ae`.
- The 17:20 live check was API counts (93 products, 744 cells) plus a DOM table count (`table_or_matrix_count=110`). Nobody looked at the page against the old screen. A baseline screenshot exists: `terminals\screens-20261119\listing-capture_tab_registry__1280.png`.

**Who decided what**
- The page replacement and the KPI choices: the brief (coordinator).
- Rewriting the tests instead of treating them as a warning: the coordinator.
- The table type, colours, labels and SRP rule: the agent.

### Planner (customer promotions vs distributor sell-out; open cases only)

**What Warren asked for**
- t426u–t430u: the timeline by customer shows non-reporting customers, "still shows Sell out cases", and he wanted the type label removed. t435u: full width.
- His standing rules: promotions are sell-throughs; sell-out (distributor to customer) is never mixed in; no closed, settled, ended or old-year cases by default; follow the promotion-plan mockup.
- The repo already records the sell-out rule in four places:
  - `docs/BACKLOG.md:292`: "Sell out PP is Disti sell-in"
  - L935: sell-out is not sell-through
  - BACKLOG-265 (L4028–4032, Warren, 19 Nov): "the planner uses customer sell-through only"
  - `cpor_activation.py` L15–16 and L46–52, `_band_kind`

**What the brief said (`gamc8-calendar-ui.md`, coordinator)**
- "Official cpor promotion types … ARE promotion cases. Do not filter them out." It read Warren's "Sell out cases" complaint as being about labels, not data.
- "~6-month scrollable window … do not crop data away". That keeps 2024 data in the timeline.
- `gamc8b-timeline-fullwidth.md` labels the drawer layout "Decision:".

**What Cursor did (`c4f85535`, then `19c7fd46`)**
- `plannerCalendarScope.ts` sends `reporting_only=true` and `official_promotion_types=true`, which keeps Sell out PP in.
- `PromotionPlannerSurface.tsx` L170–179 only adds a status filter when the user picks one. L270–271 is `const rows = rowsAll`.
- `timelineModel.ts` `buildTimeline` (L126–154) stretches the axis from the earliest start to the latest end.
- The create dialog defaults to `'Sell out PP'` (L991, L1053). So do `promo_plan_builder.py:62` and `profile_defaults.py:57–62`.
- "Headline counts stay on the full book."

**How it was checked, and why the problem got through**
- `proof\20261124-calendar\proof.txt` asserts "NOTE Sell out PP is an official CPOR promotion type and is expected to remain". The check had the wrong rule built in.
- The full-width proof opened a case drawer showing "Amazon April Sell Through Support … 2024-04-22 → 2024-05-13 Ended" and still passed.
- `reporting-scope-audit-20261124.md` (14:35) repeats "Those are promotions, not a scope gap".

**Who decided what:** keeping sell-out cases and old ended cases was decided in the brief, by the coordinator. The agent implemented it faithfully. The "you decided????" at t445u matches the "Decision:" lines the coordinator wrote.

**Data fact that changes the fix:** of 310 live cases, every one is ended, settled, cancelled or draft. The three drafts are all Sell out PP. A planner showing open customer promotions only will be empty today.

### Discovery (customers not pulling)

**What Warren asked for**
- 19 Nov: in `docs/audits/LIVE_SCREEN_AUDIT_20261119.md` §7 (unmerged branch `docs/live-screen-audit-20261119`), "the readers were deleted on purpose; the discovery tool is meant to find each customer's website and listings". §8.4 records that he chose "watch all five sites".
- 24 Nov (t417u/t424u): live fetch allowed, Discover usable from the screen, scheduled discovery for reporting customers, no auto-link, and a confirm-site step.

**What the briefs said**
- GAMC-3: "If the schedule setting is off, nothing runs." That is correct.
- GAMC-9: "Scheduled discovery already runs for reporting customers". That is false; the setting key was never set.

**What Cursor did:** built the code paths in `0c5710ba` and `f1a561cb`. Turning a schedule on is a live-database write that needs Warren's approval; no brief asked for it and nobody asked him.

**How it was checked, and why the problem got through**
- One live Discover preview was run, for Evetech, the only customer already working. Details:
  - Time 12:40, `progress-20261124-wave-t417u.md` 12:47.
  - `preview_id d5e30111…`, with 5 sites needing review.
  - Apply was never called.
- The 17:20 check read "0 proposed sites waiting. Nothing for Warren to approve yet". An empty queue was treated as success rather than as the symptom.
- The 14:35 scope audit marked discovery "Already fixed (OK)".

**Who decided what:** the false premise came from the coordinator's brief. Not asking Warren to switch the schedule on was a coordinator omission.

### composer-2.5's role overall

Errors attributable to the model:

- the h1/h5 mix-up
- the `UnboundLocalError` crash
- a raw Table and a hard-coded colour despite the "reuse, no hardcoding" rule
- an invented SRP rule
- not challenging a brief that contradicted `cpor_activation.py`, which it could have read
- reporting a missing environment instead of fixing it so it could test its own work

This is my assessment, not a measured comparison: a stronger model would probably have avoided most of those. It would still have carried out the brief's explicit replacement and Sell-out-PP instructions, because those were stated as decisions. The model made things worse but is not the root cause.

---

## 2. Current situation: the earlier findings checked

| Earlier finding | Verdict | Evidence |
|---|---|---|
| Theme: tokens equal the mockup | Partly confirmed. I did not re-diff the mockup HTML. | `cipTheme.test.ts` asserts the mockup values. BACKLOG-272. |
| Theme: only a few component overrides exist | Confirmed, but the count is **13**, not 12. | `cipTheme.ts`: CssBaseline, Paper, Drawer, AppBar, Button, OutlinedInput, Chip, Alert, TableContainer, Table, TableHead, TableRow, TableCell. Nothing for icons, tabs, dialogs, menus, nav items, tooltips or cards. |
| Theme2 shrank titles to 15px | Confirmed. **The coordinator knew at 14:53 and shipped it.** | `edbdfc00` diff; `proof\20261124-theme2\proof.txt`; progress note 14:53. |
| Page background is flat | Confirmed, with a **new cause**. | Invalid `background-image` (`cipTheme.ts:65`) plus the solid `AppShell.tsx:129` background. Broken in both modes. |
| Listings: the old page can be restored from `9abc4716` | Confirmed. There are **4 change sites**, not 3. | Import lines, the L356 customers query, the L917–918 lens block, and the L1196 search box. Only the lens block and the health panel are the regression. |
| Matrix: raw Table, hard-coded colours, sku and name labels, SRP is the highest price ever | Confirmed. | `PriceMatrixLens.tsx` L132, 165, 167; `price_matrix.py` L54–63, L237–249. |
| (new) Matrix price counts | Two more gaps. | `below_srp` counts out-of-stock listings (L202); no observation date, so no price age. |
| (new) The matrix gets the sell-out rule right | The matrix leaves Sell out PP out of its promo tags; the planner shows it. | `price_matrix.py` `_active_promos` L66–103 uses `_band_kind`. |
| Takealot and Amazon have had no prices since 4 Nov | Confirmed (from the earlier SQL). | Last observation 2026-11-04 00:33; Evetech is current. |
| Their missing reader is a code regression from `3ea6cce4` | **Corrected.** Warren had the readers deleted on purpose (19 Nov 16:40) and wants discovery to find the sites. | `LIVE_SCREEN_AUDIT_20261119.md` §7 and §8.4. A restore script and snapshot exist on integrate (`restore_listing_site_readers.py`, `docs/ops/listing_site_readers_20261113.json`); Warren stopped it. |
| 5 reporting customers have no website recorded | Confirmed. | `web_sites` is 0. |
| The discovery schedule key is unset, so nothing runs | Confirmed. | `tasks.py:884–895` returns `discovery_schedule_off`; the setting key is defined at `tenant_settings.py:26`. |
| On-demand Discover has never been run | **Corrected.** It ran once, for Evetech only, and was never applied. | Progress note 12:47; `proof_discover_preview_20261124.py`. Possible reason it was missed (unchecked): it calls `/discovery/previews`, a different endpoint from the one the earlier audit searched for. |
| Planner: no status or date filter, axis covers every case, Sell out PP defaults | Confirmed. | Citations in §1 Planner. |
| Live cases are all ended, settled, cancelled or draft | Confirmed (from the earlier SQL). | The three drafts are all Sell out PP (2024 ×2, 2025 ×1). |
| All jobs ran on composer-2.5 | Confirmed. | `launch.ps1` default; no override in any job. |

**Things the earlier audit missed**

- **The test alarm was silenced.** The 6 failing listings tests were rewritten on the coordinator's instruction (GAMC-9c). They need restoring from `9abc4716`.
- **Docs are out of date.**
  - `docs/memory/CURRENT.md` still says the Discover button is disabled and there is no schedule activation (lines 26 and 48). It has nothing on theme2, the matrix or the pickers.
  - BACKLOG-274 says the scheduled run "applies only exact-evidence outcomes". After `f1a561cb` it only proposes.
- **Takealot needs a different kind of reader.** Its pages are built in the browser, so the plain HTML reader can never match them (19 Nov audit §8.4b). Amazon's 51 listings have no product links (§8.4c). Turning discovery on will not fix either.
- **Sensitive and stray untracked files in the main checkout.**
  - `apps/api/.env.bak-20261117` probably holds secrets and must never be committed. I did not open it.
  - `apps/api/20` is a stray file, probably left by a broken shell redirect. I did not open it.
- **The planner mockup is not on disk.** Only tests that mention it exist (`PlannerLayout.test.tsx:106–115`, `timelineModel.test.ts:101`), so no job could have checked against it.
- **No reviewed PRs.** Merges were made on a detached checkout (`cip-dashboard-20261124`) as "Merge commit … into HEAD", so no change was reviewed as a PR.
- **Global `Paper` change.** `overflow:hidden` on every `Paper` can clip menus, sticky headers and focus rings inside cards. Not yet observed.

---

## 3. Branches and worktrees

**How fresh the remote branch data is:** remote branch refs were last updated today at 17:31–17:38 SAST (`.git/FETCH_HEAD` at 17:38:29; integrate at 17:31:44). `packed-refs` dates from 20 Nov 01:15. I did no fetch, so anything pushed after 17:38 is not shown. PRs are unavailable because `gh` is not installed.

**Main checkout:** `feat/integrate-20261103` at `ca8f5f7f`, the same as `origin` (0 ahead, 0 behind). It has 9 untracked items: `.agents/`, two EIF upgrade folders, `.env.bak-20261117`, `apps/api/20`, and the four reference images. `origin/main` was last updated 2026-08-31 and is 1285 commits behind integrate.

**Counts:** "patch-equivalent" means the same change is already on integrate under a different commit.

| | Total | Merged | Unmerged but patch-equivalent | Unmerged with real work |
|---|---|---|---|---|
| Local branches | 271 | 219 | 14 | 38 |
| Remote branches | 264 | 198 | 15 | 51 (most are copies of the local unmerged ones) |
| Worktrees | 131 | — | — | 25 have uncommitted work |

### A. Today's branches (all merged, all clean)

| Branch | Result on integrate | Status |
|---|---|---|
| feat/theme-rebuild-20261124 | `edbdfc00` via `b79b1d33` (local only) | Merged, 0 ahead |
| feat/scroll-theme-20261124 | `676fe8c3` (local only) | Merged |
| feat/matrix-discovery-20261124 | `f1a561cb`, `0bd7ed1b`, `5ef007ae`, `ca8f5f7f` | Merged, also on origin |
| feat/timeline-fullwidth-20261124 | `43e8aab4` area (local only) | Merged |
| feat/calendar-ui-scope-20261124 | `c4f85535` (local only) | Merged |
| feat/reporting-defaults-20261124 | `19c7fd46` (local only) | Merged |
| feat/store-map-like-shipments-20261124 | (local only) | Merged |
| discovery-live, calendar-reporting-only, background-prefetch, theme-align-mockups and the other 24 Nov jobs | — | All merged, 0 ahead |

### B. Every unmerged local branch

In the Ahead and Unique columns, "+N" is how many of the branch's commits have no equivalent change on integrate. "+0" means everything is already there.

| Branch | Ahead | Unique | Date | What it is / verdict |
|---|---|---|---|---|
| chore/eif-v0.7.0-host-upgrade | 5 | +5 | 2026-08-29 | EIF v0.7.0 upgrade. Same commits as docs/design-language-v1. Stale. |
| docs/design-language-v1 | 5 | +5 | 08-29 | As above. |
| cursor/backlog-210-215-216-done-30b6 | 1 | +0 | — | Already on integrate. |
| cursor/cloud-agent-1779897120532-z2oy3 | 1 | +1 | 05-27 | Old cloud agent. Stale. |
| cursor/cloud-agent-1779984010444-wxmy7 | 1 | +1 | 05-28 | Old cloud agent. Stale. |
| cursor/customer-sales-pipeline-2787 | 7 | +7 | 05-17 | Early customer-sales pipeline. Superseded. |
| cursor/fix-shipment-sheet-memory-tenant-2f77 | 1 | +0 | — | Already on integrate. |
| cursor/pricing-page-padding-e640 | 1 | +0 | — | Already on integrate. |
| docs/ai-import-spec-20261120 | 1 | +1 | 11-20 | Content already on integrate via `35118f46`. |
| **docs/live-screen-audit-20261119** | 3 | +3 | 11-19 | **Relevant.** Warren's 19 Nov discovery decisions and the 56-route screen audit. |
| feat/channel-ops-ag-grid-chrome | 27 | +27 | 07-12 | AG Grid + ModuleDataSection layout. Old base; reference only. |
| feat/channel-ops-kpi-and-gap-scan-perf | 24 | +24 | 07 | Reference only. |
| feat/channel-ops-kpi-first-layout | 25 | +25 | 07 | Earlier KPI cards. Reference only. |
| feat/ci-live-e2e | 1 | +1 | — | CI end-to-end idea. Stale. |
| feat/cst-alias-bulk-actions | 28 | +28 | — | Old base. Review before reuse. |
| feat/listing-site-autoconfigure | 3 | +3 | 11-06 | `autoconfig.py` is on integrate in later form. Likely superseded. |
| feat/n0100-part-a | 1 | +0 | — | Already on integrate. |
| feat/n0118-cst-apply-c57a | 2 | +0 | — | Already on integrate. |
| feat/promote-provisionals-run | 4 | +4 | 08-21 | Unmerged feature. Needs Warren's call. |
| feat/pve-exception-list-parity | 26 | +26 | — | Old base. |
| feat/report-schedules-beat | 5 | +5 | — | Unmerged feature. |
| feat/shipping-layout-rhythm | 29 | +29 | — | Old base layout work. |
| feat/steward-queue-depth | 2 | +2 | — | Small. Review. |
| feature/background-tasks-shipment-evidence-pm | 2 | +2 | 05 | Stale. |
| fix/b215-test-isolation | 1 | +0 | — | Already on integrate. |
| fix/b216-rls-nonsuperuser | 1 | +0 | — | Already on integrate. |
| fix/backlog-225-eif-linux-identity | 1 | +1 | — | EIF Linux identity. Worktree has 18 uncommitted files. |
| fix/customer-fk-count-savepoint-2 | 1 | +0 | — | Already on integrate. |
| fix/drop-uq-source-definition-code | 1 | +0 | — | Already on integrate. |
| fix/dsi-resolution-cache-tid | 1 | +0 | — | Already on integrate. |
| fix/grant-cip-role-four-tables-2 | 1 | +0 | — | Already on integrate. |
| fix/pm-bulk-upsert-coercion-and-sql-types | 1 | +1 | 05 | Stale. |
| fix/test-cleanup-20261105 | 1 | +0 | — | Already on integrate. |
| fix/web-grid-community-stabilization | 1 | +1 | 05 | Stale. |
| wip/backlog-214-c57a | 1 | +1 | — | Rescue snapshot. |
| wip/backlog-214-e5d4 | 1 | +1 | — | Rescue snapshot. |
| wip/folder-rescue-20261112 | 3 | +1 | 11-12 | Rescue snapshot. |
| wip/recover-dirty-tree-before-data-reload | 2 | +0 | — | Already on integrate. |
| wip/rescue-20261112-eif-v070-host-upgrade | 5 | +5 | — | Copy of the EIF upgrade. |
| wip/rescue-20261112-n0118-cst-apply-c57a | 2 | +0 | — | Already on integrate. |
| wip/rescue-20261112-promote-provisionals-run | 4 | +4 | — | Copy of promote-provisionals. |
| wip/rescue-20261112-stash0-context-current-pre-rebuild | 2 | +1 | — | Old docs state. |
| wip/rescue-20261112-stash1-ns2-sellthrough-teleport | 2 | +1 | — | SellThrough UI files. Check against the current planner. |
| wip/rescue-20261112-stash2-ns2-merged-leftover-teleport | 2 | +1 | — | Leftovers. |
| wip/rescue-20261112-stash3-ns2-eif-guard-wip | 2 | +1 | — | EIF guard WIP. Do not touch (control plane). |
| **wip/rescue-20261112-stash4-ns1a-promo-planner-doc** | 2 | +1 | — | A 17-line edit to `PROMO_PLANNER_CAPABILITY.md`. Read before the planner work. |
| wip/rescue-20261112-stash5-design-backlog | 7 | +6 | — | Design backlog notes. |
| wip/rescue-20261112-stash6-eif-v070-current-md | 7 | +6 | — | Old CURRENT.md. |
| **wip/rescue-20261112-stash7-ops-grid-workflow-bar** | 38 | +37 | 07 | MasterDataGridShell list-page consistency. Reference for the grid work. |
| wip/rescue-20261112-stash9-shipment-steward-imports-page | 2 | +1 | — | Shipment steward page. |
| wip/rescue-20261112-stash10-main-dsi-steward-workspace | 3 | +2 | — | DSI steward workspace. |
| wip/rescue-20261112-stash11-main-dsi-phase0-scripts | 3 | +2 | — | DSI scripts. |

### C. Unmerged branches that exist only on origin

| Remote branch | Ahead | Unique | Note |
|---|---|---|---|
| origin/cursor/cloud-probe-guard-20261116 | 1 | +1 | Cloud guard probe docs. |
| origin/cursor/dev-env-setup-2787 | 3 | +3 | May. Stale. |
| origin/cursor/m5c-tenant-filter-55de | 1 | +0 | Already on integrate. |
| origin/cursor/setup-dev-environment-ab45 | 2 | +2 | May. Stale. |
| origin/docs/stage1-memory-refresh | 2 | +2 | Old memory docs. |
| origin/wip/programme-runtime-20261112 | 1 | +1 | EIF programme. Control plane. |
| origin/wip/rescue-20261112-files-backlog-214-c57a / -e5d4 | 1 each | +2 / +2 | Rescue file snapshots. |
| origin/wip/rescue-20261112-files-cip-b221, -grant-migration, -lane-a, -lane-f, -lane-p1, -n0108-cover-speed, -n0118-c57a, -queue-n, -queue-n4 | 1 each | +1 each | Rescue file snapshots, one per worktree. |

Also on origin with differing commits: `origin/cursor/backlog-210-215-216-done-30b6` (2 ahead, +0) and `origin/feat/cst-hist-8x4q-game-w27` (1 ahead, +0). Both are already on integrate.

### D. Merged branches, grouped

- **Merged locally but not on origin (27):** audit/second-look-item1, cursor/backlog-214-idempotent-migrations-c57a/-e5d4, cursor/lane-p1-hosting-hardening-1376, cursor/w1b-auto-discovery-a913, docs/backlog-status-c57a, docs/dashboard-v2-design-20261120, feat/calendar-ui-scope-20261124, feat/discovery-s3-20261120, feat/discovery-s4-20261120, feat/lane-a-listings-golive, feat/lane-b-cpor-cases, feat/lane-f-small-fixes, feat/listing-link-and-buybox, feat/n0077-competitor-scorer-wire-c57a, feat/reporting-defaults-20261124, feat/scroll-theme-20261124, feat/store-map-like-shipments-20261124, feat/theme-rebuild-20261124, feat/timeline-fullwidth-20261124, feature/dsi-phase-0-foundations, fix/customer-fk-count-savepoint, fix/e-n0108-cover-latest-20261113, fix/e-n0110-stock-gap-20261113, fix/grant-cip-role-four-tables, pr60-merge-20261109, promote-product-dsi-clean.
  - All of their content is on the pushed integrate branch, so nothing is lost.
- **Merged on origin with no local branch (6):** feat/listing-link-and-prices, feat/shipment-single-write, feat/store-dc-foundation, feat/tenant-mapping-scope, feat/verify-gate, feature/shipment-ev.
- **The other 192 local and 192 remote merged branches** are matching names, all fully contained in integrate.
- **Clean worktrees (106):**
  - 105 are on merged branches or detached commits already on integrate.
  - `verify-pr60` is detached 2 commits ahead, but both are already on integrate (+0).
  - `cip-dashboard-20261124` (today's merge checkout) is detached at `ca8f5f7f` and clean.
  - All of these can be pruned once Warren approves.

### E. Worktrees with uncommitted work, one row each

| Worktree | Uncommitted items | What's in it |
|---|---|---|
| Main checkout | 9 untracked | Listed above. `.env.bak` is sensitive. |
| C:/AI/cip-b221 | 26 | `.tmp_scan*.py` scratch scripts |
| backlog-214-c57a | 1 | EIF runtime events |
| backlog-214-e5d4 | 6 | `.pg_b214`, `_prove` scripts |
| backlog-225-eif | 18 | ops scripts |
| **disc-s3-20261120** | 14 | Identity, candidate, robots and scoring changes plus tests. Some files (gtin, page_facts) are now on integrate. |
| **disc-s4-20261120** | 7 | `listing_capture.py`, links, apply and preview changes. link_apply and linking are on integrate. |
| e-n0108 | 2 | `woc_observation_read.py`; its matching test is not on integrate |
| e-n0110 | 12 | Customer stock gap; tests not on integrate |
| grant-migration | 4 | Migration grants |
| **lane-a** | 2 | `autoconfig.py` own-seller autofill; its test is not on integrate |
| lane-c-20261120 | 2 untracked | dashboard-v2 mockup and spec. The same filenames are on integrate. |
| lane-f | 3 | Small fixes |
| lane-p1 | 5 | Hosting hardening |
| n0108-cover-speed | 34 | ops scripts |
| n0118-c57a | 1 | EIF event |
| no-hardcoded-identity-7017 | 2 | Identity fix |
| queue-n | 19 | Queue work |
| queue-n4 | 2 | Queue work |
| rev-pr95 | 2 | CONTEXT and CURRENT edits |
| sched-off-20261120 | 3 | Edits to migration 0064 and tenant settings. Do not apply; 0064 is already on live. |
| store-dc-unconfirmed-pins | 7 | Store map pins |
| w1a-store-dc | 1 | Store and DC work |
| **w1b-auto-discovery** | 10 | `html_page.py` +23 lines, `autoconfig.py` +30, ListingCaptureHealth +42. An untracked `structured_page.py` (104 lines, not on integrate) reads structured data from retailer pages. |
| **w1d-listing-poll** | 5 | autoconfig, registry and site-pause changes |

### (i) Unmerged work that matters

- **docs/live-screen-audit-20261119:** Warren's discovery decisions and a 56-route audit. Should be merged as docs.
- **feat/promote-provisionals-run**, **feat/report-schedules-beat**, **feat/steward-queue-depth:** real unmerged features. Warren decides whether they're still wanted.
- **The July layout and grid branches** (channel-ops ×3, shipping-layout-rhythm, pve-exception-list-parity, stash7): built on an old base and not mergeable. Useful as design reference for the theme and grid work.
- Everything else is either already on integrate, a stale May cloud branch, or an EIF control-plane change, which needs Warren and must not be touched by agents.

### (ii) Worktrees with uncommitted work worth keeping

- **w1b-auto-discovery:** `structured_page.py` and the html_page and autoconfig changes. This is the most relevant to fixing Takealot.
- **lane-a, w1d-listing-poll, disc-s3, disc-s4:** discovery and autoconfig edits.
- **e-n0108, e-n0110:** missing tests.
- **sched-off-20261120:** migration edits. Treat as dangerous.
- The rest are scratch or ops scripts.
- None of these should be cleaned up without Warren's approval.

### (iii) Existing work to reuse

- **Old listings page:** `git show 9abc4716:apps/web/src/features/market-listings/MarketSurface.tsx`, plus its 6 tests at `9abc4716:.../MarketSurface.test.tsx`.
- **Baseline screenshots:** `terminals\screens-20261119\listing-capture_tab_registry__1280.png`, `promotions_timeline__1280.png`, and the rest.
- **Sell-out rule in code:** `cpor_activation._band_kind` and `price_matrix._active_promos`. `promotion_type_vocab.py` holds the type and status vocabulary.
- **Matrix pieces to keep:** the price-matrix API, `ListingCustomerScopePicker`, `listingCustomerScope.ts`, the Data health → Sources tab.
- **Fallback for Takealot and Amazon readers:** `restore_listing_site_readers.py` plus its snapshot, only if Warren changes his 19 Nov stance. Also `structured_page.py` from w1b.
- **Shared UI:** EnterpriseDataGrid, MasterDataGridShell, `packages/ui` `agGridMuiTheme.ts`, HeadlineFigure, Panel, ModuleDataSection, PageHeader and DomainHeader.
- **Planner mockup clues:** the tests that encode it (`PlannerLayout.test.tsx:106–115`, `timelineModel.test.ts:101`) and `docs/design/PROMO_PLANNER_CAPABILITY.md`.

---

## 4. Correction and fix plan, in order

Every code step follows Warren's rules:

- a worktree off `feat/integrate-20261103`
- explicit-path `git add`
- tests on `cip_test` only
- eslint and `next build` before restart
- pg_dump before `cip-deploy.ps1 -Execute`
- BACKLOG and CURRENT updated in the same PR
- a browser smoke test on live before calling it DONE

### Step 0. Fix the process before any code (coordinator, about an hour, no code)

- **Rules file.** Add Warren's standing rules (a) to `RULES.md` word for word, including:
  - the list of shared components to reuse
  - `sales_model_name` always shown
  - sell-out kept separate from promotions
  - planner shows open cases only by default
  - DONE means proven on live
- **Briefs.** Each brief pastes Warren's message verbatim. Any interpretation is marked ASSUMPTION and confirmed with Warren before launch. No "Decision:" line unless Warren made the decision.
- **Hard stops.** Removing an existing screen or section, or rewriting a failing regression test to fit a new layout, needs Warren's explicit yes.
- **Checks.**
  - Use a Playwright check on the owning route against a written acceptance list taken from Warren's words and the mockup or reference images.
  - Any recorded mismatch blocks the deploy.
  - API JSON is not proof.
- **Environment.** Worktrees get a node_modules junction so agents can run their own vitest and tsc.
- **Model.** Switch `launch.ps1` to a stronger model (Claude Opus 5.5 high) for design, planner and theme work. Changing that default needs Warren's OK. Keep composer only for mechanical edits, and only with a strong-model review.
- **Mockups.** Save the planner mockup into `docs/handoffs/2026-11-24/assets/` before any planner layout work.
- **Docs catch-up.** One docs-only PR: BACKLOG-272 and BACKLOG-274 corrected, CURRENT.md updated for theme2, the matrix and the pickers, and merge the 19 Nov audit doc.

### Step 1. Listings: restore the old page, then add the matrix on top

**1a. Revert (small job, strong model)**
- Files: `MarketSurface.tsx` and `MarketSurface.test.tsx`.
- Restore the L917–918 lens block from `9abc4716`, so `listings` and `history` share the old table again. Restore the 6 tests.
- Keep the reporting-customer default and the search-box change unless Warren objects.
- **Warren approves:** whether `ListingCaptureHealth` returns to the listings tab. My default is yes, per "revert to then just add the matrix", while also keeping it on Data health.
- **Live check:** at `/listing-capture?tab=registry`, the old "Active listings" tiles, table and last-check caption are back. Compare by eye against the 19 Nov registry screenshot.

**1b. Matrix as an extra tab (medium job, strong model)**
- Files: `PriceMatrixLens.tsx` rebuilt on `EnterpriseDataGrid` with colours from theme tokens and no rgba literals; the market lens or chrome config gets a new "Price comparison" tab; `price_matrix.py` updated.
- `price_matrix.py` changes:
  - labels from `sales_model_name`
  - an `observed_at` per cell and a stale flag, so price age shows
  - `below_srp` counts in-stock, fresh listings only
  - the SRP source changed to whatever Warren defines
- **Warren approves:** the SRP definition, the summary tiles (drop "cheapest at"?), and where the tab goes.
- **Live check:** a Playwright check that the old tab is unchanged, the new tab shows `sales_model_name` labels and price age, and no 500 errors.
- Prove it on a small sample in `cip_test` first.

### Step 2. Planner: customer promotions only, open cases only (medium job, strong model, no migration)

**Files**
- `promotion_type_vocab.py`: move `_band_kind` here as one shared customer-promotion vs distributor-sell-out classification; `cpor_activation.py` imports it.
- The CPOR cases list and count endpoints: add a case-family filter and an open-only filter (open statuses, `window_end >= today`).
- `plannerCalendarScope.ts`.
- `PromotionPlannerSurface.tsx`:
  - default to open, with a "History" toggle
  - the ended queue only shows in history
  - the create dialog defaults to a customer type
- `timelineModel.ts`: the axis is bounded by the filter window.
- `promo_plan_builder.py:62` and `profile_defaults.py`.
- Leave `apply_sync.py` alone; that is settlement data.

**What Warren must approve**
- Which types count as customer promotions: Sell-Through PP for certain; Stock PP (In-Direct), SPIV and Stock PP (Direct) are his call.
- A label for distributor sell-out support.
- The planner will be empty today, because live has 0 open cases.

**Live check**
- `/promotions` shows no Sell out PP bars and no ended, settled or cancelled cases.
- No pre-current-year axis by default.
- History shows them.
- An honest empty state.

Planner layout changes wait until the mockup is on disk.

### Step 3. Get customers pulling prices (coordinator first; code only if needed)

**Order of work**
1. Warren confirms his 19 Nov stance: discovery finds the sites, rather than restoring the old readers.
2. With Warren's approval, run Discover preview from the screen for the 5 customers. Warren confirms sites in Data health → Sources.
3. Run autoconfigure so `adapter_key` gets set.
4. Turn on the `discovery.schedule_enabled` setting (a live setting write). Afterwards the 07:20 scheduled run only proposes; nothing is applied automatically.

**Code follow-ups (strong model, medium job)**
- **Takealot:** a browser-based or structured-data reader. First evaluate `structured_page.py` and the html_page and autoconfig diffs in the `w1b-auto-discovery` worktree.
- **Amazon:** product links for its 51 listings, through the link queue with steward confirmation.

**Warren approves:** every live write (previews, site confirmations, the setting), plus a pg_dump first.

**Live check:** Sources shows each customer's proposals. After confirmation, the Price history last-check is fresh for Takealot and Amazon, and the worker log no longer shows `skipped_not_configured`.

### Step 4. Theme

**4a. Page titles and background (tiny job, strong model)**
- `PageHeader.tsx:29` and `DomainHeader.tsx:43` switch to `variant="h1"`, which is already 27px/650 in the theme. Two files, and it matches what the mockup means.
- Fix the `cipTheme.ts:65` gradient (drop the trailing colour from `backgroundImage`).
- Make the `AppShell.tsx:129` background transparent so the gradient shows.
- Narrow `Paper overflow:hidden` to toned cards only.
- **Live check:** title computes to 27px and the body background is not `none`, in dark and light mode, against the reference images.

**4b. Theme drives everything (large job, strong model, 4–5 PRs)**
- New tokens:
  - typography styles: KPI value, tile label, panel title, eyebrow
  - tone colours
  - a chart palette
- Overrides for icons, tabs, dialogs, menus and popovers, nav items (including the active bar), tooltips, toggle buttons, cards and progress bars.
- Grid styling comes from tokens (`agGridMuiTheme.ts`).
- Chart colours come from the theme (the `workbench-ui` charts file holds roughly 16 hex codes).
- One KPI tile: HeadlineFigure absorbs PlannerKpiCard and ChannelOpsKpiCards. One panel head.
- Clean up page-level hard-coding only where it fights the theme.
- Remove the unused `packages/ui` theme copy, with Warren's approval.
- **Live check:** a Playwright computed-style checklist plus a visual comparison of /dashboard and /targets against the reference PNGs and the rendered `docs/design/dashboard-v2` mockup, in both modes. Results are reported as text, not screenshots.

**4c. Appearance settings for Warren (medium job, after 4b)**
- Theme overrides (font, background, card colours, icon size) stored in a tenant setting and applied in `createCipTheme`.
- **Warren decides:** per user or per tenant, and which controls to expose. No migration needed; the tenant settings table exists.

### Step 5. Clean-up (needs Warren's approval; no agent does this unprompted)

- Prune the 106 clean merged worktrees and the stale May branches.
- Decide on the unmerged feature branches in 3(i).
- Rescue the useful uncommitted worktree work listed in 3(ii) into branches before any prune.
- Remove `%TEMP%\x`.

### What Warren needs to approve

- **Listings:** whether the health panel returns to the listings tab, the SRP definition, and the matrix tiles.
- **Planner:** which promotion types count as customer promotions, and that the planner will be empty today.
- **Discovery:** confirm his 19 Nov stance on readers, plus approval for the live writes to run discovery and switch the schedule on.
- **Theme:** scope of the appearance settings.
- **Process:** the model change in `launch.ps1`, and the clean-up.

---

STOP. This is the end of the report. Recommendation for the next session: **start a new chat** for implementation, beginning with Step 0 and Step 1a. This audit thread is long and covers four separate areas.