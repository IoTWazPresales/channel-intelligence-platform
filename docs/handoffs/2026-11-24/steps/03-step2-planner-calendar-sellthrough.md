# Step 2

- **Status:** Cloud code run 27 Nov (U2) finished the web layout the mock-up answers, then Warren's 27 Nov decisions (at-risk = open and behind plan, detail buttons). Not merged, not visually checked, cip_test not run. API-side items need U4's files (see "Warren's decisions, 27 Nov").
- **Branch:** `fix/planner-sellthrough-calendar-20261125` (cut from integrate tip `6d2adc16`)
- **Worktree:** `C:\Users\warren_eliason\channel-intelligence-platform\.worktrees\impl-step2`
- **EIF node:** N-0122, run `IMPL_step2_20261125`
- **PR:** #132 to `feat/integrate-20261103` (not merged; the coordinator merges)
- **Commits:** `c63ce68c` (API), `6bb09a95` (web scope, History, empty state, create dialog, mock-up timeline), `cba724cc` (fixed customer column, bar text, legend names), plus the tracker/polish commit that carries this file.

## Checklist

- [x] Read `docs/handoffs/2026-11-24/RULES.md`, the step prompt, 00-EIF-FLOW, the brief and resume notes
- [x] Phase A: rules quoted, path map, read-only live counts (below)
- [x] Phase B: API families, `promotion_family` + `open_only` on list and counts, `/cpor/meta/promotion-types?family=`, clash summary family, plan-builder default (`c63ce68c`)
- [x] Phase C: planner scope, Open | History toggle, cards and Planner tab badge on the same scope, create dialog family, empty state, tests
- [x] Phase D: mock-up image compared element by element; layout-only gaps fixed where they keep the locked test and every section; the rest are questions
- [x] Gates (below). Visual gate rendered in dark and light from the worktree.
- [ ] Coordinator: independent review, merge, backup, deploy, live proof (not this session)

## Warren's words (verbatim)

- t454u item 2: "2. Fine, keep original page, include promotion calendar AS PER THE FUCKING MOCKUP SPEC (Other content on the page can be worked around, or removed when we finish"
- t454u answer 3: "Correct, Sell through, sell out is disti to reseller and is still valuable but not here."
- t445u: "How many times did I share the screen shot of the promotion plan mock up for you to follow????" and "How many times did I tell you sell out is from disti to customer???? maybe we need to name them differently in the system and seperate them from a where they fit perspective"
- Rules: "Promotions are sell-throughs. Sell-out is distributor (disti) to customer. They must not be mixed. The promotion planner shows customer promotions, never sell-out." and "The planner never shows closed, settled or ended cases (or old years) by default."
- Recorded earlier: BACKLOG-265 (Warren, 19 Nov): "the planner uses customer sell-through only"; `cpor_activation.py` L15-19 (Warren, 13 Aug): "Sell out PP is Disti sell-in".
- 26 Nov (via coordinator): planner proof on live is not needed; Warren will upload the rest of the cases and check it himself. The earlier live-proof question is dropped.

## Path map (UI -> API -> filter -> query)

| Surface | Web | Request | API filter |
|---|---|---|---|
| Timeline + list | `PromotionPlannerSurface.tsx` `PlannerList` | `/cpor/cases?reporting_only=true&promotion_family=customer_sell_through&open_only=true` (History drops `open_only`) | `cpor_cases.py` `_apply_case_filters` -> `promotion_type IN family types`, `_where_open_case` |
| KPI + secondary cards | `plannerCards.ts` `BASE_COUNTS_URL`, `BOOK_COUNTS_URL`, `awaitingCountUrl`, `startingCountUrl` | `/cpor/cases/counts?...family...[&open_only=true]` | same helper (list and counts cannot drift) |
| Clash card | `calendarClashUrl` | `/customer-calendar/clashes/summary?from=&promotion_family=` | `cpor_customer_calendar.py`, `timeline.py` |
| Action queue | proposed list (open family), ended list (family history) | `/cpor/cases?status=...&promotion_family=...` | same helper |
| Create dialog | `CreateCaseDialog` | `/cpor/meta/promotion-types?family=customer_sell_through` (first type = default) | `promotion_type_vocab.promotion_family_types` |
| Planner tab badge | `FundingChrome.tsx` | `BASE_COUNTS_URL` (same query key as the planner) | same helper |
| Family vocabulary | — | — | `promotion_type_vocab.py` (one map; exact match after case/space folding, no substring) |

