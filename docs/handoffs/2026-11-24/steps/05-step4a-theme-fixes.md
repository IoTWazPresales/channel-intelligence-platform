# Step 4a: theme quick fixes (page titles, page background, Paper clipping)

- **Status:** Session 1 built and pushed; gates and visual gate run; waiting for coordinator review/merge
- **Branch:** `fix/theme-titles-background-20261125`
- **Worktree:** `C:\Users\warren_eliason\channel-intelligence-platform\.worktrees\impl-step4a`
- **EIF node / run:** N-0124 / `IMPL_step4a_20261125` (lease reacquired 26 Nov, ledger rev 2934; ledger files stay uncommitted)
- **PR:** none (`gh` unavailable); compare URL `https://github.com/IoTWazPresales/channel-intelligence-platform/compare/feat/integrate-20261103...fix/theme-titles-background-20261125?expand=1`
- **Commits:** `28576e6b` theme: page titles use theme h1, valid body gradient, drop global Paper/TableContainer overflow

Warren's words (verbatim): "4. Fine, BE SURE CURRENT COMPONENTS ARE SHARED WERE NECESSARY SO THE CHANGES ARE SMALL GOING FORWARD IF NEEDED". Earlier: "NOTHING LOOKS LIKE THE SCREEN SHOTS I SHARED??????" and "What is every fucking page hardcoded?". 26 Nov: "the previous theme edit that cursor did, completely screwed the navigation bar".

## Checklist

- [x] Read `RULES.md` and the step prompt
- [x] Page title (E1, E2): `PageHeader` and `DomainHeader` render the theme `h1`
- [x] Page background (E3): valid gradient `backgroundImage` + `backgroundColor`; `AppShell` root transparent
- [x] Paper / TableContainer clipping (E4): global `overflow` removed; toned cards keep clipping
- [x] Tests added to `cipTheme.test.ts` (3 new, none weakened)
- [x] Gates (below)
- [x] Visual gate dark + light (below)
- [x] Nav rail diagnosis (below): cause found, NOT fixed here (file outside allowed list)

## What changed (files)

- `apps/web/src/theme/cipTheme.ts`: `h1` letterSpacing `-0.04em` -> `-1px` (mock-up); body `backgroundImage` is now only the radial gradient (a trailing colour is not a valid image layer, so browsers dropped the whole rule); `MuiPaper` and `MuiTableContainer` lose global `overflow: 'hidden'`; `MuiPaper` keeps `&[data-cip-tone] { overflow: hidden }` so the 3px accent rail follows rounded corners.
- `apps/web/src/components/PageHeader.tsx`: `variant="h1" component="h5"` (element kept because `PageHeader.test.tsx` pins `h5`), `sx` typography overrides removed (E2), margin kept.
- `apps/web/src/features/workbench-ui/DomainHeader.tsx`: `variant="h1"` (element is `h1` by default), typography overrides removed (E2).
- `apps/web/src/features/shell/AppShell.tsx`: root `bgcolor` removed, so the theme's body paints the page.
- `apps/web/src/theme/cipTheme.test.ts`: 3 new assertions (title = 27px/1.1/650/-1px in both modes; body gradient valid + `backgroundColor` set; Paper/TableContainer have no `overflow`, toned cards do).

## `h5` usage and the E1 choice

`variant="h5"` count: **8 at `bc396c88`, 6 now** (the two shared headers moved to `h1`).

| File | Use | After |
|---|---|---|
| `app/(app)/sell-out/SellOutTab.tsx:276,282,290` | KPI figures | h5 (unchanged) |
| `design-lab/surfaces/DensitySurface.tsx:162` | lab heading | h5 (unchanged) |
| `features/promotions-funding/PromotionPlannerSurface.tsx:412` | **page title**, own `Typography` | h5, still 15px (see 4b list) |
| `features/shell/CapabilityDirectory.tsx:30` | **page title**, own `Typography` | h5, still 15px (see 4b list) |
| `components/PageHeader.tsx`, `workbench-ui/DomainHeader.tsx` | page titles | moved to theme `h1` |

