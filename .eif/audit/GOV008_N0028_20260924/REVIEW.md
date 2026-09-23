# GOV-008 independent review: N-0028 (R2, ui)

"Start work cards and Lineup cases on the lab composition"

- Reviewer: independent GOV-008 verifier (fresh context). Lenses: verification-controller, ui-visual-design-specialist, product-interaction-designer, ux-content-naming-specialist, accessibility-specialist. The lenses were applied from their names; the Skill tool was not used.
- Date: 2026-09-24. Branch `feat/ns-2-brief-nav-collapse`, HEAD `2fe78bd5`. Working tree for `apps/web/src` is clean except for the untracked `apps/web/.tmp_n0026_vitest.txt`.
- Forbidden folders not opened: `.eif/audit/NS16_*`, `NS18_*`, `GOV008_N0025_N0029_*`, and the `docs/design/gov-008-*handover*` files.
- **Independence limitation:** while grepping for "D-0011" I saw root `CONTEXT.md` changelog lines 29–43. Several of them mention N-0028, for example "Playwright `/brief` admin Start work → `/admin/imports?unified=1`". I did not rely on them. Every verdict below comes from code, tests and my own clicks.
- Signed-in user: "Local Admin · admin · session" (VERIFIED, rendered in the rail footer). No sign-in was performed.
- Nothing that writes data was clicked. The chips clicked were URL-state filters. No Approve, Reject, Calc, Apply or Export was clicked.

## Evidence collected