## Live facts (read-only, `cip`, `BEGIN READ ONLY ... ROLLBACK`, 26 Nov)

`current_database() = cip`. 310 `cpor_case` rows in total. Current (not replaced), commercial cases of reporting customers:

| promotion_type | cancelled | ended | settled | open |
|---|---|---|---|---|
| Sell-Through PP | 3 | 21 | 49 | 0 |
| Sell out PP | 3 | 9 | 19 | 0 |
| Stock PP (In-Direct) | 4 | 2 | 54 | 0 |
| SPIV (In-Direct) | 0 | 7 | 15 | 0 |

- Customer sell-through family book = 73, open = 0. So the default planner shows the honest empty state.
- B3: Stock PP (In-Direct) is in no family and hides **60** reporting-customer cases (all closed). SPIV (In-Direct) (22) and Stock PP (Direct) (3, not reporting) are also in no family and are not in `CPOR_PROMOTION_TYPE_SET`.
- The audit's "3 Sell out PP drafts" are not in this set today (no current commercial drafts exist).

## Mock-up comparison (`docs/design/planner/Promotion_Planner Mockup.png`)

What the image shows that differs from B2: a Timeline | List switch in the panel header; a period navigator `< Nov – Jan 2027 (Q4) >` over a three-month window; Week selected; ISO week headers ("W47 / Nov 16") under month headers; customer logos with "N promotions"; bars that carry the promotion name, a status chip and an icon; the current week as a highlighted column (not a red today line); a legend with counts under the rows; the detail panel docked on the right and already filled, with Plan & assumptions and Adjust promotion / Create claim / More buttons; the action queue of five cards. The image itself shows a Makro "Sell-out support · Ended" bar and a "Year-end Sell-out" bar; Warren's rules win over that part of the image (no sell-out, no ended by default).

| Element | Mock-up | Built | Status |
|---|---|---|---|
| Page order | header, KPIs, filters, timeline, queue | same (locked test) | match |
| KPI strip | 5 cards | 5 cards, same order (money cards "Not available yet", BACKLOG-254) | match (data gaps stay in BACKLOG-254) |
| Panel title | "Promotion timeline" | "Promotion timeline" | fixed |
| Customer column | fixed, name + "N promotions", logo | fixed (sticky), name + "N promotions", no logo (no data) | fixed; logo = no data model |
| Bars | name + status + icon | name, and status when the bar has room; tooltip + aria-label always | fixed (icons not added) |
| Lane colours | Live green, Approved purple, Planned blue, Ended grey | Live success, Approved secondary (teal), Planned primary (blue), Ended text.secondary | 3 of 4; purple needs a theme token |
| Week header | month row + "W47 / Nov 16" | "W45" above "2 Nov" (no month row in week view) | partial (locked test bans "Nov 2026" in week view) |
| Current week | highlighted column | highlighted column (primary tint, edge lines) | fixed |
| Legend | under rows, with counts | under rows, with counts | fixed |
| Bar radius | ~6px | 6px (0.6 × theme radius) | fixed |
| Week/Month default | Week | Month | QUESTION (locked test) |
| Period navigator | 3-month window, Q label | whole range, scroll | QUESTION |
| Timeline / List | switch | timeline and grid both shown | QUESTION |
| Detail panel | docked right, filled | drawer on selection, 7 sections | QUESTION |
| Page title | 27px / 650 | 15px / 600 | theme step (titles) |
| Panel title weight | 650 | 600 | theme step (shared Panel) |

## Visual gate (rendered from the worktree)

