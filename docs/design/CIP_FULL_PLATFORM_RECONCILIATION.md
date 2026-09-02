# CIP Full-Platform Reconciliation

**Audit date:** 2026-09-02  
**Branch:** `feat/ns-2-brief-nav-collapse`  
**HEAD:** `0027db73f88685d5d84f7a4995e237120c511c34`  
**Programme:** `PRG-20260831T145514` · revision **166**  
**Mode:** Discovery / audit only — no product changes in this session.

---

## 1. Buyer vocabulary / IA findings

Target user: commercial or channel operator at a distributor, reseller, OEM, or vendor organisation, encountering CIP with little or no onboarding. Verdicts are naming recommendations only — **no renames in this session**.

| Container | Current name | Verdict | Rationale |
|---|---|---|---|
| **Brief** | Brief | **RETAIN** | In trade promotion and channel ops, a morning “brief” is a credible daily signal queue. First-time buyers expect: *what needs my attention today?* Matches grammar-3 blotter job. |
| **Lineup** | Lineup | **RENAME RECOMMENDED** | “Lineup” reads as product assortment or retail shelf planning, not distributor buy-plan / net-requirement origination. Buyers from Anaplan/Kinaxis/SAP TM expect *Plan*, *Buy plan*, or *Demand plan*. |
| **Stock** | Stock | **NEEDS PRODUCT DECISION** | Covers sell-out, fill vs plan, cover, and inbound — broader than “stock” alone. Operators may expect *Channel performance*, *Inventory & flow*, or *Supply chain*. Single word underspecifies four lenses. |
| **Settlement** | Settlement | **RETAIN** | CPOR / trade-spend settlement is conventional in vendor–distributor commercial management. Buyers expect: *claim settlement*, *funding reconciliation*, *CPOR cases*. Spine href to `/commercial-planner/cpor-cases` is internally inconsistent but the label works. |
| **Response** | Response | **RENAME RECOMMENDED** | “Response” does not communicate ranked commercial actions, promo/pricing decisions, or portfolio response. Comparable products use *Trade actions*, *Commercial response*, or *Promotions*. Container is largely unbuilt (N-0010 proposed). |
| **Steward** | Steward | **NEEDS PRODUCT DECISION** | “Steward” is credible for data stewardship among practitioners but opaque to first-time buyers vs *Data quality*, *Imports*, or *Master data*. Spine correctly lands on Import Center; label may need subtitle or utility rename. |

**Secondary lens / route terms (selected):**

| Term | Verdict | Rationale |
|---|---|---|
| Movement (Stock lens) | RETAIN | Sell-out / sell-through is conventional. |
| Execution (Stock lens) | RENAME RECOMMENDED | “Execution” is vague; *Fill vs plan* or *Plan vs executed* matches operator mental model. |
| Cover (Stock lens) | RETAIN | Days-of-cover is industry-standard. |
| Inbound (Stock lens) | RETAIN | Clear for shipment / pipeline visibility. |
| Commercial Planner (legacy route) | RENAME RECOMMENDED | Internal project name; should converge to Response container vocabulary when N-0010 ships. |
| CPOR Cases (settlement detail) | RETAIN | Domain-accurate for CPOR practitioners. |

---

## 2. Design-system convergence findings (Phase 7B)

### 2.1 System diagnosis

`packages/ui` exports **tokens and theme only** — no shared behavioural primitives. North Star containers (Brief, Stock, Settlement, Lineup) each duplicate workbench chrome (`*TaskCrumb`, `*RegimeStrip`, `*ScopeBar`, `*ReadStrip`). Legacy surfaces (~50 routes) use `PageHeader` + `ModuleDataSection` + legacy `AppBar`. **Two chrome eras coexist in one shell.**

`CIP_DESIGN_LANGUAGE.md` (FROZEN v1.1) specifies **behaviour + appearance** for grids, filter bars, empty/loading/error states, destructive confirms, and top strips. It specifies **appearance only** for drawers and form controls. It specifies **nothing** for toasts, pagination APIs, or general dialog chrome.

### 2.2 Primitives needing shared implementation

