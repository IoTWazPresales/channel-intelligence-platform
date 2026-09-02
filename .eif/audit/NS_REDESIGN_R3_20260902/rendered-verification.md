# Rendered verification — N-0013 r3 React design prototype

Run `NS_REDESIGN_R3_20260902` · Author of renders: **the authoring run (Fable 5.1, Cursor)** ·
Independence: **NONE for these renders** — every row below is *rendered by the author* and therefore
**UNVERIFIED** until a separate GOV-008 session re-inspects the cited screenshots. Nothing here is PASS.

Method: `capture_renders.mjs` (Playwright/Chromium from `apps/web` deps) against the live Next dev server
`http://localhost:3000`, viewports **1280×800** (desktop) and **390×844** (mobile, `isMobile`, touch).
`nextjs-portal` (dev indicator) hidden by injected CSS only. Each capture waits for every Recharts
responsive container to draw; recharts animation is disabled in the prototype so bars/lines are complete.
`manifest.json` records file · viewport · URL · fullPage · `scrollWidth` for every capture; **all 34 captures
report `scrollWidth` equal to the viewport width (no horizontal overflow).**

Screenshots: `renders/proto/*.png`. WIP frames used during iteration are prefixed `_wip-` and are not
evidence.

## Artifact class

This is class **"React prototype in the real product environment"**: real Next 15 App Router route group
`(design-lab)`, real MUI 6 theme (`@cip/ui` `AppThemeProvider`), real `EnterpriseDataGrid` (AG Grid
Enterprise) and `ModuleDataSection`, real Recharts. It is **not** standalone HTML/CSS. It proves shell,
navigation, composition, density, interaction and responsive behaviour of the actual component stack;
it does **not** prove production data wiring (fixtures only) or API latency.

## 1280×800 — every representative prototyped surface

| # | Claim (what the operator sees) | Screenshot | Status |
|---|---|---|---|
| 1 | Domain rail (Overview expanded with 3 leaves; 6 further domains; "What CIP does" footer); top bar with scope stamp `FY26 P09 · W36`, search `⌘K`, attention bell with count, role select | `d-overview.png` @1280×800 | UNVERIFIED (author-rendered) |
| 2 | Overview composes **Business dashboard** (4 legible KPI figures ≥28px, trend, distribution, paired bars, ageing, family table) beside **Needs attention** (5 urgent + 3 informational rows with counts and area) and **Pinned reports**; viewport fill > 85% | `d-overview.png` | UNVERIFIED |
| 3 | Dashboard **Edit** mode shows per-widget remove affordances, dashed outlines, `Add widget` and `Done` | `d-overview-edit.png` | UNVERIFIED |
| 4 | Stock › Cover: `DomainHeader` with description/meta/actions; `LensTabs` with count; 5 headline figures incl. severity colours; cover distribution + sell-out vs shipped charts with axis labels; `ScopeBar` (saved views, status chips with counts, family chips, "40 of 40 pairs"); AG Grid cover table with proportion bars | `d-stock-cover.png` | UNVERIFIED |
| 5 | Clicking a grid row opens the **entity context panel** (product kicker, 3 figures, cover by distributor, derivation, related workflows, `Filter grid to this product` / `Done`) over the grid, grid state preserved | `d-stock-cover-panel.png` | UNVERIFIED |
| 6 | Stock › Movement: 4 figures, SOH-vs-sell-out trend W24–W36 (complete lines), sell-out by family horizontal bars | `d-stock-movement.png` | UNVERIFIED |
| 7 | Stock › Forecasts lens renders (method-labelled / gated state) | `d-stock-forecast.png` | UNVERIFIED |
| 8 | Supply & Inbound domain overview: 5 figures, shipment lifecycle bars, PO coverage proportion bars, domain attention (1 signal), workflow links | `d-supply.png` | UNVERIFIED |
| 9 | Planning domain overview: 5 figures, shipped-vs-plan paired bars with non-colliding angled labels, readiness proportion bars, attention, workflows | `d-planning.png` | UNVERIFIED |
| 10 | Funding › Case book: 5 figures (blocked/awaiting with severity), outstanding-by-age chart with currency axis, blocked-reasons panel, status chips, case grid | `d-funding-book.png` | UNVERIFIED |
| 11 | Case panel: evidence checklist (claim / sell-through / payment), figures, related workflows, `Return with reason` / `Approve` footer | `d-funding-case-panel.png` | UNVERIFIED |
| 12 | Commercial inputs: honest headline (uplift shown as "—", not a number), **price observation trend (fitted axis)**, promotion plan lines table as imported, data-gated note; not-yet-populated leaves absent from rail | `d-commercial.png` | UNVERIFIED |
| 13 | Data › Import Center: 5 figures, start-import launcher (6 template tiles), status chips, job grid with status chips | `d-data-imports.png` | UNVERIFIED |
| 14 | Data › Steward queue: 4 figures, governance note, entity tabs with counts, selectable grid with confidence bands and corroboration | `d-data-steward.png` | UNVERIFIED |
| 15 | Steward drawer: ranked candidates (radio, tier, corroboration, band·score), master search, provisional-record action, source rows table, governance key-values, `Reject` / `Map to candidate` footer | `d-data-steward-drawer.png` | UNVERIFIED |
| 16 | Data › Master data hub: four master panels (Products / Customers / Distributors / Stores) with records · provisional · possible-duplicates figures and `Open grid`; governance sentence (no silent master creation). Master grids themselves are **not prototyped** (pattern shown on cover/case/job grids); ~20% of viewport below the hub is empty | `d-data-masters.png` | UNVERIFIED |
| 17 | **Reports** = governed builder: 4 figures; metric catalogue grouped by family with **not-runnable** (spec-only / do-not-build) metrics disabled; grain toggle; horizontal bars for distributor grain with full labels; metric/grain/scope chips; Export / Schedule / Save & pin; result table; saved reports + recent runs column; sibling-of-Dashboards note. Viewport fill > 95% | `d-reports.png` | UNVERIFIED |
| 17b | Interaction: selecting *Shipped vs plan* switches to paired bars + Plan/Shipped/Attainment table; **Save & pin** appends a new saved report (green `pinned`) and shows a toast | `d-reports-shipped-vs-plan.png` | UNVERIFIED |
| 18 | Administration domain overview (captured as **admin** role; Administration is rail-visible only for admins): 4 figures, Operations panel with running/queued/failed background tasks (activity-feed rule), attention, workflow links | `d-admin.png` | UNVERIFIED |
| 19 | **Capability directory** — 8 domains × leaves with one-line "what it computes"; role chips; not-yet-populated leaves labelled | `d-directory.png` | UNVERIFIED |
| 20 | **Command palette** (⌘K) — typing `cover` lists workflows with descriptions | `d-command-palette.png` | UNVERIFIED |
| 21 | Role = **viewer**: seven domains unchanged (Administration hidden), Data & Stewardship retained for read-only masters/job status with Import Center, Steward queue and Steward audit leaves removed; dashboard labelled `viewer default · published` | `d-overview-role-viewer.png` | UNVERIFIED |

