# N-0013 r3 — Converged product / IA / navigation direction

Run `NS_REDESIGN_R3_20260902` · Branch `feat/ns-2-brief-nav-collapse` · Author: Fable 5.1 (Cursor) ·
Status: **PROPOSED design package for operator review — not accepted, not implementation authority.**

Inputs: `PRODUCT_CAPABILITY_AUDIT.md`, `COMPONENT_ECOSYSTEM_AUDIT.md`, `CONCEPTS.md` (three divergent
concepts), `CONSULT_SEED.md` → `CONSULT_RESPONSE.md` (independent model), `FAULT_FINDINGS.md`.
Proof: interactive React prototype at `apps/web/src/design-lab/**` (route group `/design-lab`) and
rendered evidence in `renders/proto/` (see `rendered-verification.md`).

---

## 1. Direction in one paragraph

CIP's primary navigation axis is **what the business knows about — capability domains** — not process
stages and not entities. The rail reads: **Overview · Stock & Sell-through · Supply & Inbound · Planning ·
Funding & Settlement · Commercial inputs · Data & Stewardship · Administration** (Administration is
role-gated). The **first destination is a composed Overview** with two distinct zones: the configurable
**Business dashboard** (the operator's overall business view, seeded per role from ~30 governed metrics)
and **Needs attention** (the live Brief signals with counts and deep links), plus pinned governed reports.
Every domain has a **real overview page** (headline figures · that domain's attention items · analysis ·
workflow links), never a folder of routes. **Every number drills** into an entity/case context panel that
preserves the grid behind it. A **command palette** and a **capability directory** ("What CIP does") are
findability accelerators, not the primary structure. Leaves are **data-gated**: a route whose data layer
computes nothing is listed in the directory as "not yet populated" and hidden from the rail.

This is CONSULT's recommended hybrid **H** (Concept A domains + B's entity drill + C's composed home and
palette), adopted after comparing three materially different concepts (`CONCEPTS.md`).

## 2. Why this and not the rejected six containers

| Rejected axis (Brief · Plan · Position · Settlement · Actions · Imports) | Domain axis |
|---|---|
| Stage verbs/abstractions: "Position" cannot be predicted to hold *weeks of cover* | Nouns operators already use: *Stock & Sell-through*, *Funding & Settlement* |
| Linear pipeline reads as one flow; hides that CIP is a multi-domain analytical platform | The rail itself enumerates the product's breadth |
| Cross-cutting capabilities (dashboards, reports, search, masters) have no stage → arbitrary placement | Placement rule: *a workflow lives in the domain of its primary governed metric / entity*; Reports and Dashboards live in Overview as siblings |
| Business view and operational work collapsed into one sequence | Overview visibly separates *business view* (dashboard) from *operational attention* (signals) |
| Imports as a top-level destination made governance plumbing peer to the business | *Data & Stewardship* is a domain that also carries Master data and the Steward audit — the door every fact enters through |

Domain count (8, one role-gated) is an **output** of the capability audit: each domain owns a distinct set of
fact tables / governed metrics in `PRODUCT_CAPABILITY_AUDIT.md` §3 clusters. No target count was set.

## 3. Domains → capabilities (source-derived)

| Domain | Owns (capability audit) | Leaves in prototype | Data-gated / hidden |
|---|---|---|---|
| Overview | brief_signals (8 ids), dashboards (widgets over semantic metrics), report builder, saved reports | Business dashboard · Attention · Reports | — |
| Stock & Sell-through | fact_sales_sellout, derived SOH + weeks of cover, fact_customer_sales, plan-vs-executed, forecasts | Cover · Movement · Sell-through · Execution vs plan · Forecasts | Forecasts gated by method availability |
| Supply & Inbound | fact_inbound_shipment lifecycle, receipts/POD, PO coverage | Shipments · Receipts & POD · PO coverage | — |
| Planning | lineup cases, plan lines, readiness, line economics (calc_explanation/calc_flags), PO reconciliation, rankings | Lineup cases · Readiness · Line economics · PO reconciliation · Rankings | — |
| Funding & Settlement | CPOR cases, claim evidence, payments, pricing support | Case book · Claims evidence · Payments · Pricing support | — |
| Commercial inputs | promotion_plan lines, price_observations, pricing support terms | Promotion plans · Price observations | Competition · Roadmap · Budgets (routes exist, compute nothing) |
| Data & Stewardship | 19 import templates, per-job + cross-job steward queue, dim_product/customer/distributor masters, steward audit | Import Center · Steward queue · Products · Customers · Distributors · Steward audit | Steward queue/audit hidden for planner/viewer |
| Administration | users/roles, background operations, audited SQL viewer, audit log, settings | Users & roles · Operations · SQL viewer · Audit log · Settings | Whole domain admin-only |

**Mapping / resolution (D-0002, deferred):** kept reachable at two levels — per-job stewarding remains inside
each import job (unchanged governance boundary), and the **cross-job Steward queue** is a first-class leaf under
Data & Stewardship plus a Brief signal (`steward_queue`). The prototype's steward drawer mirrors the shipped
steward engine (ranked candidates with tier, master search, source rows, provisional-record path). Nothing here
retires or replaces the capability; that remains Warren's decision.

## 4. Dashboards — resolved model

- **Prominence:** prime real estate on the first destination (Overview, left/major column at 1280px; first
  zone at 390px unless deep-linked to attention).
- **Relationship to Reports:** siblings. Reports = *ask* (governed builder: metric · grain · dimensions; run,
  save, export, schedule). Dashboards = *keep showing me* (persistent widgets). A saved report can be pinned as
  a widget; Dashboards is not a saved-report destination.
