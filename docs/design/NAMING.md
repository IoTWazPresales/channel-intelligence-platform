# CIP navigation naming study

Status: recommendation. Labels for containers 1, 3, 4, 5, 6 and the two
utilities are **provisional** until Warren confirms. **Lineup** is settled and
is not re-opened here.

Specialist: UX-006 (ux-content-naming-specialist). Tests applied: a good label
tells the user what the thing is; uses the same term everywhere; avoids
internal jargon unless the audience expects it; distinguishes nearby concepts;
predicts consequences.

Hard rules (operator rejection, binding):

- Nouns the operator owns, never verbs.
- No implementation language (no “Data”).
- No AI-demo words (no “Decide”).
- No metaphor imports from other trades (no “Desk”, “Moves”, “Blotter” as
  labels).
- Labels must survive being said aloud in a business review.
- Do not re-propose unchanged: {Today, Channel, Funding, Actions, Imports}
  and {Desk, Position, Moves}. Individual words may reappear only with a
  stronger argument than “it was the default”.

---

## 1. Inputs (evidence quoted)

### 1.1 Containment map — what each container is

From `docs/design/CIP_NAV_MAP.md` (structure decided this session):

| # | Job | Grammar | Owns |
|---|---|---|---|
| 1 | Landing / attention blotter | 3 signal blotter | Failed imports, stale vintages, recon-not-run, cover breaches, funding blocks, missing assumptions, sell-out gaps |
| 2 | LINEUP (settled) | 2 instrument + grid | The plan: composition, items, net requirement (B2), half-year Q1+Q2, BU from `product_line`, approval and supersession history |
| 3 | Channel position & execution | 2 instrument + grid | Cover, movement, fill vs plan, inbound — **reads** the plan, does not edit it |
| 4 | Funding & settlement | 1 queue + case | The 310-case settlement book; budgets as ceiling only |
| 5 | Commercial response | 4 ranked actions + calculator | Ranked actions; do-nothing is first-class; calculators; **reads** the plan, does not edit it |
| 6 | Ingest & steward | 5 factory + 1 worklists | Jobs, steward queues, identity masters; lineup **file** ingest only |
| U | Reports | — | Builder, saved views, scheduled deliveries |
| U | Admin | — | Users, settings, SQL, ops, audit, planner defaults, budget administration |

Boundary quote (LINEUP): “the plan first exists as data here; position,
response and funding all derive from it, so it cannot be a lens on a surface
that measures execution against it.”

### 1.2 Live product vocabulary

Spine groups and leaves, `apps/web/src/features/shell/navConfig.ts`:

> Overview · Channel Intelligence · Commercial Planning · Master Data ·
> Data Imports · Admin

Leaves (quoted): Dashboard, Report builder, Dashboards, Report inbox,
Channel Operations, Sell-Through, CST channel intelligence, Listing Capture,
Inbound shipments, Forecasting, Commercial Planner, CPOR Cases, Line-up
Planning, Plan vs Executed, Products, Product catalogue gaps, Customers,
Distributors, Channels & Regions, CST steward, Import Center, Shipment
Evidence, PO Management, Customer Reports, Users, SQL viewer,
Ops / monitoring, Steward audit, Settings.

Page titles and chrome:

- Channel Operations tabs (`sell-out/page.tsx`): “Overview”, “Sell-out”,
  “Inventory”, “Movements”.
- KPI copy (`ChannelOpsKpiCards.tsx`): “Channel stock”, “weeks of cover”,
  “Replenish flag: {n} pairs below {t}w”, tooltip “Flag only — not a buy
  recommendation.”
- Inventory grid: “Reported SOH”, “Derived stock”, “Weeks of cover”,
  “Replenish”.
- Line-up page: “**Line-up** is customer / channel / period assortment
  planning”; “Net requirement (B2)”; “approval history”.
- Commercial Planner tabs (`commercial-planner/page.tsx`): “Plans & lines”,
  “Planner defaults”, “Data map”, “Lineup coverage”.
- Customer terms (`customer-commercial-terms/page.tsx`): title “Customer
  commercial terms”; columns “Dealer margin”, “Rebate / support”.
- Budget requests: title “Justification workflow”.
- Product name (`layout.tsx`): “Channel Intelligence”.

Implementation words already in the live nav, to be **avoided** as container
labels: “Data Imports”, “Master Data”, “Data map”.