## 390×844 — global shell + workflows that require mobile

| # | Claim | Screenshot | Status |
|---|---|---|---|
| M1 | Mobile shell: hamburger, page title, search, attention bell, avatar; single-column dashboard with 2-up KPI figures; **bottom nav** (Overview · Stock · Funding · Data · More); no horizontal scroll | `m-overview.png` @390×844 | UNVERIFIED |
| M2 | Full mobile Overview order: dashboard → attention → pinned reports | `m-overview-full.png` | UNVERIFIED |
| M3 | **Navigation drawer** shows the complete domain tree with expandable leaves and directory footer | `m-drawer.png` | UNVERIFIED |
| M4 | `?zone=attention` (bell) puts Needs attention first on mobile | `m-attention.png` | UNVERIFIED |
| M5 | Funding approvals as **record cards** (customer · case · programme · SKU · claimed/outstanding/age · status chip) | `m-funding-cards.png` | UNVERIFIED |
| M6 | Case sheet full-screen with sticky `Return with reason` / `Approve` footer; evidence checklist visible | `m-funding-case.png` | UNVERIFIED |
| M7 | After **Approve**: awaiting count decrements, approved increments, toast confirms — interaction works | `m-funding-approved.png` | UNVERIFIED |
| M8 | Stock cover on mobile: lenses scroll horizontally, figures 2-up, chart stacked; breach rows as cards | `m-stock-breaches.png`, `m-stock-breaches-full.png` | UNVERIFIED |
| M9 | Import Center on mobile: figures 2-up, lenses scroll, launcher; below it the job list as **record cards** (file · job id · source · time · status chip). In the full-page frame the fixed bottom nav is painted at its scroll position — a full-page capture artifact, not a layout defect | `m-data-imports.png`, `m-data-imports-full.png` | UNVERIFIED |
| M10 | Capability directory readable single-column | `m-directory.png` | UNVERIFIED |
| M11 | Command palette full-width on mobile | `m-command-palette.png` | UNVERIFIED |

Desktop-first workflows intentionally **not** card-transformed (documented behaviour, not a warning
screen): report builder, dashboard editor, lineup planning grid, import column mapping — they render with a
frozen first column and horizontal scroll inside the grid only (`ScopeBar` and figures remain single-column).

## Non-rendered checks run by the author (not smoke)

- `npx tsc --noEmit -p apps/web/tsconfig.json`: **0 errors under `src/design-lab/**` and `src/app/(design-lab)/**`**; 8 pre-existing errors in unrelated files (`features/settings/SemanticCatalogOverlayPanel.tsx`, `features/shipping-mailer/ShippingDigestRecipientsPanel.tsx`, `src/app/(app)/…`) — reported separately, not touched.
- `ESLINT_USE_FLAT_CONFIG=false npx eslint "src/design-lab/**/*.{ts,tsx}" "src/app/(design-lab)/**/*.tsx"`: **clean**.
- Browser console on `/design-lab` after fixes: 0 errors (an earlier `<rect height=NaN>` from an explicit `undefined` XAxis height was fixed by passing explicit heights). On `/design-lab/reports` a hydration error (`<div>` Chip inside `<p>` from `PanelRow.figure`) was found and fixed by rendering the figure slot as a `div`.
- Also updated `DIRECTION.md` §7: Reports is now its own surface (`surfaces/ReportsSurface.tsx`), not a `DomainOverviewSurface` variant.

## Known limitations of this evidence

- Author-rendered; independence pending (see header).
- Fixture data; figures illustrate metric *types* the data layer can compute, not real values.
- Not captured: Reports builder interior, Administration leaves, Master data grids (domain overviews only) — out of the representative set by design; the pattern is shown on Stock/Funding/Data.