Method: worktree `next dev` on :3113 -> worktree API on :8013 against live `cip` with every DB session forced `READ ONLY` (proved `SHOW transaction_read_only = on` on the sync and async engines before serving; mailbox, report-schedule and FX pollers off). Sign-in only was forwarded to the running API on :8001, as the coordinator's proof block does. Playwright (Python), 1600x1000, dark and light, default and `?view=history`. Dashboard-v2 `index.html` read via file:// for the reference styles. Screenshots kept in uncommitted scratch, not shared.

| Property | Mock-up (dark / light) | Live (dark / light) | Match |
|---|---|---|---|
| Body background | rgb(20,22,26) / rgb(243,245,247) | same | yes |
| Panel bg | rgb(34,38,46) / rgb(255,255,255) | same | yes |
| Panel border | rgba(120,160,190,.22) 1px / rgba(32,52,72,.14) 1px | same | yes |
| Panel radius | 12px | 12px | yes |
| Panel title | 13px / 650 | 13px / 600 | partial (weight) |
| KPI tile bg / radius / border | surface / 12px / border | same | yes |
| Page title | 27px / 650 | 15px / 600 | no (theme step) |
| Live colour | --success #3d9b6a / #1f7a4d | rgb(61,155,106) / rgb(31,122,77) | yes |
| Planned colour | blue (--accent #3db8e8 / #156f9c) | rgb(61,184,232) / rgb(21,111,156) | yes |
| Approved colour | purple | rgb(95,212,200) / rgb(15,122,114) teal | no (no purple token) |
| Ended colour | grey (--secondary) | rgba(186,198,210,.82) / rgba(40,54,68,.82) | yes |
| Current week | blue tint column | primary 0.10 fill, 0.70 edges | yes |

Rendered behaviour (both modes):

| Check | Default (Open) | History |
|---|---|---|
| List request | `reporting_only, promotion_family=customer_sell_through, open_only=true` | `reporting_only, promotion_family=customer_sell_through` |
| Rows returned | 0 | 73 (= read-only SQL 73), all Sell-Through PP: 21 ended, 49 settled, 3 cancelled |
| Timeline | "No open customer promotions. History shows ended and settled cases." + Show history | 7 customer rows, 73 bars (70 Ended lane, 3 Cancelled) |
| KPIs | In planning 0, Live 0, reserve/support "Not available yet", At-risk 22 | same |
| Ended card | 21 (family book) | 21 |
| Planner tab badge | 0 (was the whole book with sell-out) | 0 |
| Case-list requests without the family | only the shared domain header `/cpor/cases?page=1&page_size=1` (FundingChrome, also serves the case book) | same |

Found and fixed during the gate: customer names scrolled away with the dates (column now sticky); short bars showed clipped status text (now width-aware); the legend named an empty lane "planned" (now "Planned").

## Gates run (26 Nov)

| Gate | Command (from `<worktree>\apps\web` unless noted) | Result |
|---|---|---|
| eslint, touched web files | `node node_modules\eslint\bin\eslint.js <10 files>` and the 2 timeline files | exit 0, 0 errors |
| tsc | `node_modules\.bin\tsc.cmd --noEmit -p .` | exit 0, 0 errors |
| Production build | `pnpm --dir <worktree> --filter @cip/web build` | exit 0 |
| Web tests (one file each) | `node node_modules\vitest\vitest.mjs run <file>` | plannerCalendarScope 5/5, plannerCards 16/16, PromotionPlannerSurface 36/36, **PlannerLayout 16/16 (file unchanged)**, CustomerRowsTimeline 4/4 (new), timelineModel 19/19, PlannerTimeline 9/9, customerRows 3/3 |
| API tests on cip_test (one file each; DB path printed `/cip_test`) | `python -B -m pytest <file> -q` from `<worktree>\apps\api` | test_promotion_families 14, test_clash_summary_promotion_family 5, test_cpor_planner_scope_db 6, test_cpor_case_counts_db 6, **test_cpor_activation 10, test_listing_activation_timing 31 (`_band_kind`, unchanged)**, test_promo_plan_builder_vat_guard 2, test_customer_calendar_timeline 2, test_customer_calendar_clash_summary 7, test_promo_plan_builder 8, test_customer_calendar_db 8, test_cpor_cases_api 9 — all passed |
| Hardcoding scan | `git diff origin/feat/integrate-20261103 -- apps` (1266 added lines) | no hex/rgba, no country/VAT/URL, no customer or retailer names; promotion type names only in the one vocabulary map and in tests |

## Changed existing assertions (each encoded sell-out or the planner's official-types URL)

Warren: "Correct, Sell through, sell out is disti to reseller and is still valuable but not here." and "The promotion planner shows customer promotions, never sell-out."

1. `plannerCalendarScope.test.ts`: expected `official_promotion_types=true` -> now `promotion_family=customer_sell_through`, `open_only=true`, no `official_promotion_types`.
2. `plannerCards.test.ts`: four exact count URLs (awaiting, starting, base, clash) gained the family (and `open_only` where the card counts open cases).
3. `PromotionPlannerSurface.test.tsx` L112 mock: `/promotion-types` returned `['Sell out PP']` -> family request returns `['Sell-Through PP']`.
4. `PromotionPlannerSurface.test.tsx` "loads the timeline case list..." and "scopes proposed, ended, and headline count requests...": `official_promotion_types=true` -> `promotion_family=customer_sell_through` (+ `open_only=true` on the main list); every planner case request must carry the family.

No test deleted, skipped or weakened. `PlannerLayout.test.tsx` unchanged.

## ASSUMPTIONS

- B1: "original page" = the current `/promotions` planner per BACKLOG-254; nothing removed. ASSUMPTION.
- B2: now backed by the image; differences listed above. ASSUMPTION for the parts the locked test or the no-removal rule prevents.
- B3: planner family = Sell-Through PP only; Stock PP (In-Direct) off the planner (hides 60 reporting cases, all closed). One-line change in `promotion_type_vocab.py` if Warren includes it. ASSUMPTION.
- B4: open = status in draft/proposed/approved/active, not replaced, window end today or later or none. ASSUMPTION.
- B5: axis covers the shown cases and today; in Open view no earlier than the earliest open case. ASSUMPTION.
- B6: sell-out cases unchanged in storage; case book and settlement desk untouched (no file of theirs in the diff). Proposed labels below, not applied. ASSUMPTION.
- B7: create dialog lists the family types from the API, first is default, no literal in the web. ASSUMPTION.
- B8: every planner count uses the planner scope, including the Planner tab badge. ASSUMPTION.
- ASSUMPTION: Approved uses the theme's secondary colour until the theme step adds a purple status token.
- ASSUMPTION: `profile_defaults.py` L57-59 is an import alias map (sheet label -> stored type), not a default, so B-4 does not apply to it; changing it would mislabel imported sell-out cases.
- ASSUMPTION: the domain header meta line ("N plans in planning · N live · N ended") keeps the whole book because it heads every Promotions & Funding tab; only the Planner tab badge was scoped.

## QUESTION FOR WARREN

1. **At-risk actions = 22 on the default planner.** It counts ended customer sell-through cases still missing claim evidence (Evidence outstanding queue). Your rule: no ended cases by default. Options: (a) count open cases only (0 today) and move evidence-outstanding under History; (b) keep it, since it is work still to do. Default built: (b), unchanged.
2. **Closed-stage chips on the default view** ("Ended · 21", "Settled · 49") and the "Ended 21" card are counts, not rows; clicking opens History. Options: (a) show open-stage chips only by default; (b) keep. Default built: (b).
3. **Week or Month by default?** The image shows Week; the existing layout test requires Month. Default built: Month.
4. **Period navigator** (`< Nov – Jan 2027 (Q4) >`): a three-month window with arrows. Which quarter calendar is "Q4" (fiscal, behind the 26Q4 chip, or calendar)? Default built: none (whole range, scroll).
5. **Timeline | List switch.** The image has it; today the grid always shows under the timeline and an existing test expects it visible. Make List a switchable view (grid kept, hidden by default)? Default built: both shown.
6. **Detail panel docked on the right** (image) vs the current drawer that opens on selection (existing tests). Default built: drawer.
7. **Approved colour.** Purple needs a theme status token (theme step). OK to add live/approved/planned/ended/cancelled status tokens there?
8. **Stock PP (In-Direct), Stock PP (Direct), SPIV:** customer promotions (planner), distributor side, or a third group? Default built: off the planner.
9. **Is "Sell out PP" distributor-to-reseller (24 Nov) or your sell-in to the distributor (13 Aug note in `cpor_activation.py`)?** The new family name follows 24 Nov. `_band_kind` (listing activation and price matrix) still treats every non-"Sell out" type, including Stock PP, as a customer price bar; align it?
10. **Display names** (not applied): "Customer promotion (sell-through)" for Sell-Through PP and "Distributor sell-out support" for Sell out PP?

## STOP items (live writes)

None done. No migration. Read-only SQL only. The visual gate's sign-ins (forwarded to the running API, as the coordinator's proof block does) each create a normal login session row; that is the only effect on live.

