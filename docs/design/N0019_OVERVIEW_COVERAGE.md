# N-0019 Overview coverage map

**Source (lab, primary):** `apps/web/src/design-lab/surfaces/OverviewSurface.tsx` (composed Business dashboard ∥ Needs attention + pinned reports) and `apps/web/src/design-lab/surfaces/ReportsSurface.tsx` at `/design-lab/reports`. `labNav.ts` domain `overview`. Judge production against that **composition**, not `LabShell` rail (BACKLOG-181). Frozen design-language HTML and grammar numbers are not cited.

**NUMBER RULE:** print `current_database()` first. Lab Overview widget figures are class **(i) fixture**. Production hub must not copy them. Live figures are class **(iii)** from `GET /api/v1/brief/signals`, `GET /api/v1/dashboards` (widget queries via `/api/v1/query/execute`), and `GET /api/v1/saved-reports`. Never change a number to make lab and production agree.

Measured 2026-09-12 (read-only; `current_database()` printed first):

```
current_database= cip
dashboard_rows= 3
dashboard_widget_rows= 6
saved_report_rows= 3
GET /api/v1/brief/signals → signal_count= 3
ids= failed_imports, cover_breach, inbound_open
as_of= 2026-09-12T08:56:00.799174+00:00
```

`dashboard` rows: id 1 Channel stock board, id 2 test, id 4 Unit 14 canvas. `saved_report` rows: Weeks of cover, WoC smoke, Sell-out units (period by week). Hub meta **VERIFIED** in browser: `3 signals · live from brief/signals`. Attention titles **VERIFIED** live (43 failed imports / 110 pairs under 4 weeks / 1964 inbound not received) — class (iii), not lab fixture KPIs. Hub uses `dashboards[0]` from the list API (observed as **test · 1 widget**), not a copied lab widget set.

---

## Lab routes

| Route | Lab SOURCE | Production analog | Coverage |
|---|---|---|---|
| `/design-lab` | OverviewSurface: dashboard column + attention column + pinned reports | `/brief` hub | **COVERED** (structure) |
| `/design-lab?zone=attention` | Same surface; attention first on mobile | `/brief?zone=attention` | **COVERED** (390 Attention triage) |
| `/design-lab/reports` | ReportsSurface fixture builder | `/reports` ReportBuilderView wrapped in OverviewChrome | **PARTIAL** — relocate existing governed builder; lab fixture run-query UI not copied |

## Production routes (AS-IS → after N-0019)

| Route | AS-IS | After N-0019 | Coverage |
|---|---|---|---|
| `/brief` | Brief-only blotter (`BriefPageContent`) | OverviewChrome + OverviewHub | **COVERED** (relocate signals into attention zone) |
| `/dashboards` | PageHeader + DashboardWorkspace | OverviewChrome wrap; workspace not deleted | **COVERED** |
| `/reports` | PageHeader + ReportBuilderView | OverviewChrome wrap; builder not deleted | **COVERED** |
| `/inbox` | PageHeader + inbox list | OverviewChrome wrap; inbox not deleted | **COVERED** (production-only leaf; not in labNav) |
| In-place Edit/Add widget on the hub | lab OverviewSurface | Edit deep-links to `/dashboards` | **PARTIAL** |
| Pin saved report as Overview widget | lab pinned-reports copy | saved-report list + All reports; no pin-as-widget writer | **UNCOVERED** |
| Role-seeded lab fixture widgets (SOH, cover, funding outstanding, …) | lab `fixtures/dashboard.ts` | not copied; tenant dashboards only | **UNCOVERED** as hub KPIs (honest empty if no dashboard) |
| `/dashboard` legacy | PageHeader “Overview (legacy)” | untouched | **UNCOVERED** leftover |
| `/getting-started`, `/exceptions` | PageHeader crumbs to `/brief` | untouched | **out of Overview map** (not D-0008 overview leaves) |

D-0002 mapping-queue disposition untouched. Rail / tab IA in `navConfig.ts` unchanged this node.

`BriefPageContent.tsx` and `BriefSignalRow.tsx` are not deleted.

---

## Browser

| Check | Viewport | Result |
|---|---|---|
| `/brief` vs lab two-column composition | 1280×800 | **VERIFIED** both surfaces: `innerWidth===1280`; dashboard left, attention right **312px** (lab `gridTemplateColumns` lg `1fr 312px`). Lab h1 `Good morning — Aurora Displays SA` (fixture tenant); production DomainHeader title **Overview** (nav IA unchanged). Lab widgets are fixtures; production live tenant widgets. |
| `/brief?zone=attention` Attention first | 390×844 | **VERIFIED** `innerWidth===390`; stacked; Needs attention y=201 above Business dashboard y=826; pin-as-widget honesty copy visible. |
| `/dashboards` DomainHeader Overview | 1280×800 | **VERIFIED** h1 Overview, crumbs Overview / Business dashboard, `dashboard-create` present, workbench canvas. |
| `/reports` DomainHeader Overview | 1280×800 | **VERIFIED** h1 Overview, crumbs Overview / Reports, governed-builder copy present, workbench canvas. |
| `/inbox` DomainHeader Overview | 390×844 (chrome; not a named 390 workflow) | **VERIFIED** h1 Overview, crumbs Overview / Report inbox, `report-inbox-list` present. |

DIRECTION §6 named 390 workflow for this node: **Attention triage** only. Dashboard editor and report builder stay desktop-first.