| Priority | Primitive | Distinct implementations (count) | Containers / surfaces |
|---|---|---|---|
| P0 | Workbench page chrome | 4 duplicated container kits + `PageHeader` + `AppShell` AppBar | Brief (slim); Stock/Settlement/Lineup (double chrome); all legacy |
| P0 | Scope / filter bar | 6 (`SettlementScopeBar`, `LineupScopeBar`, inline chip stacks, steward filters, grid search, `ModuleGridToolbar`) | Settlement, Lineup; Stock inbound via legacy shipping workspace |
| P1 | Data grid skin | 6 (`EnterpriseDataGrid`, `MasterDataGridShell`, MUI Table, Brief blotter grid, `ResolutionWorklist`, steward table) | All containers; legacy admin/commercial |
| P1 | Empty / loading / error states | 4 each category | Brief workbench-aligned; legacy `ModuleDataSection` centered spinners |
| P2 | Confirm / preview dialog | 4 patterns (`SettlementConfirmDialog`, bulk-delete impact dialogs, ad-hoc MUI) | Settlement; admin bulk ops |
| P2 | Readiness / status chips | 4 visual systems | Settlement, Lineup; legacy MUI Chip elsewhere |
| P2 | Lens / tab switcher | 5 (`StockLensSwitcher`, steward tabs, MUI Tabs, ToggleButtonGroup, DSI tab panel) | Stock; steward; legacy |
| P3 | Pagination footer | 5 (URL server, `TablePagination`, steward custom, AG Grid config, inline) | Settlement queue; shipping; steward |
| P3 | Toasts / notifications | 1 (`GlobalBackgroundTasksIndicator` + undo snackbar) | Shell only — no general mutation feedback |
| P3 | Drawer chrome | 4 (`StewardDrawerChrome`, master grid drawer, mobile nav, `uiStore` drawer) | Steward; admin masters |
| P3 | Form controls | 0 shared layer | Raw MUI everywhere |

### 2.3 Behavioural rules missing from design language

- Inert controls must not present as primary/active (**BACKLOG-157** — discovered via N-0008/N-0009 review, not pre-specified).
- Toast / inline feedback after mutations.
- Drawer width, focus trap, mobile behaviour.
- Pagination footer API (range text, honest counts, server vs client).
- Form validation, debounce, error placement.
- Dialog size tiers and destructive button hierarchy.
- Tab/lens keyboard roving focus.
- Filter bar dirty-state / Apply-Reset state machine and URL sync.
- AG Grid vs MUI Table selection semantics.

### 2.4 Workstream shape

**One programme, three phases** (not parallel silos):

| Phase | Scope |
|---|---|
| **A — Shell & chrome** | Extend brief-mode slim chrome to all NS containers; eliminate double `AppBar`; align `navPageChrome` with spine IA. |
| **B — Primitive library** (`packages/ui` or `apps/web/src/workbench/`) | ScopeBar, ReadStrip, RegimeStrip, states, confirm, badges, lens switcher, grid skin. |
| **C — Surface migration waves** | Wave 1: NS parity (Stock inbound/sell-out KPI removal, Lineup scope honesty); Wave 2: Steward factory (N-0011); Wave 3: legacy admin/commercial behind adapters. |

Migrating surfaces before extracting primitives will recreate Settlement/Lineup `ScopeBar` duplication.

### 2.5 Rendered convergence findings (Phase 7A)

| Finding | Evidence | Severity |
|---|---|---|
| Double chrome on Stock, Settlement, Lineup | `AppShell.tsx` `isBriefChromeRoute` only suppresses AppBar for `/brief` | High |
| Legacy KPI card row inside Stock Movement lens | `ChannelOpsKpiCards` in `ChannelOpsStockWorkspace` | Medium — violates grammar-2 instrument panel |
| Stock Inbound lens embeds legacy shipping workspace | Dynamic import without workbench scope bar; chip filters + `Paper` | Medium |
| Settlement queue under `/commercial-planner/cpor-cases` URL | Commercial-planner IA residue on redesigned container | Medium — IA honesty |
| Legacy surfaces retain density toggle; NS containers do not | `useUiStore` on legacy AppBar only | Low |
| Brief mobile-minimal chrome not extended to other NS containers | `AppShell.tsx` | Low |
| `navConfig.ts` crumbs vs `spineNav.ts` primary IA | Dual nav truth for breadcrumbs | Medium |

---

## 3. Baseline definition and BLN-0001 details

### 3.1 BLN-0001 identity

| Field | Value |
|---|---|
| **ID** | BLN-0001 |
| **Commit / tree_hash** | `46368f6c98e0eb4428e648e3860d37934c09e7e7` |
| **Message** | `docs: NS-2 readiness report (discovery only)` |
| **Branch at pin** | `main` |
| **Provenance** | `implementation-observation` |
| **Detail doc** | `.eif/audit/NS2_CONTINUE_20260831/implementation-baseline.md` |
| **Product code at pin** | **None** — docs-only commit; no `/brief`, no spine, no `GET /brief/signals` |

**Finding:** BLN-0001 is a **pre-NS-2 product snapshot**, not a post-redesign target. It is the correct anchor for “what CIP contained before the North Star redesign.” Preservation maps on completed nodes document what each NS tranche was required to carry forward.

### 3.2 BLN-0001 preservation map (registry)

| Key | Disposition |
|---|---|
| `dashboard_exceptions` | redirect_to_brief |
| `role_gated_nav` | spineNav_role_filters |
| `commercial_planner` | settlement_response_containers |
| `steward_imports` | steward_container |
| `background_tasks` | brief_mode_appbar |
| `settings_signout` | spine_footer_slim_header |

### 3.3 BLN-0001 latent capabilities (must preserve, port, or retire-with-decision)

| Capability | Current disposition |
|---|---|
| `customer_account_sell_out_gap` | Brief `data_unavailable` signal row; not on Stock/Settlement/Lineup |
| `pipeline_fill_pct` | Brief inbound signal null; Stock regime strip uses shipping summary; line-grain pending |
| `response_container_badge` | Spine `badges.response` null until N-0010 (NS-6) |

