# Independent GOV-008 — N-0025–N-0029

**Run:** `GOV008_N0025_N0029_20260915`  
**Actor:** `gov-008`  
**Mode:** implementation-verification + rendered comparison  
**Independence:** another session than the implementers (`gov-001` / NS13–NS17). Same-mode GOV-008 specialist. R2 nodes; not a second model.  
**HEAD (git):** `cca127f386d66674a3cd2ebf44f9c12f2d8052e9` on `feat/ns-2-brief-nav-collapse` — **VERIFIED**.  
**Viewport:** Playwright MCP `1280×800` (plus N-0025 `390×844`). No `browser_cdp`.  
**Database:** `SELECT current_database()` → `cip` before every SQL batch. Read-only. No writes to `cip`. Create-draft / Apply / upload never clicked.

## Control-plane / working tree

**FACT.** Working tree is dirty vs HEAD. Uncommitted later UX (not these nodes’ implementation runs) includes `StartWorkPanel.tsx` (Card grid → `Panel`/`PanelRow`), `steward_queue.py` (`/admin/imports?job=` → `/admin/mappings?workspace=resolve`), alias-memory filtering, and `EnterpriseDataGrid` clip. Live Playwright therefore saw **running tree**, not a clean checkout of `cca127f`.

That limitation is recorded on every rendered claim. Git diff is used only to separate HEAD product from later dirt.

## Enumeration (own, before implementer evidence)

### N-0025 — Start work + remaining obstructs

| # | Criterion (paraphrase) | How this review tests it |
|---|------------------------|--------------------------|
| 1 | Enumerate existing starts for lineup, CST, shipping, settle, steward (palette, directory, hub Workflows, headlines, headers, Import Center cards) | Palette live; rail + Import Center cards live; Start work live |
| 2 | One Start work on `/brief`; role-gated; verbs open existing screens; Attention exceptions-only | Admin + viewer live; planner SQL |
| 3 | Close remaining obstructs or record why not | Payments/Terms/Claims/Data/sell-through/dashboard/Attention width |
| 4 | Payments/Terms default to wizard/editor; Claims routes to import + case book | Live Payments + Terms |
| 5 | Data four LensTabs; also-here strip | Live Import Center |
| 6 | Sell-through names not ids | Not re-walked this session — **UNCOVERED this review** |
| 7 | Start work prime; empty dashboard not; Attention not clipped at 312px | Live 1280 boxes |
| 8 | Playwright 1280 + Start work at 390 | Done |
| 9 | Do not restructure nav / D-0002 / N-0006 / N-0013 / BACKLOG-181 | Observation only |

### N-0026 — Propose from customer + period

Compose on existing Promotion Planner; lineup then same-customer history; no other-customer ranking; strip must not show the 257% actual/planned percent; Start work `Create promotion plan` → `/promotions?propose=1`; do not confirm create.

### N-0027 — Steward queue by failure type

List `needs_review` across jobs without picking a job; `GROUP BY entity_type` plus registry for label/href; unknown type still appears; click existing engine; `failed_imports` → `/admin/imports?jobStatus=failed` not mappings.

### N-0028 — Start work cards + Lineup cases composition

Import Center outlined `Card`+`CardActionArea` grid, **no Panel wrapper**; seven verbs; Import a lineup → unified import; Lineup cases `HeadlineStrip`+approval `ScopeBar`+grid under Planning chrome, not N-0009 dark crumb/trend.

### N-0029 — Grid clipboard + Case book order

`AgGridReact` only from `EnterpriseDataGrid` with community text selection; Case book working grid above the fold (strip, rail, scope, grid; overlay/ageing below); unmatched Case ID is a link; do not mint `cpor_case`.

---

## N-0025 why the prior GOV-008 never completed

**FACT (programme).** `GOV008_N0025_20260914` recorded `VERIFIED_WITH_LIMITATIONS`, passed required quality/verification, then **`node.lease.release` without `node.status=complete`**. Stage note: steward queue empty legacy (2814 per-job, D-0002); planner live UNVERIFIED (no tenant user); Payments “Back to Payments lens” same-URL leftover. Criterion 11 forbade complete in the **implementation** run; the independent run then also refused complete.

This review re-tests those leftovers live.

## N-0025 findings

### Entry points (AC1)

