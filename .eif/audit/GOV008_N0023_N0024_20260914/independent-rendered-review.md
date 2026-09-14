# N-0023 / N-0024 independent rendered review (GOV-008)

**Run:** `GOV008_N0023_N0024_20260914`  
**Actor:** `gov-008` (this session; not the implementer)  
**Date:** 2026-09-14  
**Implementation runs (anchored, not re-executed as implement):** N-0023 `NS11_RAIL_20260913` / `gov-001`; N-0024 `NS12_NAV_DEST_20260913` / `gov-001`  
**Reviewer HEAD:** `9cd49e1` on `feat/ns-2-brief-nav-collapse`  
**Product pins:** N-0023 `6a2e912`; N-0024 `10d2a64`  
**Programme snapshot at review start:** 554; leases reclaimed here → 555 (N-0023), 556 (N-0024)  
**Out of scope:** D-0002, N-0006, N-0013, navigation IA restructuring, Movement/Execution relocated workspaces, column-picker consolidation, grid chrome.

This is **implementation-verification + evidence-skeptic**. Implementer evidence is DATA. Figures and URLs below were **re-read on screen** and **clicked**. `current_database()=cip` printed first (read-only). NUMBER RULE does not apply to either node (no headline-value gate).

---

## 1. Verdicts

### N-0023 — **VERIFIED**

LabShell rail tokens are on production `CapabilityRail`. Independent Playwright at 1280×800 vs lab `/design-lab/stock?lens=cover`, plus 390×844 drawer. Sticky pin-during-scroll, which the implementer left UNVERIFIED, was forced here: every domain expanded, rail `scrollHeight` 1893 vs `clientHeight` 607; Data header stayed at y=72 (`offsetNav` 8) while Import Center / Customer sell-through leaves moved from y=96 → y=16 under the opaque `rgb(34, 38, 46)` header. `elementFromPoint` on the header centre remained `rail-domain-data`.

### N-0024 — **VERIFIED_WITH_LIMITATIONS**

The mismatch class was enumerated independently (navConfig rail leaves, brief `action_label`/`action_href`, hub Workflows, headline-figure `onClick`) **before** reading implementer evidence. Named destination fixes land on the jobs they name. No additional **live** mismatch of the same class was found among controls that rendered this session. Limitations below are non-blocking for `complete()`: they are coverage holes the implementer already labelled, plus one unused blotter component, not a remaining wrong href on a visible labelled control.

**Limitations (non-blocking):**

- Specialist-contract R3 also wants a second-model consult when available. This run is another session and another programme run/actor than the implementers. No CLI consult.
- Keyboard path and axe not exercised.
- `soh_recon_not_run` was **not** in the live blotter (3 urgent: failed imports, cover-breach, inbound-open). Source href is `/stock?lens=cover`. **UNVERIFIED** as a click.
- `BriefPageContent` / `BriefSignalRow` `action_label` is **not mounted** on `/brief` (that route is `OverviewHub`; rows use `title` + `action_href`). Labels vs hrefs were checked in `brief_signals.py` and on Overview attention rows.
- Market “Planning lineup” row did not render on `/listing-capture` hub landing. Source `onClick` is `/lineup/cases`. **UNVERIFIED** as a click.
- PO auto-link case chip not opened this session. Source `href="/lineup/cases"`. **UNVERIFIED** as a click.
- `/getting-started` middleware-redirects to `/brief` (`RETIRED_TO_BRIEF`). That page is not a live operator surface.
- Cover-breach blotter count **102** vs Cover chip **Under 4w · 467** (430+37). Destination and chip are the under-4w union; counts are different grains. NUMBER RULE is not a gate on this node.
- Playwright click-result URLs were often one navigation behind; final URL was taken from a later snapshot/tab list/`location.href`.

---

## 2. Independence rung used

**R2 session separation + programme R3 provenance.** Fresh GOV-008 context, run `GOV008_N0023_N0024_20260914` / actor `gov-008`, distinct from `NS11_RAIL_20260913` and `NS12_NAV_DEST_20260913` / `gov-001`. Own Playwright MCP session. Own source enumeration before implementer evidence. Not a second-LLM consult. `browser_cdp` not invoked.

---

## 3. Session start / EIF denials (verbatim)

**SESSION_CLOSURE_REQUIRED** on first mutating git/shell:

```
SESSION_CLOSURE_REQUIRED: Remote closure proof pending. Run from the project root, subject to shell policy: python -B .cursor/hooks/eif_guard.py --verify-closure 2ec4337d9aa5d23e45d41daa175a6466fbe47123b1c60ea216893f96eb5cc62d 5bb04c46575e4e57abf1e1ec362ca601. Reads and policy-permitted recovery remain available; do not claim closure yet.
```

Ran that command exactly. Result:

```
{"ok": true, "reason_code": "SESSION_CLOSURE_OK", "decision_kind": "policy", "message": "ledger_commit=9cd49e159b6529e17d89df58d0b73b136f3cc6c4; verified_remote_head=9cd49e159b6529e17d89df58d0b73b136f3cc6c4"}
```

