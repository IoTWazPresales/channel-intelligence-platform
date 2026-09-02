# CONSULT seed — N-0013 r3 information architecture (neutral)

You are an independent consultant (different model and session from the author). Do not edit files.
Challenge each alternative from the evidence below; do not adopt any alternative because it is listed
first. Where evidence is insufficient say UNVERIFIED. Output: for each open question give a
recommendation with reasoning, the strongest counter-argument, and what rendered evidence would settle
it. Finish with a ranked list of the alternatives (or a hybrid you define) and the risks of each.

## Product facts (from source, 2026-09-02)

- CIP (Channel Intelligence Platform) tracks OEM → distributor → retailer → consumer stock and money.
  Data layer: product/customer/distributor masters (steward-gated), inbound shipments, distributor
  sell-out + derived SOH, retailer sell-through, lineup plan cases/lines, funding (CPOR) cases with claim
  and payment evidence, promotion/pricing plan inputs, price observations, ~30 governed metrics.
- 47 web routes; 19 import templates on one pipeline (upload→parse→map→validate→steward→apply→derive).
- Capability groups and what they compute today:
  Brief (8 live attention signals with counts + deep links); Dashboards (configurable 12-col widget
  canvas, one governed metric per widget, kpi/table/bar/line/area, publish) — shipped as an empty state;
  Reports (governed builder: metric, grain, dimensions, run/save/export/schedule); Stock (derived SOH,
  weeks-of-cover, velocity, plan-vs-executed, vintage staleness, SOH reconciliation); Shipping
  (lifecycle, ageing, receipt/POD, PO coverage); Lineup (cases, plan lines, readiness, line economics
  with explanation flags, PO reconciliation, rankings); Settlement/CPOR (book/settled/outstanding,
  blocked, delivery rate, comparables, support per unit, cost per incremental unit with weak-baseline
  flag); Forecasts (velocity/analogue, method-labelled); Import Center (guided wizard, async
  validate/apply with progress, per-job resolution workspace); Stewarding/mapping (token→dimension
  mapping queue, corroboration, provisional records, duplicates, steward audit); Masters (grids with
  column picker, drawers, terms); Ops/Audit/SQL (job control, activity feed, audited read-only SQL);
  Users/roles (admin/steward/planner/viewer); Settings. Scaffolds with thin behaviour: pricing,
  promotions, competition, roadmap, budgets, market.
- Users: commercial/channel operators — country/brand managers, buyers/planners, channel/account
  managers, data stewards. Role model exists in code and controls visibility of admin/steward leaves.
- Component assets: shared `PageHeader` (45 importing files), `EnterpriseDataGrid` (37),
  `ModuleDataSection` states (28), `ModuleGridToolbar` (23), `BulkSelectionToolbar` (12), a 44-file
  generic steward engine, a 9-file dashboard editor (metric palette, drop canvas, widget chart/editor),
  `KpiCard` (exists, barely used). Duplicated: three ScopeBar/RegimeStrip/TaskCrumb twins. Absent:
  shared charts (Recharts in 4 files; bars hand-built elsewhere), entity context panel, global search.
- Rendered today (1280px): Brief shows four text rows and ~55% empty viewport; headline figures appear as
  9.5px strips; Stock grid shows raw IDs; Dashboards shows an empty state; Import Center, steward
  workspace, report builder and lineup workspace are rich.

## Constraints (operator, 2026-09-02)

- Previous IA rejected: Brief · Plan · Position · Settlement · Actions · Imports (and before it
  Brief · Lineup · Stock · Settlement · Response · Steward). Reason: insufficient information scent for
  an unfamiliar operator to understand breadth or predict where capabilities live. Not a rename problem.
- No target/min/max number of top-level destinations. Architecture must fall out of the product.
- Do not assume process stages are the primary axis.
- Dashboards are a strategically important configurable view of the business; "saved-report
  destination under Reports" framing is rejected. Prominence, location, relationship to reporting and
  to landing/attention, and configuration model are open.
- Mapping/resolution must remain reachable (decision on retire/replace deferred).
- No fabricated intelligence (no confidence %, impact estimates, causal claims, recommendations beyond
  what the data layer computes).
- Mobile must be genuinely useful for away-from-desk workflows; no generic "open on desktop".
- Existing strong surfaces (steward, Import Center, report builder) are benchmark evidence; may be
  improved, must not be degraded.
- Test: can an unfamiliar user understand what CIP does, recognise major areas, find a named capability,
  see where related workflows live, and distinguish overall business view from operational work —
  without training?

## Alternatives (described, not ranked)

A. **Capability domains.** Top-level = business domains (e.g. Overview; Stock & Sell-through; Supply &
Inbound; Planning; Funding & Settlement; Commercial inputs; Data & Stewardship; Administration). Each
domain has an overview page (headline figures, its attention items, workflow links); lenses/workflows
are secondary navigation; rail shows domain + leaves. Entity context as a slide-in panel.

B. **Entity workbench.** Top-level = business objects (Home; Products; Customers; Distributors;
Shipments; Funding cases; Plans; Data). Capabilities are tabs on entity pages; cross-entity workflows are
saved filtered views of an entity set; every number drills to the object.

C. **Home + Work + Explore.** Top-level = operating cadence (Home = configurable dashboard + attention
inbox + my queues; Work = role queues; Explore = analytics/reports/dashboard library; Data; Admin).
Findability via a capability directory page and command palette rather than rail labels.

Hybrids are permitted (e.g. domains primary with entity context panel; domains primary with a
dashboard+attention home; entities primary with a domain directory).

## Open questions

1. Which primary axis (or hybrid) best passes the unfamiliar-user test for THIS capability set, given
   that import/steward/ops/SQL/users have no natural entity and that lineup and cover are cross-entity?
2. Should the first destination be the configurable Dashboard, the attention Brief, or one page
   composed of both? What is the relationship of Dashboards to Reports in navigation?
3. Should the thin scaffolds (pricing/promotions/competition/roadmap/budgets/market) be a visible area
   now (as "plan inputs & evidence"), or hidden until they compute something?
4. Where should the cross-job mapping/resolution queue live so it remains reachable and discoverable?
5. Should role change the rail's contents, or only defaults and landing?
6. Which workflows genuinely need 390px use, and what should dense grids do at 390px?
7. What in the three prior rejected IAs was structurally wrong (beyond labels), and does any alternative
   above repeat it?