| # | Evidence | Result |
|---|---|---|
| E1 | `npx --prefix apps/web vitest run --root apps/web` on `StartWorkLaunch.test.tsx`, `startWork.test.ts`, `(app)/lineup/cases/page.test.tsx` | 3 files, 10 tests passed |
| E2 | Code: `features/overview/startWork.ts` (verbs, hrefs, roles), `StartWorkLaunch.tsx`, `workbench-ui/ActionCard.tsx`, `design-lab/primitives/ActionCard.tsx` (re-exports the production ActionCard), `design-lab/surfaces/OverviewSurface.tsx:33,231`, `features/overview/OverviewHub.tsx`, `StartWorkPanel.tsx`, `app/(app)/brief/page.tsx`, `app/(app)/lineup/cases/page.tsx`, `features/lineup/LineupContainer.tsx`, `LineupWorkspace.tsx`, `planning/PlanningChrome.tsx`, `shell/navConfig.ts:59-75,188,300-306` | see criteria |
| E3 | `git log` / `git show d25a9275` on startWork.ts | steward copy changed from "Candidates grouped by failure type. Resolve in the job steward." to "Unmatched tokens from imports, resolved in one place." |
| E4 | Claude-in-Chrome, own tab. The window reports 1707×876 CSS px at dpr 1.5, and `resize_window` had no effect. To render true 1280×800 and 390×844 I loaded a same-origin `<iframe>` at those exact sizes inside my tab (the iframe's `innerWidth` and `innerHeight` were confirmed as 390 and 844) | see criteria 5 |
| E5 | Screenshots saved by the browser tool, which blocked copying them into this folder with FOREIGN_PATH: `%TEMP%\claude-chrome-screenshots-kJIzlj\screenshot-1790203558909-0.jpg` (/brief at 1707), `...775958-1.jpg` (/lineup/cases at 1707), `...874635-2.jpg` (design-lab Overview, planner role), `...919498-3.jpg` (/brief iframe at 390×844), `...932948-4.jpg` (/lineup/cases iframe at 390 after a card click), `...987309-5.jpg` (/brief iframe at 1280×800 with the Settle card focused), `...204021587-6.jpg` (/lineup/cases iframe at 1280×800) | descriptions inline |

## Per-criterion results

### AC1: Start work uses the governed ActionCard from the lab Overview composition. **PASS**
- VERIFIED (code): `OverviewSurface.tsx:33,231` mounts `StartWorkLaunch` with `layout="strip"`. The lab's `primitives/ActionCard.tsx` is a single-line re-export of `@/features/workbench-ui/ActionCard`, so lab and production share one component. Production mounts it through `/brief` → `OverviewHub` → `StartWorkPanel` → `StartWorkLaunch` with the same strip layout.
- VERIFIED (DOM at /brief): `[data-testid=start-work-cards]` holds exactly 7 `<a>` MuiCard elements.
  - Each card has an eyebrow (PLAN/DATA/FUNDING), a title, a one-line explanation and "START ›".
  - The whole card is the link: I clicked in the description area, not on the START text, and it navigated.
  - The heading "Start work" is plain typography (`h6`). Walking up from `start-work`, no ancestor has a MuiPaper or MuiCard class; its parent is `MuiStack-root`. There is no Panel or Card wrapper around the set.
  - None of the cards is a PanelRow, a list item or a menu item.
- VERIFIED: all seven verbs are present, with current labels:
  - Import a lineup
  - Review lineup cases
  - Propose a promotion
  - Load retailer sell-through
  - Load inbound shipments
  - Resolve unmatched tokens
  - Settle a funding case
- Visual (1280 iframe): a 4 + 3 grid of 237px cards. The cards in a row share one height, and the icons are in primary blue.
- One observation against the "not Import Center type-picker tiles" wording. The ActionCard docstring says its surface "matches Import Center type-picker Cards", and commit `d25a9275` says the same. It is still a distinct component with an eyebrow and a START affordance, not the type-picker component. I record this as an observation, not a failure.

### AC2: hrefs and copy. **FAIL** (steward-queue copy)
- PASS, VERIFIED:
  - `create-lineup` has href `/admin/imports?unified=1` and label "Import a lineup" (`startWork.ts:27-33`). Clicked: the URL became `/admin/imports?unified=1`.
  - No Start verb targets `POST /lineup-cases`. A grep of `startWork.ts` finds no `lineup-cases` href.
  - `steward-queue` href is `/admin/mappings`. Clicked: the URL became `/admin/mappings` and `[data-testid=steward-failure-queue-strip]` was present, meaning the N-0027 failure-type queue rendered.
- FAIL, VERIFIED:
  - The steward-queue card copy is title "Resolve unmatched tokens" with description "Unmatched tokens from imports, resolved in one place." (`startWork.ts:62-68`).
  - That copy does not describe the N-0027 queue, whose defining features are that it is grouped by failure type (`StewardFailureQueue.tsx:81,134`, "Failure types · GROUP BY entity_type") and that it holds unknown **or conflicting** candidates.
  - "Unmatched tokens from imports" describes the legacy `entity_mapping_queue` equally well. The same page calls that queue "Unresolved entity tokens" (`admin/mappings/page.tsx` legacy Paper).
  - "Resolved in one place" contradicts the queue page's own guidance that a row opens the token in the existing job steward (`StewardFailureQueue.tsx:145-148`).
  - The earlier copy did meet the criterion: "Candidates grouped by failure type. Resolve in the job steward." Commit `d25a9275` (2026-09-18, "approved copy") replaced it. Operator approval of the new wording is ASSERTED by that commit message only and was not verified. If the operator did approve it, the acceptance criterion needs a recorded amendment. Otherwise the fix is copy only.
  - The rail entry at `navConfig.ts:305` does say "grouped by failure type", so the card and the rail disagree.

### AC3: Lineup cases chrome. **PASS**
- VERIFIED (code): `lineup/cases/page.tsx` renders `<PlanningChrome><LineupContainer/></PlanningChrome>`.
  - `LineupContainer` contains `HeadlineStrip` with 5 figures (Planned units, Net requirement, Approval, Pending approval, Plan coverage), and `ScopeBar` with the chips "All lines" and "Pending approval · N".
  - `LineupWorkspace` renders `LineupPlanGrid` and `LineupPlanActionBar`.
  - `LineupTrendInstrument`, `LineupTaskCrumb`, `LineupReadStrip` (which holds the "26Q3" string) and `LineupRegimeStrip` are not imported anywhere (a grep for import statements returned exit 1). They are dead files.
- VERIFIED (render at 1707 and in the 1280 iframe), strip values:

  | Figure | Value | Caption |
  |---|---|---|
  | Planned units | 7,309 | 1647 plan lines |
  | Net requirement | 96 | B2 apply-bias |
  | Approval | 100% | of decided lines |
  | Pending approval | 1646 | (none) |
  | Plan coverage | 20% | (none) |

  - Net requirement and Plan coverage first show "—" and fill in after the queries resolve.
  - The action bar reads "NET REQUIREMENT | 96 units (B2) | Calc | Export | Apply".
  - Crumbs are "Planning / Lineup cases" (one Lineup crumb), and the LensTabs mark "Lineup cases" as selected.
  - The DOM of `main` has no From/To pattern and no "26Q3" text. The "26Q3" chip in the top app bar comes from `briefMeta.tenant_period` via the API (`AppShell.tsx:191-195`), so it is not hardcoded.
- VERIFIED (the approval filter is wired): clicking the "Pending approval · 1646" chip changed the URL to `/lineup/cases?approval=pending`, turned the chip to filled, and dropped the "Approved" Game row from the grid.

### AC4: Create promotion plan goes to /promotions?propose=1. **PASS**
VERIFIED: I clicked the "Propose a promotion" card and the URL became `/promotions?propose=1`.

### AC5: Click the real cards; render at 1280×800 and try 390×844. **PASS**
- VERIFIED, each card clicked with a mouse click on /brief as admin, then `location` read:
  - Import a lineup → `/admin/imports?unified=1`
  - Review lineup cases → `/lineup/cases`
  - Propose a promotion → `/promotions?propose=1`
  - Load retailer sell-through → `/admin/imports?template=customer_sell_through`
  - Load inbound shipments → `/admin/imports?template=inbound_shipments`
  - Resolve unmatched tokens → `/admin/mappings`
  - Settle a funding case → `/commercial-planner/cpor-cases`
- Keyboard: I focused the Settle card, pressed Enter, and it went to `/commercial-planner/cpor-cases`. The focus ring is a 2px solid rgb(61,184,232) outline.
- Tool quirk: clicks sent right after a navigate, with no screenshot in between, did not register. After a screenshot they worked every time. I attribute this to the tool, not the product, and I did not re-test it outside the tool.
- Window resize had no effect: the window stayed at 1707×876 CSS px. I rendered 1280×800 and 390×844 in a same-origin iframe of exact size instead. The iframe is a faithful viewport for CSS breakpoints, but it is not device emulation (no touch, and dpr is inherited).
- At 390: one column of cards, each 351px wide, and no horizontal overflow (`scrollWidth` 375, which is the width minus the scrollbar). I clicked "Review lineup cases" inside the iframe and it went to `/lineup/cases`, which rendered the crumb, the strip as a 2-column grid, the ScopeBar and the grid.

### AC6: Role gating. **PASS** (verified from code; rendered for admin only)
- VERIFIED (code): `startVerbsForRole` filters `START_VERBS` through `navConfig.roleMayAccess`, where admin always passes (`navConfig.ts:70-75`).

  | Card | Roles in `startWork.ts` | Matching rail leaf in `navConfig` |
  |---|---|---|
  | Import a lineup | STEWARD_PLUS [admin, steward] | Import Center, STEWARD_PLUS (:294) |
  | Review lineup cases | PLANNER_PLUS [admin, planner] | Lineup cases, PLANNER_PLUS (:188) |
  | Propose a promotion | PLANNER_PLUS | Promotion planner, PLANNER_PLUS |
  | Load retailer sell-through | STEWARD_PLUS | (none listed) |
  | Load inbound shipments | STEWARD_PLUS | (none listed) |
  | Resolve unmatched tokens | STEWARD_PLUS | Steward queue, STEWARD_PLUS (:304) |
  | Settle a funding case | PLANNER_PLUS | Case book, PLANNER_PLUS |

- A viewer sees the empty state (unit test E1). The only way to pass a role in is `StartWorkLaunch`'s `role` prop, which `StartWorkPanel` fills from `useCurrentUser().role`.
- `startWork.ts` keeps its own copies of the STEWARD_PLUS and PLANNER_PLUS arrays rather than importing them from navConfig. The values are equal today, but the two could drift apart.
- Gating is client-side visibility only. None of the destination pages has a client role guard (a grep found `roleMayAccess` only in `AppShell`). Server-side enforcement was not examined and is ASSERTED only.
- VERIFIED (rendered): as admin, 7 cards. In the design lab with the planner role, 3 cards (Review lineup cases, Propose a promotion, Settle a funding case), which is consistent with PLANNER_PLUS. That is lab rendering, not production.
- Steward, planner and viewer were not rendered in production because I did not switch users.

## Referent comparison (design lab vs production)
- VERIFIED: `/design-lab` Overview renders the same ActionCard: 344×122 at 1707 width, background rgb(34,38,46), 12px radius, the same eyebrow/title/description/START anatomy, the same heading and subline "Begin a job from here. Needs attention stays exceptions-only.", and the same strip placed above dashboard ∥ attention.
- The lab hrefs are lab analogs via `hrefFor`, which is intended.
- Production divergences are data-driven: the tenant, the live attention list, and the live dashboard.

## Findings (not acceptance failures)
1. **Mobile order (UX).** At 390×844 the Start work block runs from y=201 to about 1100. Needs attention starts at y=1107, below the first viewport, so a phone user sees only launch cards on first paint. Attention comes first only with `?zone=attention`. Consider a compact 2-column or collapsed Start strip on xs.
2. **Grid column alignment (visual).** The Planned header is right-aligned but its cells are `text-align: start`, so the numbers sit under the filter icon with the header floating to the right. Also, at 1280 the Approval column and the Approve/Reject buttons sit off-screen to the right behind the grid's horizontal scroll.
3. **Line counts disagree (content).** The domain header meta says "29 cases · 2 703 lines" while the strip and ScopeBar say "1647 plan lines", with no explanation.
4. **Approval figure misleads (content).** "Approval 100%, of decided lines" is 1 of 1 decided line out of 1647. Consider "1 of 1 decided" or showing the count.
5. **ScopeBar summary ignores the filter.** It stays at "1647 plan lines" when the pending filter is active; "1646 of 1647" would be clearer. The chips have no `aria-pressed` (a11y).
6. **Heading levels (a11y).** "Start work" is an `h6` directly under the page `h1`, skipping levels. Card titles are divs, so screen readers read each card as one long link, which is acceptable.
7. **Dead code.** `LineupReadStrip.tsx` still hardcodes "26Q3", and it and the other three Lineup chrome files are unused. They could be deleted.

## Overall verdict: **FAILED**
AC2's steward-queue copy requirement is not met. The current card copy ("Resolve unmatched tokens / Unmatched tokens from imports, resolved in one place.") does not describe the N-0027 failure-type queue, and it reads as the legacy mapping queue. Every other criterion passed with rendered or code evidence.

Remediation, copy only:
- Restore failure-type wording, for example "Work the steward queue: open candidates grouped by failure type; resolve each in its job steward".
- Or record an operator decision that amends AC2.

Limitations:
- The iframe viewport stands in for a window resize.
- Only the admin role was rendered in production.
- Server-side role enforcement was not examined.
- I was partly exposed to implementer changelog lines in root CONTEXT.md (see above).
- The screenshots stay in the browser tool's temp folder because copying them was denied.