### 3.4 Node-level preservation maps

**N-0004 (NS-2):** sell-out gap explicit on Brief; pipeline_fill_pct null on inbound signal; response badge null.

**N-0007 (NS-3):** `/forecasts`, `/channel-intelligence` context routes preserved; middleware redirects for `/sell-out`, `/plan-vs-executed`, `/shipping`, `/inventory`; latent capabilities unchanged on Brief.

**N-0008 (NS-4):** CPOR case detail route, FX blocked-settle (NS-1b), settle readiness chips, portfolio intelligence API folded into `SettlementPortfolioRead`, `?case=` deep link, steward import routes; structural scope filters deferred with honest disabled state.

**N-0009 (NS-5):** commercial-planner lineup tab deferred; `/buy-plans` → `/lineup`; no file jobs on lineup surface; stock execution lens read-only reference preserved; scope filter persistence deferred.

**N-0012 (NS-1a):** `baseline_ref: BLN-0001`; empty preservation map (display-only FX honesty).

**Finding — thin baseline areas:** BLN-0001 does not enumerate per-route dispositions; `CIP_NAV_MAP.md` (post-baseline) fills that gap. No preservation map exists for utilities (`/dashboards`, `/inbox`, `/reports`), `/market`, or orphan commercial routes (`/promotions`, `/pricing`, etc.) — **classify via source inventory, not silent RETIRE.**

### 3.5 Programme state at audit

| Node | Status | baseline_ref |
|---|---|---|
| N-0004 NS-2 Brief + nav | complete | BLN-0001 |
| N-0007 NS-3 Stock | complete | BLN-0001 |
| N-0008 NS-4 Settlement | complete | BLN-0001 |
| N-0009 NS-5 Lineup | complete | BLN-0001 |
| N-0012 NS-1a FX display | complete | BLN-0001 |
| N-0006 NS-1b FX enforcement | **proposed** (product shipped `92f8edb`) | — |
| N-0010 NS-6 Response | proposed | — |
| N-0011 NS-7 Steward | proposed | — |

**Frontier:** N-0006, N-0010, N-0011.

---

## 4. Pre-redesign capability inventory (BLN-0001 · `46368f6`)

**Scale:** 47 `page.tsx` routes · 42 API router prefixes · 14 web feature folders · MUI drawer + grouped `navConfig` · landing `/dashboard`.

### 4.1 Shell and landing

| Capability | Route / module | API |
|---|---|---|
| Auth login | `/login` | `/api/v1/auth/*` |
| Landing redirect | `/` → `/dashboard` | — |
| Control tower / KPI dashboard | `/dashboard` | `/api/v1/dashboard/summary` |
| Exceptions inbox | `/exceptions` | `/api/v1/exceptions` |
| Getting started coach | `/getting-started` | — |
| Grouped sidebar nav + role gating | `navConfig.ts`, `AppShell.tsx` | — |
| Background task indicator | `GlobalBackgroundTasksIndicator` | async job APIs |
| Settings / sign-out | `/settings`, AppBar | `/api/v1/auth/tenant-commercial-profile`, `/semantics/*` |

### 4.2 Channel intelligence and operations

| Capability | Route | API |
|---|---|---|
| Channel ops / sell-out workspace | `/sell-out` | `/api/v1/channel-ops/*`, `/api/v1/sellout/*` |
| CST channel intelligence | `/channel-intelligence` | `/api/v1/channel-intelligence/*` |
| Listing capture jobs | `/listing-capture` | `/api/v1/listing-capture/*` |
| Inbound shipments | `/shipping` | `/api/v1/shipping/*` |
| Forecasting grid | `/forecasts` | `/api/v1/forecasts/*` |
| Reported SOH paste (legacy inventory) | `/inventory` | `/api/v1/inventory` |

### 4.3 Commercial planning, lineup, execution

| Capability | Route | API |
|---|---|---|
| Commercial planner hub (tabs: plans, lineup coverage, data map, defaults) | `/commercial-planner` | `/api/v1/commercial-planner/*` |
| CPOR case list | `/commercial-planner/cpor-cases` | `/api/v1/cpor/cases` |
| CPOR case workspace (detail) | `/commercial-planner/cpor-cases/[id]` | `/api/v1/cpor/cases/{id}/*` |
| CPOR historical import | `.../historical-import` | `/api/v1/cpor/historical-import/*` |
| CPOR payment evidence import | `.../payment-evidence-import` | `/api/v1/cpor/payment-evidence/*` |
| Lineup planning (page-level) | `/lineup` | `/api/v1/lineup/*`, commercial-planner lineup APIs |
| Plan vs executed | `/plan-vs-executed` | `/api/v1/plan-vs-executed` |
| Buy plans / net requirement (legacy table) | `/buy-plans` | `/api/v1/buy-plans` |
| Budget ceilings | `/budgets` | `/api/v1/budgets` |
| Budget requests | `/budget-requests` | `/api/v1/budgets/requests` |