## Specialist pass (run `IMPL_step2_20261125`, separate subagents, read-only)

See "Specialist findings" below. Proposals only; this file is the single writer.

## Specialist findings

(filled at the end of the session)

## Cloud code run (27 Nov, U2)

FACT: continued on `fix/planner-sellthrough-calendar-20261125` (tip was `5444352f`). Merged `origin/feat/integrate-20261103` (`643b2892`) in. No new branch. No migration. `cpor_cases.py` not edited. Theme files not edited (U5).

The mock-up (`docs/design/planner/Promotion_Planner Mockup.png`) answered questions 3, 5 and 6, and the navigator half of question 4. Those are built. Warren: "include promotion calendar AS PER THE FUCKING MOCKUP SPEC". The image's sell-out and ended bars are not built. Warren: "The planner never shows closed, settled or ended cases (or old years) by default." and "The promotion planner shows customer promotions, never sell-out."

| Element | What the cloud run did |
|---|---|
| Week default | Week is selected. Month is still there. |
| Week header | Month row ("Nov 2026") and `W45 / 2 Nov` on the week row. |
| Period navigator | Previous / next over a three-month block starting at the month that contains today ("Nov – Jan 2027" when today is in November 2026). |
| Quarter name | Appended only when that block is one quarter of the tenant's gregorian business calendar (`/api/v1/auth/tenant-commercial-profile`). No name while the profile is missing, the calendar is not gregorian, or the block is not a quarter boundary. No implied January. |
| Timeline \| List | Timeline is the default. List shows the existing grid (or the phone cards). The grid is not removed. |
| Detail | Docked beside the timeline (`planner-detail-dock`), empty until a promotion is selected. Close, Clear and Escape clear it. No drawer. |
| Bar mark | A lane-coloured dot on a bar wide enough to hold it. There is no icon field on the case. |
| Approved colour | Unchanged (theme secondary). Purple is a theme token; U5 owns the theme. |
| Logos | Not added. The case list has no logo. |
| Page title / panel weight | Unchanged. U5 owns the theme. |