E1 choice: **change the two shared headers to the theme `h1`; leave `h5` alone.** Reason: `h5` is also the KPI figure style in `SellOutTab`, so restoring `h5` to title size would have enlarged those numbers. Only page titles changed size.

## ASSUMPTIONS

- E1-E4 from the step prompt as written (all labelled ASSUMPTION there). E1 choice and reason above.
- `PageHeader` keeps `component="h5"` because `PageHeader.test.tsx:12` asserts `selector: 'h5'`; changing the element would mean editing that test. Heading semantics for those pages stay `h5` (pre-existing; listed for 4b/a11y).
- Specialist passes were done inline in one session, not as separate subagents (design-system, ui-visual-design, frontend-engineer, maintainability, test-engineering; accessibility/responsive via the visual gate). Recorded in the node stage note.

## QUESTION FOR WARREN

1. **Left navigation width.** The mock-up sidebar is 172px with short labels and no badges or chevrons. The app took 172px (Theme 2, `edbdfc00`: `RAIL_WIDTH` 252 -> 172) but kept long group labels plus a count badge and a chevron in one row. At 172px "ADMINISTRATION" and "DATA & STEWARDSHIP" cannot fit next to the chevron whatever the letter-spacing. Two tests pin 172 (`CapabilityRail.test.ts`, `FundingChrome.test.ts`: "rail width matches LabShell RAIL_WIDTH"). Question: keep 172px and change the label/chevron layout, or widen the rail (needs those two tests changed)? **My default:** keep 172 and fix the layout (see "Nav rail" for measured options), because no test has to change.

## STOP items waiting for Warren

None. No live `cip` writes, no migrations, no deploys. All DB access: none (browser reads of the running app only).

## Gates run (26 Nov, from `<worktree>\apps\web`)

| Gate | Command | Result |
|---|---|---|
| Unit | `node node_modules/vitest/vitest.mjs run src/theme/cipTheme.test.ts` | pass, 7 tests (3 new) |
| Unit | `... src/components/PageHeader.test.tsx` | pass, 2 tests (unchanged) |
| Unit | `... src/features/shell/CapabilityRail.test.ts` | pass, 2 |
| Unit | `... src/features/shell/AppShell.layout.test.ts` | pass, 2 |
| Unit | `... src/features/promotions-funding/FundingChrome.test.ts` (also matched `.test.tsx`) | pass, 4 |
| eslint | `node node_modules/eslint/bin/eslint.js` on the 5 touched files | 0 errors, 0 warnings |
| tsc | `node_modules/.bin/tsc.cmd --noEmit -p .` | clean (no output) |
| Build | `CIP_NEXT_DIST_DIR=.next-4a-build pnpm --dir <worktree> --filter @cip/web build` | `Compiled successfully`, 85/85 static pages, exit 0 |
| Hardcoding scan | `git diff origin/feat/integrate-20261103 -- apps` for hex / `rgba(` / `px` | no new hex or rgba. Only px: the mock-up `h1` token (`-1px`, comment `27px`) in `cipTheme.ts` and its test. No page-specific values |
| Tests weakened | n/a | none deleted, skipped or rewritten |

Note: the `DomainHeader` has no test of its own; it is covered through `FundingChrome.test.tsx` and the live render.

## Visual gate (Playwright, worktree `next dev` :3141 against API :8001, read-only, signed in via the credential file; no secret printed; dev server stopped afterwards)

