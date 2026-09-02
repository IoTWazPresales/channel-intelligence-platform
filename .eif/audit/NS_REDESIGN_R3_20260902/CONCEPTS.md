# Divergent product concepts — N-0013 r3

Three concepts that differ in **primary navigation axis and product behaviour**, not in theme. Each is
tested against the capability clusters in `PRODUCT_CAPABILITY_AUDIT.md` §5 and the component assets in
`COMPONENT_ECOSYSTEM_AUDIT.md`. Evaluation is pre-CONSULT; `CONSULT_RESPONSE.md` records the
independent challenge; `DIRECTION.md` records convergence.

## Concept A — Capability domains ("what the business does")

Primary axis: commercial capability domains an operator already names. Derived from §5 clusters:
Overview · Stock & Sell-through · Supply & Inbound · Planning · Funding & Settlement · Commercial
inputs · Data & Stewardship · Administration. Each domain opens on a **domain overview** (headline
figures, the domain's attention items, links to its workflows), with workflows/lenses as secondary
navigation inside the domain. The rail shows domain + its leaves (expandable, not always-expanded), so
the breadth of CIP is visible without training. Dashboards live in Overview as the default home;
Brief signals become the attention pane of that home; Reports sit beside them. Entity context
(product/customer/distributor) is a slide-in panel available from any grid.

## Concept B — Entity workbench ("the business objects")

Primary axis: entities. Home · Products · Customers · Distributors · Shipments · Funding cases ·
Plans · Data. Every analytical capability is a tab on an entity set: a product page has Stock,
Sell-through, Inbound, Plan, Funding, Pricing tabs; a customer page has Lineup, Sell-through,
Settlement, Terms. Cross-entity workflows (lineup = customer×product×period; cover =
distributor×product) become saved filtered views of an entity set. Drill-down is the product: every
number leads to the object. Dashboards and Reports live in Home.

## Concept C — Home + Work + Explore ("my operating cadence")

Primary axis: how a person works. Home (configurable dashboard + attention inbox + my queues) ·
Work (role queues: steward queue, planner cycle, settlement approvals, receipts) · Explore (stock,
sell-through, forecasts, reports, dashboards library) · Data (imports, masters, mappings) · Admin.
Capability findability is delivered by a **capability directory page** and a command palette
(⌘K) rather than by rail labels. Role determines which queues appear.

## Comparison

| Criterion | A domains | B entities | C cadence |
|---|---|---|---|
| Capability coverage (47 routes, 19 imports, 14 capability groups) | All map; latent scaffolds sit under Commercial inputs with honest "inputs & evidence" framing | Import/steward/ops/SQL/users have no entity → forced into "Data/Admin"; promotions/roadmap/budgets awkward | All map, but 20+ leaves sit under Explore/Work, so the rail carries little scent |
| Findability of a named capability without training ("where is Lineup?", "where are claims?") | High — domain names are the operator's own words | Medium — must know lineup is a customer×product view | Low–medium — depends on directory/palette |
| Commercial mental model | Matches org structure (planning, supply, funding, stock) | Matches CRM/ERP object model; strong for account managers | Matches task inboxes; strong for stewards |
| Workflow efficiency | Good: domain overview → lens → grid → context panel | Excellent for entity drill; poor for cross-entity cycles (lineup planning, settlement book) | Excellent for queue work; analytics two clicks deeper |
| Component fit | Direct: PageHeader + HeadlineStrip + LensTabs + EnterpriseDataGrid + ModuleDataSection; steward engine re-hosted unchanged | Needs new entity-360 page type; grids re-shaped as tabs; steward engine unchanged | Needs queue primitives (partly exist: steward-worklist), directory, palette |
| Existing strengths preserved | Yes — Import Center, steward, report builder, lineup workspace re-host as-is | Lineup workspace and settlement book must be re-cut into entity tabs (regression risk) | Yes |
| Density & analytical quality | Domain overviews give room for real charts; grids keep density | Entity pages become long tabbed records; cross-cuts weaker | Home dense; Explore pages as today |
| Scalability (new capabilities) | Add a leaf to a domain, or a domain | Add a tab to entities (grows every entity page) | Add to Explore/Work (rail unchanged, scent unchanged) |
| Responsive | Domain overview = card stack at 390; grids → summary+list | Entity page = natural mobile record | Home/queues excellent on mobile |
| Identity | "Commercial intelligence platform" — breadth visible | "Channel CRM" — feels like records | "Work inbox" — feels like tooling |
| Implementation plausibility | High: route prefixes map 1:1 to existing `(app)` folders | Medium–low: new page type, re-cut of workspaces | High |
| Failure mode it repeats | Could regress to six process stages if domains are collapsed | Hides analytics behind objects | Abstract labels (Work/Explore) = the rejected problem |

## Hybrids worth carrying into CONSULT

- A + B: domains as primary; **entity context panel** (B's 360 view) as a universal secondary surface.
- A + C: domains as primary; **Home = configurable dashboard + attention inbox** (C's home) as the first
  destination; command palette as accelerator, not primary findability.
- B is not eliminated: its entity page is the strongest answer to "drill-down / context preservation".

## Contested decisions (to CONSULT)

1. Primary axis: domains vs entities vs cadence — or which hybrid.
2. Home: Dashboard-first (configurable business view) vs Brief-first (attention) vs merged.
3. Whether Dashboards and Reports are one area ("Overview/Insight") or Dashboards is the landing and
   Reports a utility.
4. Where mapping/resolution (D-0002) belongs: inside Data & Stewardship as a cross-job queue, or only as
   per-job resolution inside Import Center.
5. Whether latent scaffolds (promotions/pricing/competition/roadmap/budgets/market) get a visible
   "Commercial inputs" domain now, or stay hidden until derived metrics exist.
6. Whether role should change the rail (hide domains) or only defaults/landing.
