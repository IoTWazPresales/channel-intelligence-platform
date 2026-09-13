# N-0020 Planning coverage map

**Source (lab, primary):** `apps/web/src/design-lab/surfaces/DomainOverviewSurface.tsx` `PlanningSurface` + `apps/web/src/design-lab/shell/labNav.ts` domain `planning`. Lab page `apps/web/src/app/(design-lab)/design-lab/planning/page.tsx` always renders `PlanningSurface` and **ignores** `?lens=`.

N-0009 `LineupContainer` is pre-D-0008 input, not the design source. Judge production against the lab composition, not LabShell rail (BACKLOG-181).

**NUMBER RULE** (`current_database()=cip`, measured 2026-09-12). Lab figures are class **(i) fixture**. Production headlines are class **(iii)**. Never change a number to make two surfaces agree.

| Headline / chart | Lab fixture (i) | Production grain | cip (iii) | Class |
|---|---|---|---|---|
| Lineup cases | 14, caption “P09–P10” | Active `commercial_lineup_case` | **29** cases; periods include 2025 Q1–2026 Q3, 26Q1, NV\Q4, PF\Q4 | (iii) |
| Plan lines (caption) | 1 260 | `commercial_lineup_line` on those cases | **2703** | (iii) |
| Plan units | 96 400 | `sum(quantity_units)` | **273982** | (iii) |
| Shipped vs plan % | fixture shipped/plan | Fill rate `min(shipped, planned)/planned` Execution vs plan default period **26Q3** | **20%** (6586 / 32509) | (iii) |
| Lines not ready | 158 | Any of four gates fail | **2703** (customer terms 0; SKU assumptions 260; distributor 810; cost 260) | (iii) |
| Economics flagged | 280 / 980 ok | `commercial_plan_line.calc_flags` | **0** flagged / **0** planner lines | (iii) |

---

## Lab routes

| Route | Lab SOURCE | Production analog | Coverage |
|---|---|---|---|
| `/design-lab/planning` | DomainOverview: 5 headlines, PairedBars, readiness ProportionBars, attention, workflow PanelRows | New hub at `/lineup` (rail href unchanged) | **COVERED** (structure) / PARTIAL (fill-rate grain, not lab shipped/plan %) |
| `/design-lab/planning?lens=cases` | Same page; lens ignored | Relocate N-0009 `LineupContainer` to `/lineup/cases` | **PARTIAL** — workspace preserved; lab “cases” are `commercial_lineup_case` on `/commercial-planner` |
| `/design-lab/planning?lens=readiness` | Same page; lens ignored | Gates on hub + planner defaults on `/commercial-planner` | **PARTIAL** |
| `/design-lab/planning?lens=economics` | Same page; lens ignored | `/commercial-planner` wrapped | **COVERED** |
| `/design-lab/planning?lens=po` | Same page; lens ignored | Production PO coverage is Supply `/admin/po-management` | **PARTIAL** — not stolen onto Planning rail |
| `/design-lab/planning?lens=rankings` | Same page; lens ignored | Product rankings live in commercial-planner Intelligent Add | **PARTIAL** — no standalone rankings leaf |
| `/design-lab/planning?lens=roadmap` | Same page; lens ignored | `/roadmap` wrapped; nav `substrate` kept | **PARTIAL** — Data only marker retained |

## Production routes (AS-IS → migrate)

| Route | AS-IS | After N-0020 | Coverage |
|---|---|---|---|
| `/lineup` | `LineupContainer` (N-0009) | Planning hub (`PlanningChrome` + `PlanningOverview`) | **COVERED** (hub) |
| `/lineup/cases` | (none) | Relocated `LineupContainer` | **COVERED** (relocate, not deleted) |
| `/commercial-planner` | PageHeader + plans/economics workspace | `PlanningChrome` wrap; workspace not deleted | **COVERED** |
| `/commercial-planner/cpor-cases*` | Promotions & Funding | **untouched** | out of Planning map |
| `/roadmap` | PageHeader + grid | `PlanningChrome` wrap; substrate honesty kept | **PARTIAL** |
| `/buy-plans` | middleware → `/lineup` | middleware → `/lineup/cases` | **COVERED** (legacy follows workspace) |
| Rail Planning hrefs/labels | `/lineup`, `/commercial-planner`, `/roadmap` | unchanged | **COVERED** (no rail IA change) |
| Promotion-plan template profile | — | out of scope | **out of map** |
| Budget ledger writer | — | not chartered | **out of map** |
| D-0002 mapping queue | `/admin/mappings` | untouched | **out of map** |

BACKLOG-181 lab rail is not the production bar.

---

## Browser 1280×800

Planning is **not** a named DIRECTION section 6 390px workflow — 1280 only.

Viewport via Playwright MCP `browser_resize` 1280×800 (not `browser_cdp`). Waits via Playwright `browser_wait_for`. 2026-09-13.

| Check | Result |
|---|---|
| `/lineup` hub vs `/design-lab/planning` two-column DomainOverview | **VERIFIED** — both DomainHeader + 5 headlines + PairedBars + readiness + attention + workflows. Lab fixtures (e.g. attention 18); production cip 29 / 273 982 / 20% / 2 703 / 0 |
| Workflows › Lineup cases real `<a href="/lineup/cases">` | **VERIFIED** — Playwright snapshot `/url: /lineup/cases`. In-page click stayed on `/lineup`; direct navigation used for the leaf |
| `/lineup/cases` still mounts `lineup-container` | **VERIFIED** — DomainHeader, LensTabs (Lineup cases selected), relocated workspace “Lineup / 26Q3 assortment” (testid `lineup-container` in `LineupContainer.tsx`) |
| `/commercial-planner` DomainHeader + workspace | **VERIFIED** — crumbs Planning / Plans & line economics; LensTabs selected; Intelligent add / Recalculate still present |
| `/roadmap` DomainHeader; Data only | **VERIFIED** — crumbs Product roadmap; hub substrate caption “Product roadmap (data only)”; leaf empty “No roadmap rows”. Empty-state Lineup cases href remapped to `/lineup/cases` |
| 390 named workflow | not required |

D-0002 mapping-queue disposition untouched. `navConfig.ts` Planning hrefs and labels unchanged. Rail Lineup cases remains `/lineup` (hub).