Other denials / skips this session (not retried as workarounds):

- Read of `.eif/audit/NS12_NAV_DEST_20260913/payloads/node.add.json` — eif_guard fail-closed twice; **SKIPPED**. N-0024 AC taken from `program.py status --node N-0024`.
- Playwright `browser_take_screenshot` with a custom filename — `MCP_OUTPUT_PATH`; retried without filename; screenshot saved to Playwright default path.
- Intermittent eif_guard fail-closed on Playwright evaluate / find / shell; retried once then skipped that call.
- `print_db.py` first run: `psycopg2` missing; switched to `postgresql+psycopg`. Then `current_database()=cip`.

`browser_cdp` not invoked.

---

## 4. N-0023 — acceptance criteria

| AC | Result |
|---|---|
| Governing visual input is LabShell (`LabShell.tsx`), port into `CapabilityRail.tsx`. Do not cite a frozen design-language version. | **VERIFIED** source + lab/prod measure |
| Raised opaque expanded header; sticky group header; nested guide rail removed (indent kept); active leaf 3px rounded bar + weight, not Mui-selected fill | **VERIFIED** |
| Collapsed-active decided and recorded | **VERIFIED** (transparent after pointer left the rail; primary icon + weight 600; no bar). While the pointer stayed on the header after the chevron click, bg was `rgba(61, 184, 232, 0.24)` — hover, not selected fill |
| D-0010 chartered; this node does not collapse the rail, remove tabs, or change nav hrefs/labels/order | **VERIFIED** LensTabs still present on Cover/Supply/Planning/Funding; D-0010 Option A already accepted on the ledger (`abaf04b`) |
| Preserve RAIL_WIDTH 252, role gating, chevron aria-label, badges, directory footer, localStorage, testids, label wrap. D-0002 / N-0006 / N-0013 untouched | **VERIFIED** measured rail width 251 (same as lab; 1px chrome). `NAV_STORAGE_GROUP_EXPANDED` still written. Directory footer `/directory`. D-0002 copy still on steward queue |
| Browser-verify 1280×800 vs lab; 390×844 drawer. No browser_cdp. NUMBER RULE n/a | **VERIFIED** `innerWidth===1280` `innerHeight===800`; drawer `390×844` same 3×15 bar + raised header |
| `target_artifact_class: high_fidelity` | **VERIFIED** live production UI |
| Independent GOV-008 vs implementation_run | **VERIFIED** this run |

### Token table (this session)

| Token | Lab `/design-lab/stock?lens=cover` | Production `/stock?lens=cover` |
|---|---|---|
| Viewport | 1280×800 | 1280×800 |
| Rail width | 251 | 251 |
| Expanded header bg | `rgb(34, 38, 46)` sticky z=2 | same |
| Active leaf bg | `rgba(0,0,0,0)` | same |
| Leaf `::before` | 3×15px r=2 `rgb(61, 184, 232)` | same |
| Active leaf `<p>` weight | 600 | 600 |
| Nested list `marginLeft` | 34px | 34px (source `ml: 4.25`) |
| Collapsed-active (after blur) | (not re-measured on lab this pass) | bg transparent, icon `rgb(61, 184, 232)`, weight 600, no bar |
| Sticky pin-during-scroll | same CSS as prod | **VERIFIED** Data header pinned at y=72 while leaves scrolled under; opaque; `elementFromPoint` stayed on the header |

390 drawer: `drawerOpen=true`, `inner 390×844`, Cover leaf 3×15 bar, Stock header paper + sticky z=2.

---

## 5. N-0024 — systematic enumeration (own, before implementer evidence)

### 5.1 Rail leaves (`navConfig` live+partial, rendered for Local Admin)

Every rail leaf href in the 1280 a11y tree matched `navConfig.ts`. Domain homes remain hubs (`/lineup`, `/admin/users`, `/supply`, …) — D-0010 Option A, not this class.

Clicked (final URL):

| Control | Final URL | Page job |
|---|---|---|
| Rail Lineup cases | `/lineup/cases` | Lineup cases tab selected |
| Rail Users & roles | `/admin/users/list` | Users & roles tab; Tenant users table |
| Administration **domain** header | `/admin/users` | Administration hub (contrast; not a leaf mismatch) |
| Rail Sell-through | `/channel-intelligence` | Sell-through tab selected (honesty landing, not this class) |
| Rail Receipts & POD | `/admin/shipment-evidence` | Receipts & POD tab (partial; documented) |
| Rail Plan templates | `/commercial-planner/cpor-cases/historical-import` | Plan templates tab |
| Rail Payments | `/commercial-planner/cpor-cases/payment-evidence-import` | Payments tab |
| Rail Promotion planner | `/promotions` | Promotion planner tab |
| Rail Terms & assumptions | `/admin/customer-commercial-terms` | Terms & assumptions tab |
| Import Center footer “Lineup cases” | `/lineup/cases` | Lineup cases |