### 1.3 Operator speech register

The operator is a key account manager talking to distributors, retailers, and
a country manager. Quoted product phrases that already live in that register
(not engineering):

- “weeks of cover” / “pairs below 4w”
- “Channel stock”
- “Replenish flag … not a buy recommendation”
- “Line-up” / “net requirement”
- “dealer margin” / “rebate / support”
- “CPOR Cases” / settlement of promotional support
- “steward” (the work of resolving unmapped entities)
- “fill vs plan” / “Plan vs Executed”
- “inbound not received”

A business-review sentence that must work: “Before we look at the lineup:
seven items need us. Stock is 119 pairs under four weeks against a 24.3-week
mean. Settlement still has R 19 million open. Response has six ranked items,
including do-nothing.”

### 1.4 SaaS category conventions (dated 2026-08-30)

Trade promotion / channel / revenue-growth products organise the same jobs
under nouns the operator already uses with finance and retail:

- SAP Trade Management: closed loop “from budget planning to **execution and
  settlement**”; “central **claims** repository”  
  (https://www.sap.com/products/crm/trade-management.html).
- Salesforce Consumer Goods TPM: “**Claims Management**”; “reconciliations
  while streamlining **settlements**”  
  (https://www.salesforce.com/consumer-goods/trade-promotion-management-software/).
- CPG TPM guides: account planning, **deductions reconciliation**, forecasts,
  assortment — not “Decide” or “Desk”  
  (https://www.cpgvision.com/the-ultimate-guide-to-trade-promotion-management-tpm).

S&OP / IBP peers (Anaplan, Kinaxis, o9) use **Demand / Supply / Inventory /
Response** as plan nouns. CIP already settled **Lineup** for origination, so
“Plan” and “Demand” are not free. “Response” in that family means the
commercial answer to a measured gap — the job of container 5.

---

## 2. Rejected sets (do not revive unchanged)

| Set | Why it failed (inferred from the hard rules + live vocab) |
|---|---|
| Today · Channel · Funding · Actions · Imports | Today is a time noun the operator does not own. Channel collides with the product name. Funding names the money supply, not the settlement job. Actions is a verb-adjacent pile. Imports is the mechanism. |
| Desk · Position · Moves | Trading-floor metaphor imports. |

Words from those sets appear below only where a **different job argument** is
made.

---

## 3. Candidates by container

Collision = an existing product term that already names something else.

### 3.1 Container 1 — landing / attention blotter

| Candidate | Rationale | Collision |
|---|---|---|
| **Brief** | Noun a KAM already uses with a country manager (“walk the brief”). Names the morning packet of what must be cleared before the book is trusted — not the time of day. Survives: “The Brief has seven items.” | None in product. Mild overlap with “briefing deck” as a document, not a screen. |
| Attention | Directly names the job. Weaker aloud: “open Attention” sounds like a cognitive act, not a place. | None. |
| Blockers | Precise to failed files, recon, funding blocks. Too narrow: cover breaches and missing assumptions are not all “blocks”; collides with settlement’s blocked-FX state. | Funding blocked cases; `chk.fail` “blocked”. |
| Exceptions | Live page title. Absorbed *as a place* by this container — reviving the word keeps the old IA. | `/exceptions`, nav-retired Exceptions inbox. |

**Recommendation: Brief.** Stronger than Today because it names the packet the
operator owns, not the clock. Not Blotter (trading floor).

### 3.2 Container 3 — channel position & execution

| Candidate | Rationale | Collision |
|---|---|---|
| **Stock** | Operator-owned noun in live copy (“Channel stock”, derived SOH). All four lenses are stock in the channel: cover (stock as weeks), movement (stock leaving), execution (stock vs plan), inbound (stock arriving). Survives: “Stock is 119 pairs under four weeks.” | Inventory tab; retired `/inventory` paste-as-SOH. “Stock” is the commercial word; “Inventory” was the file. Distinct. |
| Cover | Distinctive CIP metric; this mockup’s primary lens. Too narrow for Movement / Execution / Inbound. | Cover lens; “weeks of cover”; replenish-below-cover. Keep as **lens**, not container. |
| Position | Map job name “channel position”. KAM speech (“stock position”). Was rejected inside {Desk, Position, Moves} as a trading-floor trio. Reusing it *alone* is a stronger argument than default — still weaker than Stock, which was never rejected and is already on-screen. | None as a nav label. |
| Actuals | Finance noun for execution-vs-plan. Misses the cover-distribution decision (mean vs tail). | None. |

**Recommendation: Stock.** Do not revive Channel (product name). Do not lead
with Position; Stock carries the same job without the rejected-set baggage.

### 3.3 Container 4 — funding & settlement

| Candidate | Rationale | Collision |
|---|---|---|
| **Settlement** | The work the operator does on the 310-case book. Reference artifact is already titled “Settlement book”. TPM category (SAP/Salesforce: settlement / claims). Survives: “Settlement has R 19 million outstanding.” | None as a nav label. Aligned with “Record settlement”. |
| Claims | TPM standard; live case files say “claim rows”. Narrower than the book (FX, assumptions, evidence, budget ceiling). | Claim evidence vs CST; not fatal. |
| Support | Operator “promotional support” / “rebate / support”. Ambiguous in a review (helpdesk). | Rebate/support column on customer terms. |
| Funding | Previously marked settled on the map; then rejected in {Today, Channel, Funding, Actions, Imports}. Names the ceiling, not the job. Budget administration is Admin. | Live “CPOR funding cases” copy. |

**Recommendation: Settlement.** Funding is not reused: the operator owns
settling claims, not a funding round.

### 3.4 Container 5 — commercial response

| Candidate | Rationale | Collision |
|---|---|---|
| **Response** | Noun for the ranked commercial answer to Stock vs Lineup. S&OP/IBP family uses Response for this job. Do-nothing is a response, not an omission. Survives: “Response has six items, including do-nothing.” | None in operator register (HTTP “response” is not this audience). |
| Options | Fits do-nothing. Weaker: a catalogue, not a ranked action list. | None. |
| Calls | Sales “judgment calls”. Informal for a country-manager review. | None. |
| Actions / Decide / Moves / Planner | Rejected or AI-demo / verb / metaphor / implementation of the retired page. | Commercial Planner, Plans & lines. |

**Recommendation: Response.** Distinguishes from Lineup (the plan) and Stock
(the measurement). Both of those are read-only here.

### 3.5 Container 6 — ingest & steward

| Candidate | Rationale | Collision |
|---|---|---|
| **Steward** | Domain noun for the governance job (unmapped entities, identity, failed jobs). Live leaves: “CST steward”, “Steward audit”. Operators already say “send it to steward”. Covers ingest *and* masters; Intake does not. Survives: “Steward still has 23 failed jobs.” | **UserRole `steward`.** Same pattern as Admin (utility named for the role that lives there). Flag, not a veto. |
| Intake | Clean noun for file arrival (mailbox, Import Center). Misses identity masters and mapping. | None. |
| Files | Concrete. Too physical once mailbox + listing capture are in. | None. |
| Imports / Data | Rejected / implementation. | Data Imports, Data map, Master Data. |

**Recommendation: Steward.** Stronger than Imports because it names the
governance boundary the operator owns, not the file mechanism.

### 3.6 Utility — Reports

| Candidate | Rationale | Collision |
|---|---|---|
| **Reports** | Already the utility. Operator owns the pack sent to a country manager. Not in a rejected set. | Report builder, Dashboards, Report inbox — children, not rivals. |
| Analysis | Collides with the Read (intelligence signature), which is not a place. | None. |
| Insights | AI-demo adjacent. | None. |

**Recommendation: Reports.** Keep.

### 3.7 Utility — Admin

| Candidate | Rationale | Collision |
|---|---|---|
| **Admin** | Already the utility. Owns users, settings, SQL, ops, audit, planner defaults, budget administration. | UserRole `admin` — same accepted pattern as today. |
| Settings | Too narrow (SQL, ops, budget admin are not settings). | `/settings`. |
| Control | Vague; sounds like retired Control tower. | Control tower (retired). |

**Recommendation: Admin.** Keep.

---

## 4. Recommended full set

**Brief · Lineup · Stock · Settlement · Response · Steward · Reports · Admin**

Spine order: Brief (attention count) · Lineup · Stock (cover-tail count) ·
Settlement (open-book count) · Response (ranked-item count) · Steward
(failed-job count, red) · rule · Reports · Admin.

Lineup is settled. The other seven words are the naming-study recommendation,
still provisional until Warren confirms.
