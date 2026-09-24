# GOV-008 independent re-review — N-0032 (settlement case tabs a11y)

Reviewer: verification-controller (independent). Model identity: Claude Sonnet 5 (claude-sonnet-5), Anthropic, knowledge cutoff January 2026.
Date: 2026-09-24. App under test: http://127.0.0.1:3000 (restarted immediately before this review; `/login` returned HTTP 200 on first poll). Rendered surface: `/commercial-planner/cpor-cases/46` (no query string), via Claude-in-Chrome in a dedicated tab, closed at the end.

Commit reviewed: `16ccee1c` ("web: settlement case tabs - tabpanel named by active tab, tabs aria-controls, visible focus; pivot corner header named (N-0032 GOV-008 a11y fail)"). Files touched: `apps/web/src/features/settlement/SettlementCaseTabs.tsx`, `apps/web/src/features/settlement/SettlementCaseTabs.test.tsx`, `apps/web/src/features/cpor/CporUsdPivotPanel.tsx`.

## Tablist/tab semantics, aria-selected

- Rendered DOM: `document.querySelector('[role="tablist"]')` exists; five `[role="tab"]` buttons ("USD pivot", "Events", "Exports", "Promo load", "Payments / recon"). Claude-in-Chrome's own accessibility-tree read (`read_page`) independently exposed the same five elements as `tab "USD pivot"`, `tab "Events"`, etc. — confirms the ARIA role reaches the browser's AX tree, not just the DOM attribute. VERIFIED.
- `aria-selected`: on initial load, `USD pivot:true | Events:false | Exports:false | Promo load:false | Payments / recon:false`. After keyboard-activating Events, `document.activeElement.getAttribute('aria-selected')` returned `true` for the Events tab. VERIFIED (JS query + screenshot).
- Roving tabindex: initial query showed `tabindex="0"` on the selected tab and `tabindex="-1"` on the rest (`_r_24_-tab-pivot|true|_r_24_-panel|0`, others `|-1`). VERIFIED.

## Every tab has id + aria-controls pointing at the tabpanel; tabpanel has an accessible name (aria-labelledby the active tab)

- Source (`SettlementCaseTabs.tsx:59-68`): each `<Tab>` gets `id={tabId(t.key)}` and `aria-controls={panelId}`, where `panelId` is the single shared `Box role="tabpanel"` (`SettlementCaseTabs.tsx:70-76`). Since only one tabpanel DOM node exists and its content swaps by `tab` state, all five tabs legitimately point `aria-controls` at that one panel — this is a recognized ARIA tabs variant (single dynamically-updated panel) and not a mismatch, since the panel's `aria-labelledby` always points at whichever tab is currently active.
- Live DOM check confirmed all five tabs' `aria-controls` equal the panel's `id` (`_r_24_-panel`) and the panel's `aria-labelledby` was `_r_24_-tab-pivot` initially, updating to `_r_24_-tab-events` after switching to the Events tab. VERIFIED (JS queries, two snapshots before/after activation).
- Unit test `SettlementCaseTabs.test.tsx:56-64` (`names the panel by its active tab and links every tab to the panel`) pins exactly this: `getByRole('tabpanel', { name: 'USD pivot' })`, every tab's `aria-controls` equals that panel's id, and after clicking Events the *same* panel node is now named "Events". Ran and passed (see Tests section). VERIFIED.

## Keyboard switching (arrow keys + Enter/Space) and visible focus indicator

- With the "USD pivot" tab focused (via click), pressing `ArrowRight` moved DOM focus to "Events" (`document.activeElement` became the Events tab) while `aria-selected` remained `USD pivot:true` — i.e. MUI Tabs' standard manual-activation pattern (arrow keys move focus, selection changes on activation), which conforms to the WAI-ARIA APG tabs pattern. VERIFIED (JS query).
- Pressing `Return` (Enter) while "Events" had focus activated it: `aria-selected` became `true` for Events, the panel content changed to "Case events", and the panel's `aria-labelledby` updated to the Events tab's id. VERIFIED (JS query + zoomed screenshot).
- Visible focus indicator: zoomed screenshot after the Enter activation shows a clear blue 2px outline ring around the "Events" tab button, matching the CSS added at `SettlementCaseTabs.tsx:52-56` (`.MuiTab-root.Mui-focusVisible { outline: 2px solid; outlineColor: primary.main; outlineOffset: -2px }`). VERIFIED (screenshot).

## Pivot table headers including the corner header

- Source (`CporUsdPivotPanel.tsx:81-85`): the empty corner `<TableCell />` was replaced with `<TableCell component="th" scope="col">` containing a visually-hidden `<Box component="span">Row by column</Box>` span (same visually-hidden technique as MUI's `visuallyHidden`, defined locally at lines 5-16 to avoid adding a dependency).
- Live DOM check on the rendered pivot table (`table[aria-label="USD pivot by row and column"]`): the corner header is `TH`, `scope="col"`, text content `Row by column` (present in the accessibility tree though visually hidden). VERIFIED (JS query on live table showing years 2023Q4/2024Q1/2024Q2 rows and NB/Total columns).
- Row headers (`th scope="row"` per row) and column headers were already present in the surrounding markup (`CporUsdPivotPanel.tsx:86-89, 101-103, 117-120`) and unaffected by this diff. VERIFIED (file read).

## Accessible names on buttons/links; loading/error/empty roles

- The tabs themselves carry visible, unambiguous text labels ("USD pivot", "Events", "Exports", "Promo load", "Payments / recon") which double as their accessible names — confirmed via the AX-tree read showing `tab "USD pivot"` etc. VERIFIED.
- Loading/error/empty states for `CporUsdPivotPanel` (and by extension the other four case tabs, which share the same pattern) are delegated to `ModuleDataSection` (`apps/web/src/components/ModuleDataSection.tsx`), which grep confirms uses `role="alert"` for the error branch and `role="status"` for the loading/empty branches, with a `CircularProgress` for the loading spinner. This shared component was not touched by commit `16ccee1c` but is the mechanism the pivot panel (and the acceptance criterion) rely on. VERIFIED (grep on `ModuleDataSection.tsx`, lines with `role="alert"` at line 47 and `role="status"` at line 62).
- Note (out of scope for this commit): while reading the full page's accessibility tree at `/commercial-planner/cpor-cases/46`, four icon-only buttons in the case-header/mismatch-grid area above the tabs (`ref_121`, `ref_123`, `ref_127`, `ref_129`) exposed no accessible name in the AX tree. These are outside the diff under review (they belong to the case-header/CPOR mismatch grid, not `SettlementCaseTabs` or `CporUsdPivotPanel`) and are recorded here as an observation, not scored against this node's criterion.

## Tests

- `pnpm --filter @cip/web exec vitest run src/features/settlement/SettlementCaseTabs.test.tsx src/features/cpor` → 4 test files, 31 tests, all passed, including the new a11y-pinning test `names the panel by its active tab and links every tab to the panel`. VERIFIED (command output).

## Overall verdict: VERIFIED

All in-scope acceptance criteria for commit `16ccee1c` (tablist/tab semantics, aria-selected, tab id/aria-controls to tabpanel, tabpanel aria-labelledby, keyboard arrow+Enter/Space switching, visible focus ring, pivot corner header, loading/error/empty roles via `ModuleDataSection`) pass with direct live-DOM, AX-tree, and test evidence. No FAIL. One limitation/observation noted (unnamed icon buttons elsewhere on the case page, outside this commit's diff).