| Start | Lineup create | CST | Shipping | Settle | Steward |
|-------|---------------|-----|----------|--------|---------|
| Start work `/brief` | `/admin/imports?unified=1` unified dialog **VERIFIED** | wizard type preselected; Choose file after provider **VERIFIED** | inbound wizard **VERIFIED** | Case book **VERIFIED** | `/admin/mappings` queue with rows **VERIFIED** |
| Rail | Planning › Lineup cases (existing cases, not create) **VERIFIED** | Customer sell-through files **VERIFIED** | Import Center / inbound card **VERIFIED** | Case book **VERIFIED** | Steward queue **VERIFIED** |
| Import Center cards | Lineup (unified) outlined card **VERIFIED** | Retailer sell-through card **VERIFIED** | Inbound shipments card **VERIFIED** | (not a card) | (not a card) |
| Command palette | `Planning › Lineup cases` **VERIFIED**; “Import a lineup” not in palette results for query `lineup` **VERIFIED** (create lives on Start work / unified import) | not sampled | not sampled | not sampled | rail Steward queue exists **VERIFIED** |
| Capability directory | not opened this session **UNCOVERED this review** | | | | |

### Start work surface

Admin (Local Admin footer) **VERIFIED:** one Start work panel, seven real links, Attention is blotter-only (`48 failed imports`, cover, inbound — not start verbs). Empty Business dashboard sits **below** Start work.

Viewer (`viewer@local`) **VERIFIED:** “No start actions for this role” / “Nothing this role can start from Overview.” Footer Viewer. Start work still occupies prime at 1280 and at **390×844** (above Needs attention).

Planner live **UNVERIFIED:** `app_user` on `cip` is only `admin@local` (admin) and `viewer@local` (viewer). Creating a planner would write `cip`. `startWork.ts` gates `open-lineup`, `create-promo-plan`, `settle-case` to `admin|planner` — **ASSERTED** from source, not live.

### Verb landings (admin)

- **Import a lineup** → `http://localhost:3000/admin/imports?unified=1` dialog “Unified lineup import (multi-file)” / Choose files. **VERIFIED.** Job start is existing unified import, not `POST /lineup-cases`.
- **Import sell-through** → `?template=customer_sell_through`, selected type CST, Data provider step; after picking an existing provider and Next×3, **Choose file**. **VERIFIED.** Does not land on Choose file in one click.
- **Import a shipping file** → inbound_shipments wizard, selected type shipment evidence. **VERIFIED.**
- **Settle a case** → `/commercial-planner/cpor-cases` Case book (grid above the fold). Confirm-settlement dialog **not** opened this review (N-0029 forbids completing the desk). **VERIFIED** as landing on the book. Prior review’s case-46 confirm is not re-executed.
- **Work the steward queue** → `/admin/mappings` with live candidate grid (not empty legacy). **VERIFIED.** Completing a mapping was not clicked.

### Remaining obstructs

- **Payments** default (no `?import=1`): Choose workbook wizard. **VERIFIED.** “Back to Payments lens” still present (same-URL leftover). **VERIFIED.** Residual, not remediated.
- **Terms** `/admin/customer-commercial-terms` (no `?edit=1`): terms grid + Add terms + Edit. **VERIFIED.**
- **Data:** four LensTabs (Import Center, Steward queue, Master data, Steward audit) + also-here strip (Products, Customers, …). **VERIFIED.**
- **Attention width:** Needs attention column box width **431px** at 1280. AC requires not clipped at 312px. **VERIFIED** (production column ≠ lab 312; text not clipped).
- **Sell-through names:** **UNCOVERED this review** (not opened).
- **Claims rows:** **UNCOVERED this review** (not opened).

### Dirty tree vs N-0025

N-0025 does not require Import Center cards. Panel vs cards is **N-0028**.

**Verdict N-0025: VERIFIED_WITH_LIMITATIONS.** Limitations: planner live absent; Payments same-URL leftover; palette does not list “Import a lineup”; CST needs extra Next clicks; sell-through/claims/directory not re-walked. Steward empty-leaf leftover from 2026-09-14 is **closed** on the running tree (queue lists work). **Complete this node.**

---

## N-0026 findings

Start work **Create promotion plan** href `/promotions?propose=1` **VERIFIED** (admin). Dialog copy: lines from that customer’s lineup or that customer’s history — **not from other customers**. Listing/competitor not joined.

Compose (GET): customer `CUST-000011` / Computer Mania (`dim_customer.id=18`), period `2026Q2`, Propose from evidence. Banner: `Lines: 40 · source: commercial_lineup_line · same-customer comparables: 10`. Real SKUs (e.g. `90NV00H2-M003E0`). Create draft enabled but **not clicked**. Empty **New plan** remains on the planner. **VERIFIED.**

**NUMBER RULE** (`current_database()=cip`):