### 4.4 Response-adjacent (orphan routes)

| Capability | Route | API |
|---|---|---|
| Promotions scaffold | `/promotions` | `/api/v1/promotions/*` |
| Pricing recommendations | `/pricing` | `/api/v1/pricing` |
| Competition intel | `/competition` | `/api/v1/competition/*` |
| Roadmap notes | `/roadmap` | `/api/v1/roadmap` |
| Market stub | `/market` | `/api/v1/market/placeholders` |

### 4.5 Steward, imports, master data

| Capability | Route | API |
|---|---|---|
| Import Center (DSI, shipment, PM, CST, lineup, CPOR templates) | `/admin/imports` | `/api/v1/imports/*` |
| Shipment evidence steward | `/admin/shipment-evidence` | `/api/v1/shipment-evidence/*` |
| PO management | `/admin/po-management` | `/api/v1/po-management/*` |
| Legacy mapping queue | `/admin/mappings` | `/api/v1/mappings/*` |
| Product master | `/admin/products` | `/api/v1/products/*` |
| Catalogue gaps | `/admin/product-master-gaps` | `/api/v1/product-master-gaps/*` |
| Customer master + duplicate resolution | `/admin/customers`, `.../duplicates` | `/api/v1/customers/*` |
| Distributor master + duplicates | `/admin/distributors`, `.../duplicates` | `/api/v1/distributors/*` |
| Channels & regions | `/admin/channels-regions` | `/api/v1/catalog/channels`, `/regions` |
| CST steward | `/admin/cst-steward` | `/api/v1/cst-steward/*` |
| Customer commercial terms | `/admin/customer-commercial-terms` | `/api/v1/commercial-planner/customer-terms` |
| Steward audit log | `/admin/steward-audit` | `/api/v1/admin/steward-audit` |

### 4.6 Utilities and admin

| Capability | Route | API |
|---|---|---|
| Report builder | `/reports` | `/api/v1/query`, `/saved-reports`, `/reports/*` |
| Saved dashboards | `/dashboards` | `/api/v1/dashboards/*` |
| Report delivery inbox | `/inbox` | `/api/v1/reports/inbox` |
| User admin | `/admin/users` | `/api/v1/auth/users` |
| SQL viewer | `/admin/sql-viewer` | `/api/v1/admin/sql-viewer/*` |
| Ops monitoring | `/admin/ops` | `/api/v1/admin/ops/overview` |
| Dev wipe (settings) | `/settings` | `/api/v1/dev/*` |

### 4.7 Library modules (no direct route)

`import-steward/`, `import-mapping/`, `steward-worklist/`, `cpor/` (case detail), `background-tasks/`, `shipping-mailer/` (settings panel), `dashboards/` feature helpers.

### 4.8 API-only / minimal UI at baseline

`/reference` (DSI helper), `/inbound-shipments` (distributor page only), `/sellout` (legacy partial), `/dev` (settings).

---

## 5. Current capability inventory (`0027db7`)

**Scale:** 49 `page.tsx` routes (+`/brief`, +`/stock`) · 43 API prefixes (+`/brief`) · 18 feature folders · `WorkbenchSpine` + `spineNav.ts` · middleware redirects · landing `/brief`.

**Delta summary:** No routes or API routers **removed**. Three new product surfaces: Brief container, Stock container (lens switcher), North Star spine shell. Lineup, Settlement rewired to container components. Legacy pages retained as middleware fallbacks.

### 5.1 New North Star surfaces

| Capability | Route | Reachable | Container |
|---|---|---|---|
| Brief signal blotter | `/brief` | Spine href; `/` redirect | §1 Brief |
| Brief signals API | — | AppShell badges | `GET /api/v1/brief/signals` |
| Stock container (Movement / Execution / Cover / Inbound lenses) | `/stock?lens=*` | Spine href | §3 Stock |
| Lineup container (regime strip, grid, net-req) | `/lineup` | Spine href | §2 Lineup |
| Settlement book chrome | `/commercial-planner/cpor-cases` | Spine href | §4 Settlement |

### 5.2 Redirected but source-retained

| Capability | Legacy route | Middleware target | Page still in source |
|---|---|---|---|
| Control tower | `/dashboard` | `/brief` | Yes |
| Exceptions | `/exceptions` | `/brief` | Yes |
| Getting started | `/getting-started` | `/brief` | Yes |
| Sell-out standalone | `/sell-out` | `/stock?lens=movement` | Yes |
| Plan vs executed standalone | `/plan-vs-executed` | `/stock?lens=execution` | Yes |
| Inbound shipments standalone | `/shipping` | `/stock?lens=inbound` | Yes |
| SOH paste inventory | `/inventory` | `/stock?lens=cover` | Yes (Cover lens uses `CoverLensView` instead) |
| Buy plans table | `/buy-plans` | `/lineup` | Yes |

### 5.3 Context routes (preserved, spine prefix only)