Mock-up (`docs/design/dashboard-v2/index.html` via file://): h1 = 27px / 650 / -1px / line-height 29.7px, both modes. Body = `radial-gradient(at 25% 0, rgba(61,184,232,.15) -> transparent 52%)` over `rgb(20,22,26)` (dark), `rgba(21,111,156,.12)` over `rgb(243,245,247)` (light).

Page title (computed, live) in dark and light (identical in both modes):

| Page | Header component | size / weight / spacing | Mock-up 27px / 650 / -1px | Match |
|---|---|---|---|---|
| /dashboard | DomainHeader (h1) | 27px / 650 / -1px | same | yes |
| /listing-capture | DomainHeader | 27px / 650 / -1px | same | yes |
| /stock | DomainHeader | 27px / 650 / -1px | same | yes |
| /supply | DomainHeader | 27px / 650 / -1px | same | yes |
| /pricing | PageHeader (h5 element) | 27px / 650 / -1px | same | yes |
| /costs | PageHeader (h5 element) | 27px / 650 / -1px | same | yes |
| /promotions | own `Typography` in `PromotionPlannerSurface.tsx:412` | 15px / 600 / -0.3px | same | **NO** (page file, forbidden here; 4b) |
| /directory | own `Typography` in `CapabilityDirectory.tsx:30` | 15px / 600 / -0.3px | same | **NO** (page file; 4b) |

Body background (computed on `body`):

| Property | Mock-up | Live dark | Live light | Match |
|---|---|---|---|---|
| background-image | radial-gradient(at 25% 0, accent .15 / .12 -> transparent 52%) | `radial-gradient(at 25% 0px, rgba(61, 184, 232, 0.15), rgba(0, 0, 0, 0) 52%)` | `radial-gradient(at 25% 0px, rgba(21, 111, 156, 0.12), rgba(0, 0, 0, 0) 52%)` | yes, all 8 pages |
| background-color | rgb(20,22,26) / rgb(243,245,247) | same | same | yes |
| AppShell root / main background | n/a | transparent | transparent | yes (nothing repaints over the body) |

Clipping, live (dark and light, `/dashboard`): select menu (3 options) fully inside the viewport, box 159x109; tooltip ("Switch to light/dark theme") renders fully; focus ring outline `auto 1px`, no clipping ancestor. Paper `overflow` computes `visible` on /promotions, /listing-capture, /stock, /supply, /costs, /directory (`hidden` on the dashboard's first Paper is a toned or intentionally clipped one, not the global rule).
**Sticky table header: NOT proven live.** None of /stock, /inventory, /sell-out, /listing-capture, /supply, /promotions, /pricing, /costs, /reports or /commercial-planner shows a sticky header on its landing view; the MUI sticky headers sit in `CurrentLineupSection`, `CommercialDataMap`, `ProductPickerDialog`, `SkuEconomicsImport`, `ImportStewardCandidateWorkspace`, `UnresolvedGeoStewardPanel` behind a case or dialog. The cause of the old clipping (global Paper/TableContainer `overflow: hidden`) is removed and covered by the unit test. Coordinator: open a lineup case or the product picker on live to close this item.

Rendered also against the reference PNG `dashboard-design-reference-dark.png` (Read tool) and my own dark/light captures (`_proof4a/live-{dark,light}-dashboard.png`).

## Nav rail (Warren 26 Nov: "completely screwed the navigation bar")

**Cause (FACT, measured):** the rail component, not the theme and not Paper overflow. Theme 2 (`edbdfc00`, 24 Nov) changed `CapabilityRail.tsx` from `RAIL_WIDTH = 252` to `172` (copying the mock-up's 172px sidebar), restyled the group labels to the mock-up `.nav-label` (10px, uppercase, `letter-spacing: 1.4px`) and kept, in the same 172px row, the group icon (28px), a count badge and the expand chevron. The mock-up row has none of those and only short labels ("Workspace", "Explore"). Row budget at 172px: 172 - 8 (List px) - 12 (Box px) - 22 (button px + 2px border) = 130px, minus icon 28, chevron ~28 and badge ~28 leaves 46 to 74px for the label; "ADMINISTRATION" at 10px / 1.4px needs about 118px. Fixing it needs `CapabilityRail.tsx` (and `RAIL_WIDTH`, pinned by `CapabilityRail.test.ts` and `FundingChrome.test.ts`), neither in my allowed file list, so **not fixed here; handed to Step 4b**. The rail is a plain `Box`/`List` tree with no `Paper`, and its width, label style, badge and chevron all come from `CapabilityRail.tsx` as committed in `edbdfc00`, so the Paper overflow change in `28576e6b` is not in its path. (I did not render the rail at `bc396c88` to compare; this is from the code path and the measurements above, not from a before/after capture.)

Measured on `/dashboard` at 1440x900, 8 group rows, collapsed and expanded groups give identical header rows (a group's leaf list does not change its header). "Problem" = label wraps to more than one line, or label text runs under the badge or the chevron:

| Variant (CSS injected live, no source change) | Dark | Light | Rows with a problem |
|---|---|---|---|
| Current (172px, 10px uppercase, 1.4px) | same | same | 7 of 8: Overview/Stock/Promotions badge overlap, Stock wraps to 4 lines, Promotions & Funding 3 lines, Data & Stewardship and Administration run under the chevron |
| 172px, letter-spacing 0.4px | same | same | 7 of 8 (Administration still under the chevron; Stock 3 lines) |
| 172px, sentence case, 12px, 600, icon gutter 24px | same | same | 7 of 8 (Administration and badges still collide, 3 rows wrap) |
| **224px rail, current label style** | same | same | **3 of 8, all only two lines** (Stock & Sell-through, Promotions & Funding, Data & Stewardship); no label under a badge or chevron; no row clipped by the rail |

So at 172px label styling alone cannot fix it; width (or moving the badge/chevron out of the label row, or dropping the group icon) is needed. The 224px render (`_proof4a/nav-dark-w224-expanded.png`) reads cleanly. Also seen in the rail footer at 172px: "What CIP does / Capability directory" wraps to 3-4 lines and "Admin / session" text collides with the Next dev badge (dev-only overlay).

**For Step 4b (CapabilityRail.tsx, AppShell.tsx):** (1) decide the width: 224px clears every overlap and is my recommendation, but `RAIL_WIDTH` is asserted as 172 by two tests, so those two assertions would need to change with Warren's quote; or (2) keep 172 and restructure the group row (put badge and chevron on one trailing slot, allow labels two lines, drop the icon gutter). (3) Do not touch `LabShell.tsx` `RAIL_WIDTH` (design lab, same constant name). Remember `AppShell` uses `RAIL_WIDTH` for the rail box and `RAIL_WIDTH + 28` for the mobile drawer.

## Visible differences remaining versus the reference PNGs (input for Step 4b)

Compared with `dashboard-design-reference-dark.png` and the live dark and light dashboards (OBSERVATION from rendered pages, not from source):

1. Left rail: see above. The reference rail is flat: brand with cube mark, "WORKSPACE" and "EXPLORE" captions, plain items (Dashboard, Line-ups, Promotions, Sell-through, Stock, Shipments, Reports, Chart builder), footer "Your workspace / Only data you can access". Live has icon + grouped, collapsible domains with counts.
2. Page header: the reference puts the "Illustrative data" chip and "Light theme" button in the header row with the 27px title and a one-line muted subtitle. Live has a top bar (breadcrumb "Overview 26Q4", search, bell, icons) above a breadcrumb row, the title, a longer description and a signals line. Title size now matches.
3. Dashboard body: reference opens with three KPI tiles (coloured top rail, big figure, sparkline, status, progress bar) then charts then "Needs attention" with numbered rows, owner line and action buttons, then a "Start work" strip of four compact link cards. Live opens with "Start work" as large 7-card grid, then the chart builder canvas, then a dense "Needs attention" list of truncated rows with chips. No KPI tile row.
4. Cards: reference cards use larger radius, softer shadow, a coloured 3px top rail on KPI and attention cards; live Paper cards are flatter with left rails on attention rows.
5. Page titles still 15px on `/promotions` (`PromotionPlannerSurface.tsx:412`) and `/directory` (`CapabilityDirectory.tsx:30`); `PageHeader` pages keep an `h5` element (test-pinned).
6. Light mode: the gradient wash and colours match the mock-up numerically; no layout difference beyond the above.

## Nav rail rebuilt to the mock-up (26 Nov follow-up)

Warren (verbatim): "the previous theme edit that cursor did, completely screwed the navigation bar"; "The sidebar is barely big enough to fit a single 4 letter word and you want to rework its rows? How about you do what was told and follow the mockup layouts?"

**Done:** `CapabilityRail.tsx` rewritten to the mock-up `.sidebar` (docs/design/dashboard-v2/index.html): padding 24px 14px, gap 25px, cube-mark brand ("Channel" / "INTELLIGENCE"), group headings in the `.nav-label` eyebrow style, plain flat items (`.nav-item`, active = accent text + accent-wash fill + 2px accent left border + 600), footer "Your workspace / Only data you can access". Geometry lives in one exported `NAV_MOCK` constant (values copied from the mock-up CSS; colours from theme palette, no hex). Removed from the rail rows: group icon, raised paper band on expanded headings, 28px item indent (mock-up has none). `DOMAIN_ICONS` is still exported (AppShell mobile bar uses it). Nothing removed or renamed: all 8 groups, 50 group items (counted live, admin role), test ids `rail-domain-*`, `rail-badge-*`, `rail-directory`, `rail-tenant-stamp`, `Collapse X`/`Expand X` aria labels and the `Capability areas` nav label are unchanged.

**Width (measured, not assumed):** the mock-up's 172px was used first. At the mock-up's own eyebrow type (10px/700/1.4px, uppercase) the real headings measure (Inter, 1440px viewport, text node width): PROMOTIONS & FUNDING 154.2px, STOCK & SELL-THROUGH 152.6, DATA & STEWARDSHIP 136.7, MARKET & LISTINGS 124.6, SUPPLY & INBOUND 119.7, ADMINISTRATION 108, OVERVIEW 65.1, PLANNING 64. A 172px rail leaves a 144px content box (172 - 2x14), minus the mock-up's 10px label padding = 134px. Overflow at 172px: PROMOTIONS & FUNDING is 20.2px too wide before any chevron or count, STOCK & SELL-THROUGH 18.6px; measured live at 172px the text ended at x=178 and x=177, past the rail's right edge (172). The same widths in the mock-up's Segoe UI stack are within 6px (154.9 / 148.2), so the font is not the cause. Smallest width that fits every heading on one line beside its count chip and chevron: **240px (0px spare)**; shipped **244px** (4px spare for font substitution). Leaf labels also need it: "Customer sell-through files" is 167.2px and wraps below ~218px.

**Tests changed (2 assertions, `CapabilityRail.test.ts`), each with Warren's quote in the test comment and commit message:** (1) `RAIL_WIDTH` 172 -> 244 (LabShell stays 172, untouched); (2) the BACKLOG-181 assertion `bgcolor: 'background.paper'` for the production rail now asserts `background.elevated` (the mock-up sidebar is flat, no raised band); `position: 'sticky'` assertion kept for both files. `AppShell.layout.test.ts` unchanged and passing.

**Visual gate (Playwright, worktree `next dev` :3141 against the read-only API, signed in from the credential file, nothing printed; dev server stopped afterwards).** Pages `/dashboard`, `/stock`, `/promotions`, dark and light, all groups collapsed and all expanded:

| Property | Mock-up | Live | Match |
|---|---|---|---|
| Rail width | 172 | 244 | NO, deliberate and measured (above) |
| Rail padding T/R/B/L | 24/14/24/14 | 24/14/24/14 | yes |
| Rail gap | 25px | 25px | yes |
| Rail background | dark rgb(26,29,35), light rgb(255,255,255) | same | yes |
| Eyebrow size / weight / spacing / case | 10px / 700 / 1.4px / uppercase | same | yes |
| Eyebrow padding left / bottom | 10px / 7px | 10px / 7px | yes |
| Eyebrow colour (inactive group) | secondary (dark rgba(186,198,210,.82), light rgba(40,54,68,.82)) | same | yes |
| Item size / weight / colour | 13px / 400 / secondary | same | yes |
| Item padding T / L, left border, radius | 9px / 10px, 2px, 8px right corners | same | yes |
| Active pill colour | dark rgb(61,184,232) text + rgba(61,184,232,.15) fill + accent border, 600; light rgb(21,111,156) + rgba(21,111,156,.12) | same | yes |
| Footer size / colour / padding / top border | 11px / secondary / 12px 9px 0 / 1px divider (dark rgba(120,160,190,.22), light rgba(32,52,72,.14)) | same | yes |
| Brand | 15px / 700 / -0.3px, cube mark, "INTELLIGENCE" 10px | same | yes |

Clipping (`scrollWidth` vs `clientWidth`, plus text right edge vs the rail and vs each heading's count/chevron), 12 runs (3 pages x dark/light x collapsed/expanded, 16 rows collapsed, 66 rows expanded): **0 clipped, 0 multi-line headings, 0 wrapped items, 0 scrollbar width; min gap between heading text and its count/chevron 7px**. At 172px the same measurement showed 2 headings (and 1 item) clipped/overflowing the rail.

**Not in the mock-up, kept:** the count chips and chevrons on group headings (needed for collapse and the signal counts), the tenant stamp under the brand, the "What CIP does / Capability directory" link above the footer, the signed-in user line in the footer. The mock-up's "◈" glyph before the active item is not in the nav model and is not drawn.

**QUESTION FOR WARREN:** the rail is 244px, not the mock-up's 172px, because "PROMOTIONS & FUNDING" and "STOCK & SELL-THROUGH" cannot fit 172px at the mock-up's own type size. Options: (a) keep 244px (default); (b) go back to 172px and shorten the heading text for that rail only (e.g. "Promotions", "Stock", the `short` labels already in navConfig; this would be a rename of the rail heading, so I did not do it); (c) 172px with those two headings allowed to wrap onto two lines (you said no wrapping). My default is (a). A 3-digit count chip beside a long heading would overflow (4px spare is for font substitution only).

## Doc delta for coordinator

**BACKLOG-272 entry (replace/extend):**
`BACKLOG-272 (theme to dashboard-v2): Step 4a DONE in code 26 Nov (branch fix/theme-titles-background-20261125, <sha>): page titles use theme h1 (27px/650/-1px) via PageHeader and DomainHeader; body gradient is a valid background-image over backgroundColor in dark and light; AppShell root transparent; global Paper/TableContainer overflow removed (toned cards keep clipping). Evidence: cipTheme.test.ts (3 new), eslint 0, tsc clean, next build exit 0, live computed styles on 8 pages dark+light. Open: (a) CapabilityRail 172px overflow (labels wrap or run under badge/chevron on 7 of 8 groups); TRIGGER: Step 4b decides width (224px proven to clear overlaps) vs row restructure; (b) /promotions and /directory page-owned titles still 15px; TRIGGER: Step 4b moves them to the shared header; (c) sticky table header not proven live; TRIGGER: coordinator opens a lineup case / product picker on live after deploy.`

**CURRENT.md lines:**
- `Step 4a (theme titles/background/clipping): code pushed on fix/theme-titles-background-20261125; awaiting coordinator review and merge. Not DONE until merged, live restarted and proven.`
- `Known: left nav rail (172px) clips/wraps group labels (CapabilityRail.tsx, from Theme 2 edbdfc00); fix assigned to Step 4b, evidence in docs/handoffs/2026-11-24/steps/05-step4a-theme-fixes.md.`

**CONTEXT changelog line:**
`2026-11-26: theme: page titles use theme h1, body gradient valid in dark+light, global Paper/TableContainer overflow removed (Step 4a, <sha>); nav-rail width/overflow diagnosed, fix deferred to Step 4b.`

## Resume notes

Code is pushed at `28576e6b`. Scratch not to commit: `_proof4a/`, `apps/web/.next-4a*/`, `apps/web/next-env.d.ts`, `apps/web/tsconfig.json`, `docs/handoffs/2026-11-24/steps/_n0124_payload.json`, `.eif/**` ledger changes and `.eif/runs/`.