### Constants kept or added

| Constant | Reason it is not tenant config |
|---|---|
| `PLANNER_VISIBLE_MONTHS = 3` | The mock-up draws one three-month block. Layout of this screen. |
| `DETAIL_DOCK_PX = 360` | Width of that docked column in the mock-up. Layout of this screen. |
| Bar-mark minimum 28px, `BAR_NAME_MIN_PX` 44, `BAR_STATUS_MIN_PX` 120, `WEEK_PX` 56, `LABEL_W` 170 | How much text fits on a bar. Layout, not a rate or a threshold a tenant sets. |

### Tests (cloud Linux, no database)

| Gate | Result |
|---|---|
| eslint on the eight touched web files | exit 0 |
| `tsc --noEmit -p apps/web` | exit 0 |
| vitest planner + plannerLayout + PromotionPlannerSurface | 12 files, 143 passed |
| `pnpm --filter @cip/web build` | exit 0. Compiled, 85 pages. Existing hook warnings elsewhere, none in the planner files this run edited. |

Assertions changed because the mock-up is the requirement (close-off: follow the mock-up where it answers an open question):

1. `PlannerLayout.test.tsx` week header: Week is the default, "Nov 2026" stays in the week view (month row), week text is `W45 / 2 Nov`. The ended sample sits in November so it is inside the default block.
2. `PlannerLayout.test.tsx` and `PromotionPlannerSurface.test.tsx`: the detail is the docked column, empty until a selection. There is no drawer.
3. `PromotionPlannerSurface.test.tsx`: the grid is behind List. Timeline is what the page opens on. The sample case window is 9–20 Nov 2026 so it is on the default block. Date is pinned to 19 Nov 2026 in that file so the block does not drift.
4. `CustomerRowsTimeline.layout.test.tsx`: week labels, navigator, quarter name when fiscal start month is 2, List hides the bars.
5. `CustomerRowsTimeline.test.tsx`: the sample window is June 2026 because today in that test is 15 Jun 2026 (the three-month block). The theme mock gained `secondary` and `mode`, which the component already reads.