| Figure | UI | SQL | Class |
|--------|----|-----|--------|
| Compose lines 40 | dialog | Active CM `2026 Q2` lineup lines 46, **distinct product_id 40** (exclude superseded/cancelled cases, `row_status` not superseded) | computation proven (dedupe to product) |
| Same-customer comparables 10 | dialog | not independently counted this review | **ASSERTED** (live banner only) |
| 257% | **absent** on strip and dialog | not displayed | **VERIFIED** absence |
| Strip drafts 0 / ended 74 / settled 210 / planned reserve $253k / actual support $650k | live | `cpor_case` ended=74; settled=211 all, **210** with `intelligence_exclude=false` | ended + settled-book **computation proven**; $253k/$650k **ASSERTED** (not re-derived) |
| Domain header delivery rate 62% | live | not the 257% bias ratio | different grain; **ASSERTED** as delivery-rate caption |

Competition: dialog and banner name same-customer comparables only. No other-customer rank list in the compose dialog. **VERIFIED** for this compose. Planner “Needs a decision … then ranked” is case-condition ranking on the book, not customer-vs-customer propose.

**Verdict N-0026: VERIFIED** with chartered UNCOVERED (competitor prices, listing join, observed WoC as target, uplift) unchanged. **Complete this node.**

---

## N-0027 findings

Queue lists work **without selecting a job** **VERIFIED** (jobs 900, 96, … on one grid).

Grouping chips come from API `groups` (`StewardFailureQueue` maps `payload.groups`). SQL `GROUP BY entity_type` on `needs_review`:

| entity_type | SQL n | Open chip (live, alias-filtered) |
|-------------|-------|----------------------------------|
| product_identifier | 989 | 989 |
| cst_location_token | 790 | 790 |
| customer_dealer_token | 413 | 362 |
| cst_product_token | 407 | 407 |
| shipment_customer_token | 163 | 136 |
| shipment_distributor | 52 | (none — all remembered) |

Open candidates UI **2684** vs SQL/tab **2814**. Difference = alias memory (Already mapped **130**). **Computation proven**; tab 2814 is unfiltered `needs_review`, strip 2684 is filtered. **Label vs filtered grain**, not a silent-corruption.

A future `entity_type` still appears as a group: UI iterates `groups`; missing registry href renders **UNCOVERED**. **VERIFIED** from source. Lab DataSurface hardcodes Customer/Product/Distributor LensTabs; product queue does not.

**Click:** live row `acx12-002125nx` opened `/admin/mappings?workspace=resolve&job=96&…` mounting **DSI mapping candidates** (existing engine) on the queue leaf. **AC literal** is DSI/CST → `/admin/imports?job={id}`. That href is **HEAD** (`href_template`); uncommitted `steward_queue.py` changed it. Live **does not** match the node’s written href. Existing engine **is** what opened; Apply not clicked.

**failed_imports:** Overview **48 failed imports** → `/admin/imports?jobStatus=failed`. SQL unarchived `status=failed` = **48**. Failed last 7 days SQL **7** matches the “FAILED (LAST 7 DAYS) 7” figure (different window). Grid listed failed mailbox jobs. **VERIFIED.** Does not open mappings.

**Verdict N-0027: VERIFIED_WITH_LIMITATIONS.** Limitation: independent live click-through is the uncommitted resolve workspace, not the chartered Import Center job URL (HEAD still has the chartered href). Alias-memory filter is later dirt. **Do not complete** while the running tree’s click path disagrees with the node’s written AC.

---

## N-0028 findings

**HEAD `cca127f` source:** outlined `Card` + `CardActionArea` grid, typography heading, no Panel wrapper. **VERIFIED** (`git diff` against dirty Panel).

**Live running tree:** `MuiPaper` Panel + `PanelRow` links; `cardCountNearStart=0`. **FAIL** vs AC “Import Center outlined Card + CardActionArea grid. No Panel wrapper.”

Import Center behind unified dialog still shows the outlined card grid (Distributor sell-out, Retailer sell-through, …). Start work does **not** match that pattern live.

Seven verbs remain as links **VERIFIED**. Import a lineup unified **VERIFIED**. Create promotion plan href retained **VERIFIED**. Steward copy names failure type **VERIFIED**.

**Lineup cases** `/lineup/cases` **VERIFIED** vs N-0009: Planning chrome + LensTabs; HeadlineStrip (planned units, net, approval, pending, coverage); ScopeBar All / Pending approval; `LineupPlanGrid`; no fake Q1/Q2 trend bars.

**NUMBER RULE:**

| Figure | UI | SQL | Class |
|--------|----|-----|--------|
| 1647 plan lines | strip caption | `fact_lineup_plan_item` count **1647** | computation proven |
| 7,309 planned units | strip | sum `planned_volume_units` **7308.7029** | computation proven (UI rounds) |
| 29 cases · 2 703 lines | Planning header | different grain than strip 1647 | **label** (planning overview vs lineup items) |
| Pending 1646 vs 1647 | chips vs caption | not re-derived | **ASSERTED** |