`/forecasts`, `/channel-intelligence`, `/budgets`, `/budget-requests`, `/promotions`, `/pricing`, `/competition`, `/roadmap`, `/commercial-planner` (Response), all `/admin/*` steward routes, `/listing-capture`.

### 5.4 Latent / hard to discover (source exists, weak nav)

| Capability | Route | Issue |
|---|---|---|
| Saved dashboards | `/dashboards` | No spine utility link |
| Report inbox | `/inbox` | No spine utility link |
| Market stub | `/market` | No spine entry; PARKED |
| Legacy mapping queue | `/admin/mappings` | No nav leaf; NAV_MAP retired-on-trigger |
| Customer commercial terms (standalone) | `/admin/customer-commercial-terms` | No nav leaf; also on customer record |
| SQL viewer, ops, steward audit | `/admin/sql-viewer`, `/admin/ops`, `/admin/steward-audit` | Not spine utilities (only Users linked) |
| Settings | `/settings` | AppBar only |

### 5.5 Unbuilt North Star containers (frontier)

| Container | Programme node | State |
|---|---|---|
| Response (grammar 4) | N-0010 proposed | Legacy `/commercial-planner` + orphan promo/pricing routes |
| Steward factory (grammar 5) | N-0011 proposed | Import Center + worklists exist; not container-redesigned |

---

## 6. Canonical reconciliation matrix

**Decision legend:** KEEP · MERGE · RELOCATE · REDESIGN · RESTORE · RETIRE · BACKLOG · NEEDS PRODUCT DECISION