No test deleted, skipped or weakened. Sell-through and `open_only` assertions are unchanged.

### NOT RUN (cloud)

- Every `cip_test` / pytest path. No database on this machine.
- Visual gate (dark and light, Open and History) against the mock-up.
- Production `next build` is recorded below if this session ran it.
- Review, merge, deploy.

### ASSUMPTIONS

- The navigator pages three calendar months, not one fiscal quarter of a 4-4-5 calendar. A non-gregorian business calendar leaves the quarter name off.
- List shows the same cases as the timeline's request (open customer sell-through, or History). It is not cut to the three-month block.
- Detail actions stay "Open plan", "Case book" and "Clear". The image's "Adjust promotion / Create claim / More" were not an open question. (Superseded by Warren's 27 Nov decisions below.)
- At-risk still counts ended cases missing evidence (question 1, option b). Closed-stage chips stay on the default view (question 2, option b). (At-risk superseded by Warren's 27 Nov decisions below.)

## Warren's decisions, 27 Nov (U2 round 2)

Warren (via coordinator, verbatim): "1. An open promotion closes and reconciles itself from the sales pulled over that period, as already specified. Ended, settled, and cancelled cases are not "at risk". At risk means an open promotion whose sell-through is behind the plan for the time already elapsed. 2. Keep the three-calendar-month navigator. Quarter name comes from the tenant calendar. Do not lock in 4-4-5. 3. Add the detail buttons Adjust promotion, Create claim, and More. They can be checked later in the visual test. 4. Promotion type labels are a tenant list, assignable, not fixed names. [...] Do not hardcode those names into product code. If the list itself lives in U4's files, do not edit those files."

| Decision | What this run did (web only) |
|---|---|
| 1. At risk | New `plannerLayout/sellThroughPace.ts`. A case is judged only when it is open (draft, proposed, approved, active), not replaced, and its window has started. Planned units = case lines' `estimate_qty`; sold = the customer's own sell-through inside the window. Both come from the existing `GET /cpor/cases/{id}/promo-load-recon` (customer sell-through only, never sell-out). Behind = sold < planned × share of window elapsed (whole days, today included). The planner reads open cases started by today (`open_only=true&window_to=<today>`, separate from the main list so stage chips and History never change it), then one recon per case. The At-risk KPI counts behind-plan cases; each is queued as "sell-through behind plan". Ended, settled, cancelled and rejected cases are never judged and their recon is not read for the count. A case with no sell-through loaded or no planned units is not called at risk; the caption says how many started cases had nothing to judge. A failed read shows the card as failed, not zero. Evidence outstanding stays its own queue card. |
| 1. Reconcile | The docked detail has a Sell-through section: units sold in the window against planned units, for any selected case. For an open, started case it adds the pace ("Behind plan" / "On plan", expected so far, share elapsed) and the latest sales period loaded. The automatic close itself is API work (see below). |
| 2. Navigator | Unchanged: three calendar months. The quarter name comes only from the tenant's business calendar (gregorian + fiscal start month). Retail 4-4-5 / 4-5-4 / 5-4-4 / custom show no quarter name; nothing assumes 4-4-5. |
| 3. Buttons | "Adjust promotion" (opens the plan workspace, `planner-side-open`), "Create claim" (the case's settlement desk `/commercial-planner/cpor-cases/{id}`, where the claim file is imported, `planner-side-claim`), "More" (menu: "Open in case book", "Clear selection"; `planner-side-more`). |
| 4. Type labels | No promotion type name is hardcoded in planner product code. The detail subtitle now shows the case's stored `promotion_type` label. The planner asks the API for the family `customer_sell_through` only; which types belong to the family is decided in `promotion_type_vocab.py` (U4). The literals in `apps/web/src/design-lab/**` are mock fixtures, not product code, and were not touched. |

### Constants added

None. "Behind" uses no tolerance: there is no tenant setting for one, and inventing a threshold would be a hardcoded rate.

### Not done here (needs U4's files)

- The automatic close and reconcile of an open promotion from sales pulled over its period is a lifecycle transition on the API (`cpor_cases.py` transitions / settlement). Not edited. Also FACT: `docs/CPOR_SETTLEMENT_SPEC.md` L41 says "Ken still takes the settle/close action. The system records it; it does not auto-close." That contradicts decision 1 and needs Warren's ruling on which wins before U4 builds it.
- A tenant-assignable promotion-type list (with "Stock PP" = upfront funding marking the price down at the customer, "SPIV" = store incentive as tenant data, not code) lives in `promotion_type_vocab.py` and the tenant profile (`commercial_tenant_profile.py`). Not edited.
- A quarter name for a retail (4-4-5 / 4-5-4 / 5-4-4) or custom calendar needs period boundaries from the tenant profile (`commercial_tenant_profile.py`). Not edited; those calendars show no quarter name.
- One recon request per started open case. Fine at today's volumes; a batch recon endpoint (in `cpor_cases.py`) is the scale fix.

### Tests (cloud Linux, no database)

| Gate | Result |
|---|---|
| eslint on the touched planner files | exit 0, no warnings; `pnpm --filter @cip/web lint` 0 errors |
| `tsc --noEmit -p apps/web` | exit 0 |
| vitest `src/features/promotions-funding` | 33 files, 238 passed, 1 failed: `FundingChrome.test.ts` "rail width matches LabShell RAIL_WIDTH" expects 172, gets 244. Not this change: `RAIL_WIDTH` moved in trunk nav commits `f62a2aae` / `2ecec103` (26 Nov, merged in). U5 owns the nav/theme. |

Assertions changed, requirement = Warren 27 Nov decisions 1 and 3:

1. `PromotionPlannerSurface.test.tsx` "shows In planning, Live promotions and At-risk actions cards": was At-risk 1 from the overdue approval; now 0 while the case sells on plan, and the overdue approval is still in the queue.
2. Same file, "At-risk actions as failed": was a failed ended list; now a failed sell-through read. A new test checks a failed ended list does not fail the at-risk count.
3. Same file, the Clear path in "clears the docked detail": Clear is under More.
4. Same file, the family check and History's `mainListCalls` skip the per-case recon read and the at-risk read (`window_to=`), which are not the main list.
5. `actionQueue.test.ts` `queueSummary` gained `behindPlan`.

New tests: `sellThroughPace.test.ts` (elapsed share, open-only, ended never judged, no data no risk), behind-plan queue items, the at-risk KPI (behind, no data, ended not read), the three detail buttons and the Sell-through section.

### ASSUMPTIONS (round 2)

- "Time already elapsed" is measured to today, as Warren said. If customer sales arrive a week late, a case can read behind until the next file lands. The detail shows the latest sales period loaded so the lag is visible. QUESTION FOR WARREN below.
- Every open stage counts once its window has started, including a draft or proposed case whose window is already running.
- A case still `active` after its window ended is not on `open_only` (the API's definition of open excludes ended windows), so it is not judged here; the API close (above) is what moves it on.

### QUESTION FOR WARREN (round 2)

1. Should elapsed time stop at the latest sales period loaded for that customer (fewer false alarms when files arrive late), or at today as stated?
2. `CPOR_SETTLEMENT_SPEC.md` says the system "does not auto-close"; decision 1 says an open promotion closes itself. Which one is current?

## Close for review (Warren, 27 Nov) — STOPPED before code

Warren (via coordinator, verbatim): "Reconcile open promotions from sales over the period, then close them for review. Do not send to the customer yet. Notify the user in charge of that process. Automatic send to the customer comes later, and that send must also notify the person in charge."

Done: `docs/CPOR_SETTLEMENT_SPEC.md` §1 no longer says the system does not auto-close; it states the ruling and what is not built. No code written for the transition.

### Path map (FACT, read from the tree)

| Trigger | API | Writer | Commit model |
|---|---|---|---|
| Manual "end" today | `POST /cpor/cases/{id}/transition` `action=end` (`cpor_cases.py` L1786) | sets `status=ended`, `workflow_status`, event `transition_end` | one case, one commit |
| Claim file import | `POST /cpor/cases/{id}/claim-evidence/import`, `POST .../settlement/rollup` | `settlement.rollup_result_qty_from_claims` writes `cpor_case_line.result_qty` = claim units in each line's window, then `recompute_case_line` (sets `ttl_result`) | per case |
| Sell-through read (no write) | `GET .../promo-load-recon` (`promo_load_recon.py`) and `settlement._cst_and_claim_units` | none | read only |
| Scheduler | `worker/celery_app.py` `build_beat_schedule` (no CPOR entry) | none | — |
| Notification | none for CPOR. `report_delivery` inbox exists, constrained to `trigger IN (manual, schedule, import_event)`, `format IN (xlsx, pdf)`, tied to saved reports | — | — |

Lifecycle (`lifecycle.py`): `active → ended → settled`. "Closed for review" maps onto `ended` with no new status (ASSUMPTION, needs yes/no).

### Data-mapping gate (why this stopped)

Reconcile would write a computed value: `cpor_case_line.result_qty` (and so `ttl_result = support_unit × result_qty`, D-027) from `fact_customer_sellthrough.units_sold`. Today `result_qty` comes only from claim evidence. Before/after for a line with planned 100, claims 0, sell-through 60 in the window: before `result_qty` null, `ttl_result` null; after `result_qty` 60, `ttl_result` 60 × `support_unit`. The tree has two different "in the window" rules for sell-through, and neither pro-rates:

1. `promo_load_recon.py`: periods whose `period_start_date` is inside `[window_start, window_end]`.
2. `settlement._cst_and_claim_units`: periods starting from `window_start − 31 days` to `window_end` (catches a monthly period that began before the window).

Sell-through rows are weekly or monthly (`period_type` / `period_grain`), can be month-to-date estimates (`is_mtd_estimate`), and can be chain or store grain (`customer_location_id`). Picking one rule silently changes the amount owed.

### WARREN (needed before the close-for-review code)

1. Which sell-through counts for a window: rule 1, rule 2, or week-grain only with straddling weeks flagged (spec §5 "flagged, never silently pro-rated")? Are month-to-date estimates excluded?
2. Does sell-through set `result_qty` when no claim file exists, with a later claim file replacing it? Or is sell-through stored beside the claim figure (`ttl_result` stays claim-based) and the review shows both? The second needs no change to the amount owed.
3. Who is "the user in charge of that process"? Nothing in the tree stores it: no owner on `cpor_case`, no setting in the tenant profile (`commercial_tenant_profile.py`, U4), and the spec's Ken role is not in the role enum (§9 gap 2). Options: a tenant-profile setting naming a user (U4's file), a role (needs the role enum), or the case's `created_by`.
4. Where does the notice land? `report_delivery` cannot hold a case notice without a migration widening its `trigger` / `format` checks, or a new notice table (migration). Email has no adapter for CPOR (`promo_export/notify.py` is a stub).
5. When does it run: a daily beat task over cases whose window ended, or after each sell-through import?
6. Is "closed for review" the existing `ended` status?

## Resume notes

- Build and gates are done. Remaining work is the coordinator's (review, merge, deploy, live proof) and Warren's questions.
- Scratch never to commit: `_scratch_eif/`, `.eif/runs/`, `.eif/*.md` views and `.eif/program/*` (control plane; left uncommitted in the worktree).

## Doc delta for coordinator

(filled at the end of the session)