- **Configuration model:** per-role seeded default (planner / steward / admin / viewer sets in
  `fixtures/dashboard.ts`), owner edits in place (Edit → remove / Add widget picker over governed metrics),
  publish to a role. Widgets are typed (kpi · line · bar · table) over `metricKey` + `grain` — the same
  vocabulary as the semantic layer, so nothing on a dashboard can be a number CIP cannot compute.
- **Relationship to attention:** side-by-side, never merged. Attention is push (what changed / what is
  blocked); the dashboard is state (how the business is doing).

## 5. Users and roles — what actually changes

Evidence: role model already gates admin/steward leaves in the shipped app; workflow audit shows stewards work
queues, planners work lineups and cover, managers read dashboards and approve funding.

Role changes **defaults, landing and leaf visibility — not the domain set** (CONSULT Q5; prototype role switch
`d-overview-role-viewer.png`). Planner default dashboard leads with stock/cover and plan-vs-shipped; steward
lands on Data & Stewardship with the queue counted; viewer sees the same seven business/data domains (Administration is
the only role-gated domain) with Import Center, Steward queue and Steward audit leaves removed. No persona modes
were invented.

## 6. Mobile — which workflows earned 390px

Away-from-desk workflows (CONSULT Q6, refined from the workflow audit):

| Workflow | Mobile treatment in prototype | Evidence |
|---|---|---|
| Attention triage | Attention zone first via `?zone=attention` (bell icon), single column | `m-attention.png` |
| Funding approval / return | Case book becomes **record cards**; case sheet is full-screen with sticky approve/return footer; approving updates counts + toast | `m-funding-cards.png`, `m-funding-case.png`, `m-funding-approved.png` |
| Stock cover lookup (breaches) | Headline figures 2-up, distribution chart stacked, breach rows as cards | `m-stock-breaches.png`, `-full.png` |
| Import status check | Job list as record cards with status chips | `m-data-imports.png` |
| Find anything | Command palette full-width | `m-command-palette.png` |
| Navigation | Bottom nav (4 domains + More) + full drawer with the complete tree | `m-overview.png`, `m-drawer.png` |

Desktop-first (intentionally not card-transformed): report builder, dashboard editor, lineup planning grid,
import column mapping. Rule adopted: **decision/lookup grids → record cards; comparison/ranking grids → keep
the grid with a frozen first column** (no generic "open on desktop" screen).

## 7. Component disposition (from `COMPONENT_ECOSYSTEM_AUDIT.md`, proven in the prototype)

| Existing asset | Disposition | Where shown |
|---|---|---|
| `EnterpriseDataGrid` (37 uses) | **Preserve**, restyle via theme only; used unchanged for cover, cases, jobs, queue | every grid render |
| `ModuleDataSection` (28 uses) | **Preserve** for loading/empty/error states | scope-empty states |
| `PageHeader` (45 uses) | **Evolve → `DomainHeader`** (adds what-this-does description + meta slot) | every surface |
| `KpiCard` | **Replace → `HeadlineFigure` / `HeadlineStrip`** (legible numerals 24–32px, delta, severity, caption, click-to-drill) | headline strips |
| Scope bars (4 duplicates) | **Consolidate → `ScopeBar`** (chips with counts, saved views, summary, clear) | stock, funding, data |
| Tab/lens switchers (duplicates) | **Consolidate → `LensTabs`** with counts | all lensed surfaces |
| Panels/cards (ad hoc) | **Promote → `Panel` / `PanelRow`** | everywhere |
| Charts (Recharts + ECharts ad hoc) | **Promote → `charts.tsx`** primitives (`TrendChart`, `CategoryBars`, `PairedBars`, `ProportionBar`) with one theme | overview, domains |
| Steward engine (`features/import-steward`, 33 files) | **Preserve as benchmark**; cross-job queue + drawer composed to its depth | `d-data-steward*.png` |
| Drill-down (absent) | **New → `EntityContextPanel`** (right drawer desktop / full-screen mobile, figures + related workflows) | stock, funding, steward |
| Global search (absent) | **New → `CommandPalette`** (⌘K) | `d-command-palette.png` |
| Shell (`AppShell`) | **Replace → `LabShell`** (domain rail with expandable leaves, top bar with scope stamp/search/attention/role, bottom nav + drawer on mobile) | all |

## 8. What this run does not claim

- No production route, business logic, schema or data was changed. The prototype lives only under
  `apps/web/src/design-lab` and `apps/web/src/app/(design-lab)`; it renders fixture data and calls no API.
- Fixture numbers are illustrative; every figure type shown maps to a metric the capability audit found the
  data layer can compute (no uplift, elasticity, confidence % or financial-impact estimates are shown).
- Rendered claims in `rendered-verification.md` were produced by the authoring run and are **UNVERIFIED for
  independence** until a separate GOV-008 session (other model where available) re-inspects them.

## 9. Open operator decisions (genuine)

1. **Accept this direction (H) as the N-0013 design package** so Phase A production implementation can be
   scoped — or reject with the specific surfaces that fail.
2. **D-0002 (mapping/resolution):** with the cross-job queue as a first-class leaf, does Warren want the
   per-job resolution workspace *and* the cross-job queue (proposed), or the cross-job queue to become the
   only entry point later? Deferred until this direction is judged.
3. **Design-language disposition** (FAULT_FINDINGS §1): demote `CIP_DESIGN_LANGUAGE.md v1.1` to reference and
   author a v2 from the prototype primitives — or keep v1.1 authoritative with amendments.
4. **Steward/admin leaf visibility for planners:** hidden (prototype default, CONSULT Q5) vs visible-disabled.