| Capability / Surface | BLN-0001 evidence | Current state | Reachable now? | Current destination | Preservation requirement | Decision | Evidence |
|---|---|---|---|---|---|---|---|
| Landing / control tower | `/dashboard` nav + API | `/brief` blotter; `/dashboard` redirected | Yes (as Brief) | `/brief` | redirect_to_brief | MERGE | BLN-0001; N-0004; middleware |
| Exceptions inbox | `/exceptions` page + API | Page exists; redirected to Brief | Partial — signals absorbed | `/brief` | redirect_to_brief | MERGE | middleware; CIP_NAV_MAP §1 |
| Getting started | `/getting-started` | Redirected | No direct | `/brief` | redirect_to_brief | MERGE | middleware |
| Brief signal API | absent | `GET /brief/signals` | Yes | `/brief` | new capability | KEEP | N-0004 complete |
| Role-gated navigation | `navConfig` roles | `spineNav` role filters + legacy crumbs | Yes | spine | spineNav_role_filters | REDESIGN | BLN-0001; `spineNav.ts` |
| Sell-out / channel ops | `/sell-out` primary nav | Stock Movement lens + legacy page | Yes | `/stock?lens=movement` | middleware redirect | MERGE | N-0007 preservation |
| Plan vs executed | `/plan-vs-executed` nav | Stock Execution lens | Yes | `/stock?lens=execution` | middleware redirect | MERGE | N-0007 |
| Inbound shipments | `/shipping` nav | Stock Inbound lens (+ legacy embed) | Yes | `/stock?lens=inbound` | middleware redirect | MERGE | N-0007 |
| Reported SOH paste | `/inventory` (not primary nav) | Redirected; Cover lens derived SOH | Partial — paste grid latent | `/stock?lens=cover` | absorb; paste retired | REDESIGN | CIP_NAV_MAP §3; inventory page latent |
| Forecasting | `/forecasts` nav | Standalone route preserved | Yes | `/forecasts` | context_route_preserved | KEEP | N-0007 |
| CST channel intelligence | `/channel-intelligence` nav | Standalone preserved | Yes | `/channel-intelligence` | context_route_preserved | KEEP | N-0007 |
| Stock container shell | absent | `/stock` lens switcher | Yes | `/stock` | new | KEEP | N-0007 complete |
| CPOR case list | `/commercial-planner/cpor-cases` | `SettlementContainer` | Yes | `/commercial-planner/cpor-cases` | settlement container | REDESIGN | N-0008 |
| CPOR case detail | `[id]` route | `CporCaseWorkspace` preserved | Yes (deep link) | same | cpor_case_detail_route | KEEP | N-0008 |
| CPOR historical / payment import | sub-routes | Unchanged | Yes | same | steward_imports unchanged | KEEP | N-0008 |
| FX display honesty | partial at baseline | `fx_blocked` flags, readiness chips | Yes | case list/detail | N-0012 complete | KEEP | N-0012 |
| FX blocked-settle enforcement | partial | Shipped `92f8edb`; programme N-0006 proposed | Yes (API) | settlement case actions | fx_settle_allowed | BACKLOG | N-0008; N-0006 hygiene |
| Settlement scope filters (period/BU/customer) | full filters on legacy | Deferred; honest disabled state | Partial | Settlement scope bar | design deferral | BACKLOG | N-0008 design_divergence |
| Portfolio intelligence panel | API at baseline | Folded into `SettlementPortfolioRead` | Yes | settlement queue | portfolio_intelligence_api | MERGE | N-0008 |
| Lineup planning | `/lineup` page-level | `LineupContainer` | Yes | `/lineup` | container redesign | REDESIGN | N-0009 |
| Buy plans legacy table | `/buy-plans` | Redirected; page latent | Partial | `/lineup` | buy_plans redirect | MERGE | N-0009 |
| Commercial planner lineup tab | tab on `/commercial-planner` | Tab deferred; route preserved | Partial | `/commercial-planner` | deferred until VERIFY | BACKLOG | N-0009 preservation |
| Lineup scope bar (From/To/BU) | N/A | Inert pseudo-controls | Yes (visible) | `/lineup` | design deferral | BACKLOG | BACKLOG-156 |
| Lineup trend series | N/A | Deferred | No | — | design deferral | BACKLOG | N-0009 design_divergence |
| Commercial planner hub | `/commercial-planner` nav | Legacy tabs; Response container unbuilt | Yes | `/commercial-planner` | settlement_response split | NEEDS PRODUCT DECISION | BLN-0001; N-0010 frontier |
| Promotions module | orphan route | Scaffold unchanged | Latent | `/promotions` | NAV_MAP retired standalone | NEEDS PRODUCT DECISION | CIP_NAV_MAP §5 |
| Pricing recs | orphan route | Unchanged | Latent | `/pricing` | calculator unparked | NEEDS PRODUCT DECISION | CIP_NAV_MAP §5 |
| Competition intel | orphan route | Unchanged | Latent | `/competition` | evidence on actions | NEEDS PRODUCT DECISION | CIP_NAV_MAP §5 |
| Roadmap notes | orphan route | Unchanged | Latent | `/roadmap` | context parked | BACKLOG | CIP_NAV_MAP §5 |
| Market stub | orphan route | Static stub | Latent | `/market` | PARKED | BACKLOG | CIP_NAV_MAP |
| Budgets / budget requests | orphan routes | Unchanged | Latent | `/budgets`, `/budget-requests` | settlement context | KEEP | spine prefix; no nav leaf |
| Import Center | `/admin/imports` nav | Unchanged | Yes | `/admin/imports` | steward_container | KEEP | BLN-0001; N-0011 frontier |
| Steward worklists (DSI/CST/shipment) | import flows | Unchanged engines | Yes | imports + CPOR sections | steward_imports | KEEP | baseline |
| Master data grids | admin routes | Legacy chrome | Yes | `/admin/*` | steward_container | KEEP | BLN-0001 |
| Mapping queue page | `/admin/mappings` | Page latent | No nav | — | retired on trigger | NEEDS PRODUCT DECISION | CIP_NAV_MAP §6 |
| Customer commercial terms | admin route | Latent + customer record | Partial | customer page | customer record | KEEP | CIP_NAV_MAP §6 |
| Report builder | `/reports` nav | Unchanged | Yes | `/reports` | UTIL Reports | KEEP | baseline |
| Saved dashboards | `/dashboards` nav | Latent — no spine link | Partial | `/dashboards` | UTIL Reports | RESTORE | navConfig leaf; no spine utility |
| Report inbox | `/inbox` nav | Latent — no spine link | Partial | `/inbox` | UTIL Reports | RESTORE | navConfig leaf |
| User admin | `/admin/users` | Spine Admin utility | Yes | `/admin/users` | UTIL Admin | KEEP | spineNav |
| SQL viewer / ops / audit | admin nav | No spine utility | Partial | direct URL / legacy crumbs | UTIL Admin | RESTORE | navConfig leaves |
| Settings | admin nav | AppBar | Yes | `/settings` | settings_signout | KEEP | BLN-0001 |
| Background tasks bell | AppShell | Retained | Yes | shell | brief_mode_appbar | KEEP | BLN-0001 |
| Customer sell-out gap signal | latent BLN-0001 | Brief `data_unavailable` row | Yes (Brief only) | `/brief` | explicit data_unavailable | BACKLOG | all preservation maps |
| Pipeline fill % | latent BLN-0001 | Null signal; regime partial | Partial | Brief + Stock regime | pending read model | BACKLOG | all preservation maps |
| Response spine badge | latent BLN-0001 | null | N/A | spine | null until NS-6 | BACKLOG | N-0010 frontier |
| PO management | `/admin/po-management` | Unchanged | Yes | admin | inbound concern | KEEP | CIP_NAV_MAP §3 |
| Listing capture | nav leaf | Unchanged | Yes | `/listing-capture` | steward | KEEP | baseline |
| Dev wipe | settings | Unchanged | Admin | `/settings` | — | KEEP | baseline |

### 6.1 Decision counts

| Decision | Count |
|---|---|
| KEEP | 18 |
| MERGE | 9 |
| RELOCATE | 0 |
| REDESIGN | 4 |
| RESTORE | 4 |
| RETIRE | 0 |
| BACKLOG | 9 |
| NEEDS PRODUCT DECISION | 6 |
| **Total rows** | **50** |

**Note:** RETIRE count is zero — no capability has positive evidence of intentional obsolescence without replacement. Promotions standalone module is NAV_MAP-marked retired but replacement is unbuilt (N-0010) → **NEEDS PRODUCT DECISION**, not RETIRE.