No extra rail-leaf mismatch of the Lineup-cases-to-hub class.

### 5.2 Brief / Overview attention (`brief_signals.py` + live blotter)

Live blotter on `/brief` (Overview hub): 3 urgent · 0 informational.

| Signal | Title (live) | `action_label` (source) | `action_href` | Clicked final URL |
|---|---|---|---|---|
| failed_imports | 46 failed imports · steward queue | Open steward queue | `/admin/mappings` | `/admin/mappings`, Steward queue tab selected — **VERIFIED** |
| cover_breach | 102 pairs under 4 weeks of cover | Open Stock · Cover | `/stock?lens=cover&status=under4w` | same URL; Cover tab selected; Under 4w chip **filled** (`MuiChip-filled` / `colorError`); Under 2w and 2–4w outlined — **VERIFIED** |
| inbound_open | 2110 inbound shipments not received | Open Supply · Shipments | `/supply/shipments` | `/supply/shipments`, Shipments tab; no `/shipping` in the final URL — **VERIFIED** |
| soh_recon_not_run | (not live) | Open Stock · Cover | `/stock?lens=cover` | **UNVERIFIED** click |
| sell_out_gap | filtered (`data_unavailable`) | Import sell-out | CST import | not shown |
| settlement_blocked / missing_assumptions | not live | Open Settlement | `/commercial-planner/cpor-cases` | not shown; recorded as Case book, not this class |

`REPLENISHMENT_WOC_THRESHOLD_WEEKS = 4.0`. Cover chip Under 4w · 467 = 430 + 37.

### 5.3 Hub Workflows

| Hub | Row | href in tree | Clicked? |
|---|---|---|---|
| Planning `/lineup` | Lineup cases | `/lineup/cases` | **VERIFIED** → `/lineup/cases` |
| Planning | Plans & line economics | `/commercial-planner` | href **VERIFIED** in tree |
| Administration `/admin/users` | Users & roles | `/admin/users/list` | href **VERIFIED** in tree; Users **figure** clicked → `/admin/users/list` |
| Administration | Operations / SQL / Settings | `/admin/ops` `/admin/sql-viewer` `/settings` | href **VERIFIED** in tree |
| Supply `/supply` | Shipments / Receipts / PO | navConfig hrefs | href **VERIFIED** in tree |

### 5.4 Headline figures

| Figure | Final URL / behaviour |
|---|---|
| Planning Lineup cases | `/lineup/cases` **VERIFIED** |
| Planning Plan units | `/commercial-planner` **VERIFIED** |
| Planning Shipped vs plan | `/stock?lens=execution`, Execution vs plan tab **VERIFIED** |
| Admin Users | `/admin/users/list` **VERIFIED** |
| Supply Open shipments | `/supply/shipments` **VERIFIED** |
| Supply Unreceived past ETA | `/supply/shipments` **VERIFIED** (not `/admin/shipment-evidence`) |
| Cover Under 2 weeks / 2–4 weeks / Over 8 weeks | in-page `status` filter (matches label) |

### 5.5 Reconcile with implementer (after own enum)

Implementer table rows 1–10 match this review’s clicks. Rows 11–14:

- Getting-started: **not a live route** (middleware → `/brief`). Source still `/lineup/cases`.
- Import Center footer: **VERIFIED** click this session.
- Market “Planning lineup”: **not rendered** on hub landing; source `/lineup/cases`.
- PO case chip: source `/lineup/cases`; **not clicked**.

No additional live mismatch of the class was found that the implementer omitted. Unused `BriefPageContent` is a coverage note, not a remaining wrong href.

---

## 6. Gates

Independent quality + verification events are recorded by this run against `.eif/audit/GOV008_N0023_N0024_20260914/independent-rendered-review.md`. `target_artifact_class: high_fidelity` already materialized; delivered class is live production UI.

---

## 7. Skipped / not claimed

- Keyboard, axe, 390 named-workflow journeys (N-0024 is destinations; N-0023 drawer tokens only).
- Market Planning lineup live click; PO chip live click; `soh_recon_not_run` live click.
- `browser_cdp`.
- Writes to `cip`.

---

## 8. Engine complete (this session)

First `node.status → complete` on N-0024 was refused **QUALITY_GATE**: `design_execution_decisions.responsive_decision.status` was `na`. Engine requires `applicable` or `not_applicable`. Corrected to `not_applicable` (destination URLs, not a named 390 workflow). Retry succeeded.

| Node | Verdict | Engine status | Node revision after complete |
|---|---|---|---|
| N-0023 | **VERIFIED** | **complete** | 38 |
| N-0024 | **VERIFIED_WITH_LIMITATIONS** | **complete** | 39 |

Programme views regenerated. `implementation_run` remains `NS11_RAIL_20260913` / `NS12_NAV_DEST_20260913`. Independent pass provenance is this run/`gov-008`.