**Verdict N-0028: VERIFIED_WITH_LIMITATIONS** at HEAD; **rendered FAIL** on running tree for the card pattern. **Do not complete** from this live pass.

---

## N-0029 findings

**Clipboard:** `AgGridReact` imported only from `EnterpriseDataGrid.tsx`; `enableCellTextSelection` + `ensureDomOrder` present. **VERIFIED** source. Native selection not pixel-probed.

**Case book fold (1280×800, scrollY=0):** HeadlineStrip (open book ~y 298) → lifecycle rail (Ended 74 ~y 437) → scope/filters → grid (~y 653, in view). Overlay “Unmatched historical Case IDs” y **2347**; “Outstanding by age” y **3157**. Caption: unmatched IDs are below the grid. Lab FundingSurface puts Alert+rail then ageing **before** the grid; product follows the node’s grid-first challenge. **VERIFIED.**

**Unmatched click:** `C19A50693` is a real link to `/commercial-planner/cpor-cases/payment-evidence-import?code=C19A50693`. Copy: not minted as `cpor_case`. **VERIFIED.**

**Arrival with `?code=`:** URL keeps the param. Body **does not** mention `C19A50693`. Page is the generic Payments wizard (Choose workbook) + “Back to Payments lens”. Source: `payment-evidence-import/page.tsx` has no `searchParams` `code` reader. **VERIFIED** BACKLOG-196.

**Judgement:** a link that advertises a Case ID then lands **unfiltered** is not acceptable as completing the unmatched-token job. It is acceptable only as “open the existing steward without minting a case.” That is a **limitation**, not a silent pass.

**Open book R4.4m / 74 ended / 210 settled:** ended 74 and settled-book 210 match SQL (intelligence_exclude). R4.4m **ASSERTED** (not re-derived).

**Verdict N-0029: VERIFIED_WITH_LIMITATIONS** (`?code=` unread; settlement workspace UNCOVERED; clipboard native-select not exercised). **Do not complete** because N-0027/N-0028 remain open and the payment-evidence follow-through is a real operator miss.

---

## Lab comparison (governing compositions)

- **Import Center cards** (`DataSurface` Start an import): outlined cards. Live Start work matches **HEAD**, not lab Panel of “Start an import” (lab wraps cards in a Panel). N-0028 AC explicitly forbids a wrapper on Start work.
- **Steward lab** hardcodes Customer/Product/Distributor. Product queue groups from `entity_type`. Intentional.
- **FundingSurface book:** Alert+rail, strip, ageing, scope, grid. Product: strip, caption, rail, scope, grid, overlay, ageing. Matches N-0029, not lab order.
- **Lineup cases:** no dedicated lab leaf; product uses HeadlineStrip+ScopeBar+grid under Planning chrome (D-0008 leaf). **VERIFIED** vs pre-D-0008 N-0009 (no dark crumb/trend).

## Dirty-tree note for completion

Complete only where **this session’s live evidence** supports the written AC. Uncommitted later UX is not treated as the node’s product and is not remediated.

| Node | Verdict | Complete? |
|------|---------|-----------|
| N-0025 | VERIFIED_WITH_LIMITATIONS | yes |
| N-0026 | VERIFIED | yes |
| N-0027 | VERIFIED_WITH_LIMITATIONS | no |
| N-0028 | VERIFIED_WITH_LIMITATIONS | no |
| N-0029 | VERIFIED_WITH_LIMITATIONS | no |

---

## Programme recording (this run)

**FACT.** Actor `gov-008`, run `GOV008_N0025_N0029_20260915`. Leases reclaimed then released. No product-source writes. No `cip` writes.

- **N-0025** `complete` revision **60**. First `node.status=complete` was refused (`QUALITY_GATE`): this run’s `design_identity_tokens` dropped `tokens.direction_name` that `GOV008_N0025_20260914` had declared (`start work from overview`). Restored that field from this review’s Overview evidence, then complete succeeded. Lease null.
- **N-0026** `complete` revision **41**.
- **N-0027 / N-0028 / N-0029** remain `in_progress` / `validate`; quality + rendered/referent verification recorded; leases null. Not completed.

Why N-0025 stayed open after `GOV008_N0025_20260914`: that run recorded `VERIFIED_WITH_LIMITATIONS` and **chose not to complete** (empty steward leaf, planner unverified, Payments leftover). This run closed the empty-leaf leftover live; remaining limitations are recorded; identity-token schema was the only additional complete gate.