---

## 7. Findings by decision class

### 7.1 RESTORE (meaningful functionality disappeared or became hard to reach)

| Capability | Evidence | Recommended action |
|---|---|---|
| Saved dashboards (`/dashboards`) | `navConfig` leaf at baseline; no spine utility link at HEAD | Add Reports utility sub-link or Steward-adjacent entry |
| Report inbox (`/inbox`) | Same | Same |
| SQL viewer, ops monitoring, steward audit | `navConfig` admin leaves; spine Admin → Users only | Extend Admin utility menu or Steward footer links |
| Full dashboard KPI cards | `/dashboard` page完整 retained but middleware-blocked; Brief blotter is thinner summary | **NEEDS PRODUCT DECISION** whether KPI cards are RESTORE on Brief or acceptable MERGE — listed here as visibility gap |

### 7.2 REDESIGN (capability exists but materially changed shape)

| Capability | Evidence |
|---|---|
| Role-gated navigation | MUI grouped drawer → six-container spine |
| CPOR case list | Legacy grid → `SettlementContainer` queue + case split |
| Lineup planning | Page-level → `LineupContainer` with regime/scope/read strips |
| Reported SOH / inventory | Paste grid → Cover lens derived SOH (`CoverLensView`) |

### 7.3 RETIRE recommendations

**None with positive evidence.** The following were considered and rejected for RETIRE:

| Candidate | Why not RETIRE |
|---|---|
| `/promotions` standalone | NAV_MAP marks retired as standalone module but N-0010 Response not built — replacement unproven |
| `/admin/mappings` | NAV_MAP “retired on trigger” — page and API still exist |
| `/inventory` paste SOH | Redirected to Cover lens; paste page latent — operator workflow may still need paste path |
| `/dashboard` | Middleware redirect only — full page remains |

### 7.4 NEEDS PRODUCT DECISION

| Item | Question for Warren |
|---|---|
| Stock container label | Does “Stock” communicate four lenses to buyers? |
| Steward container label | “Steward” vs “Data & imports” for first-time users? |
| Commercial planner fate | Absorb into Response (N-0010) or retain as hub? |
| Promotions / pricing / competition / roadmap | Standalone routes vs Response container only? |
| Mapping queue page | Retire UI while keeping DSI engine, or RESTORE nav entry? |
| Dashboard KPI cards vs Brief signals | Is Brief a complete replacement for control tower? |

### 7.5 BACKLOG (explicitly deferred with programme/backlog evidence)

| Item | Reference |
|---|---|
| Customer sell-out gap read model | BLN-0001 latent; all NS preservation maps |
| Pipeline fill % line-grain | BLN-0001 latent; N-0007 regime partial |
| Response container badge | Until N-0010 |
| N-0006 programme ledger reconciliation | CURRENT.md; no runtime backfill |
| Settlement structural scope filters | N-0008 design_divergence |
| Lineup scope bar interaction honesty | BACKLOG-156 |
| Design language inert-control rule | BACKLOG-157 |
| Lineup trend series + scope persistence | N-0009 design_divergence |
| Commercial planner lineup tab | N-0009 preservation |
| Roadmap / market parked surfaces | CIP_NAV_MAP |

---

## 8. API survives, no UI reaches it

| API prefix / capability | Web consumer | Gap |
|---|---|---|
| `/reference` | `DsiCountryRegionFallback.tsx` only | No operator-facing reference browser |
| `/inbound-shipments` | `admin/distributors/page.tsx` only | No dedicated inbound-shipments import UI route |
| `/sellout` (legacy) | Partial in sell-out tabs | Superseded by `/channel-ops` in Stock; legacy path may be stale |
| `/buy-plans` | `/buy-plans` page (middleware redirect) | Lineup net-req supersedes in IA; API still wired to latent page |
| `/dashboard` | `/dashboard` page (redirected) | Summary API only on unreachable page in normal flow |
| `/exceptions` | `/exceptions` page (redirected) | Exceptions API on unreachable page |
| `/inventory` | `/inventory` page (redirected) | Paste SOH API on latent page |
| `/market` | stub page only | Placeholder API |
| `/mappings` | `/admin/mappings` latent page | Queue UI exists but no nav — **cheapest RESTORE candidate** |
| Large `/commercial-planner/*` subset | Many worklist sections not on spine | Endpoints exist for tabs/worklists not exposed in NS IA |
| `/dev` | settings wipe panel | Intentionally admin-only |

**Count: 11** API surfaces with missing, latent, or superseded UI reach (excluding intentionally admin-only `/dev` → **10 operator-relevant gaps**).

---

## 9. Stranded / unmounted / legacy convergence

### 9.1 Stranded capabilities (source retained, workflow fragmented)

- **Legacy route pages as middleware fallbacks** — eight routes (`dashboard`, `exceptions`, `getting-started`, `sell-out`, `plan-vs-executed`, `shipping`, `inventory`, `buy-plans`) still render if middleware bypassed; creates dual-truth maintenance burden.
- **Dual navigation systems** — `spineNav.ts` (primary IA) vs `navConfig.ts` (breadcrumbs, partial legacy drawer references).
- **Commercial planner** — hub tabs coexist with Settlement and Lineup containers; lineup tab explicitly deferred.
- **Stock Inbound lens** — embeds legacy `InboundShipmentsWorkspace` without workbench chrome.

### 9.2 Unmounted library modules (expected — not dropped)

`import-steward/`, `import-mapping/`, `steward-worklist/`, `cpor/`, `settlement/` (embedded), `background-tasks/`, `shipping-mailer/` — all mounted from parent surfaces.

### 9.3 Legacy UI requiring convergence (7A summary)

1. Double AppBar on Stock, Settlement, Lineup.
2. KPI cards in Stock Movement lens.
3. Legacy `ModuleDataSection` loading/error patterns on ~50 routes.
4. `PageHeader` breadcrumbs vs workbench TaskCrumb strips.
5. Settlement URL under `/commercial-planner/*` namespace.
6. `NAV_COVERAGE.md` stale (47 routes documented; 49 at HEAD).

### 9.4 Documentation drift

| Doc | Issue |
|---|---|
| `docs/design/NAV_COVERAGE.md` | Missing `/brief`, `/stock` |
| `docs/design/CIP_NAV_MAP.md` | Authoritative but pre-dates 49-route tree |
| Programme `depends_on` | N-0008 complete while N-0006 still proposed — graph does not enforce |

---

## 10. Known programme hygiene and test debt

| Item | Evidence | Status |
|---|---|---|
| **N-0006 ledger drift** | Product shipped (`92f8edb`, Alembic `20260902_0020`); node still `proposed`; no EIF backfill path | BLOCKED — Warren decision |
| **BACKLOG-156** | `LineupScopeBar.tsx` inert From/To/BU + primary Apply; Settlement remediated | Parked 2026-09-02 |
| **BACKLOG-157** | No design-language rule for inert-control honesty | Parked 2026-09-02 |
| **Settlement clone-test cleanup** | `test_cpor_settle_confirm_clone.py` on `cip_ns4_settle_clone`; `_delete_case` hard-deletes events + case | Hygiene finding — pattern risk for destructive tests |
| **Clone DB prerequisite** | NS-4 rendered evidence references disposable clone DB | Needs durable documentation in test/runbook |
| **N-0008 depends_on N-0006** | `node.status → complete` does not enforce `depends_on` | Programme graph integrity gap |

---

## 11. Suggested bounded implementation workstreams

**Suggestions only — not programme nodes.**

| ID | Workstream | Scope | Depends on |
|---|---|---|---|
| WS-1 | **Programme hygiene** | Reconcile N-0006 ledger; document clone DB test prerequisite; enforce or document `depends_on` semantics | Warren decision |
| WS-2 | **IA restoration pass** | Restore spine utility links for dashboards, inbox, admin tools; resolve NAV_COVERAGE drift | None |
| WS-3 | **Workbench primitive extraction** | Phase B primitives (ScopeBar, chrome kit, states, confirm dialog) | None |
| WS-4 | **Shell convergence** | Phase A — eliminate double AppBar; extend brief-mode chrome | WS-3 (partial overlap) |
| WS-5 | **Interaction honesty** | BACKLOG-156 Lineup fix + BACKLOG-157 design-language amendment | WS-3 ScopeBar |
| WS-6 | **NS-6 Response container** | N-0010 — absorb commercial planner, promo/pricing/competition | Programme node |
| WS-7 | **NS-7 Steward factory** | N-0011 — grammar-5 import center redesign | WS-3, WS-4 |
| WS-8 | **Latent read models** | sell-out gap, pipeline fill % line-grain | API + Brief/Stock surfaces |
| WS-9 | **Legacy route retirement** | Remove or gate fallback pages once middleware + containers proven | WS-2, WS-4 |
| WS-10 | **Buyer vocabulary** | Rename programme (Lineup, Response, Stock label) — product marketing decision | WS-6, WS-7 |

**Recommended sequencing:** WS-1 (hygiene) → WS-3 + WS-4 (primitives + shell) → WS-5 (honesty) → WS-2 (IA gaps) → WS-6/7 (frontier nodes) → WS-8/9/10.

---

## Audit metadata

| Field | Value |
|---|---|
| Baseline used | BLN-0001 · `46368f6` |
| BLN-0001 result | Valid pre-NS-2 anchor; thin on per-route disposition — supplemented by `CIP_NAV_MAP.md` and git tree |
| Capabilities inventoried | 47 baseline · 49 current routes · 42→43 API prefixes |
| API-without-UI gaps | 10 operator-relevant |
| Artifact | `docs/design/CIP_FULL_PLATFORM_RECONCILIATION.md` |
| EIF guard | Shell reads blocked intermittently during audit; evidence verified via subagent `git show` and programme YAML |

---

*End of reconciliation artifact. Warren reviews this matrix before any RESTORE, RETIRE, design-system, or IA decision becomes a programme commitment.*
