# Surface Ownership

**Owner:** Warren · **Version:** 1.0 · 2026-08-01  
**Status:** authoritative — audited from `apps/web/src/app/(app)` + `navConfig.ts` on
2026-08-01; Warren confirmed. An agent may not add a metric, tile, filter or table to a
surface that does not own that concept.

**Why this exists.** ROADMAP v3 said POD completeness was "A1 core scope". A1 is the
Plan-vs-Executed screen, so POD tiles were built onto Plan-vs-Executed — duplicating
Shipping, which already owns shipped/pipeline/landed/POD. The roadmap named the
metric but never named the **owner**, so "matters to A1" collapsed into "put it on the
A1 page". A metric mattering to a phase does not make that phase's screen its home.

**Nav source of truth for labels/hrefs:** `apps/web/src/features/shell/navConfig.ts`.

---

## The rule

1. **One concept, one owning surface.** Every metric, filter and lifecycle state has
   exactly one screen that owns it. Other surfaces may *read* or *link*, never
   re-implement.
2. **Extend, never parallel-build.** If a surface already owns the concept, the work
   goes there. "Ours would look better on this screen" is a style opinion, not a
   category mismatch.
3. **Declare the owner before building.** Any new metric names its owning surface in
   the unit prompt. If no surface owns it, that is a design decision — halt and ask.
4. **Read across, don't rebuild across.** A surface needing another's number links or
   consumes the API; it does not recompute it locally.

---

## Ownership map

| Concept | Owning surface | Route |
|---|---|---|
| **Inbound lifecycle** — shipped / pipeline / **landed** buckets; smart cohorts (arriving / overdue / landed week) | Shipping (Inbound shipments) | `/shipping` |
| **POD** — `pod_date`, awaiting-POD ageing (`awaiting_pod_days`), landed-week presets | Shipping | `/shipping` |
| Inbound commercial KPIs — pipeline / arriving / landed / overdue value·qty·lines; ETA shifts; lineup-quarter strip | Shipping | `/shipping` |
| **Plan vs fill** — fill rate (shipped-basis), line-hit, planned vs in-plan shipped, total shipped in scope, pipeline (inbound), short exposure, **deal-stock overship** (Σ max(S−P,0) — *not* POD), unplanned intake, no-PO blind spot, exception lenses | Plan vs Executed | `/plan-vs-executed` |
| PO ↔ lineup linking, coverage meter, unlinked backlog, auto-link proposals | PO Management | `/admin/po-management` |
| **Support economics** — `ttl_support_*`, `support_unit`, settlement / workflow on cases | CPOR Cases (+ case detail) | `/commercial-planner/cpor-cases` · `/commercial-planner/cpor-cases/[id]` |
| CPOR historical import + steward | CPOR Historical Import | `/commercial-planner/cpor-cases/historical-import` |
| DSI sell-out / SOH **ingest** + steward | Import Center (template `distributor_inventory`) | `/admin/imports` (optional `?template=distributor_inventory`) |
| Shipment evidence **ingest** (upload → map → validate → apply) | Import Center (template `inbound_shipments`) | `/admin/imports?template=inbound_shipments` |
| Shipment evidence **browse / steward / apply** | Shipment Evidence | `/admin/shipment-evidence` |
| CST sell-through **ingest** + article-alias resolution on job | Import Center (template `customer_sell_through`) | `/admin/imports?template=customer_sell_through` (nav: Customer Reports) |
| CST **ops** — key accounts, report slots, alias confirm/reject | CST steward | `/admin/cst-steward` |
| **Channel Ops read model** — sell-out QoQ, derived channel stock, weeks of cover, distributors reporting; sell-out / inventory / movements tabs | Channel Operations | `/sell-out` |
| CST velocity / WoC / aged stock **read model** (customer×product×site) | CST channel intelligence | `/channel-intelligence` |
| Listing registry + proposals | Listing Capture | `/listing-capture` |
| Confirmed lineups on plans, plan lines, economics waterfall, planner defaults, data map | Commercial Planner | `/commercial-planner` |
| Line-up planning items CRUD / approval (separate API from confirmed plan lineups) | Line-up Planning | `/lineup` |
| Customer / product / distributor masters, merges, channels & regions, product-master gaps | Admin masters | `/admin/customers` · `/admin/products` · `/admin/distributors` · `/admin/channels-regions` · `/admin/product-master-gaps` · duplicates routes |
| Product Master / distributor / customer / historical_lineup **imports** | Import Center | `/admin/imports` (by template) |
| Control-tower summary tiles | Dashboard | `/dashboard` |
| App prefs / density / wipe | Settings | `/settings` |

**Split surfaces (same domain, different job — do not merge concepts):**

| Domain | Ingest / steward | Operational / analytics read |
|---|---|---|
| Inbound shipment | Import Center `inbound_shipments` + Shipment Evidence | **Shipping** owns lifecycle + POD + commercial KPIs |
| DSI | Import Center `distributor_inventory` | **Channel Operations** (`/sell-out`) owns sell-out/SOH read KPIs |
| CST | Import Center `customer_sell_through` | **CST steward** (ops) · **CST channel intelligence** (velocity read) |
| Lineups | Commercial Planner confirmed lineups · Line-up Planning items · PO Management links | **Plan vs Executed** reports outcomes only |

**Draft corrections (audit vs memory draft):**

| Draft claim | Tree reality |
|---|---|
| Channel Ops → `/channel-intelligence` | **Wrong.** Channel Ops = `/sell-out`. `/channel-intelligence` = CST velocity/WoC. |
| DSI → `/admin/imports/dsi/*` | **Wrong as a page route.** No `page.tsx` under that path; DSI is Import Center template mode. |
| Support bias → Plan vs Executed | **Wrong today.** No support/bias/CPOR fields on PvE. Support lives on CPOR Cases. ROADMAP A1 *may consume* support bias later — ownership stays CPOR until Warren reassigns. |
| PO Management route omitted | Actual route **`/admin/po-management`**. |
| Deal-stock “landing” on PvE | Means **overship vs plan**, not POD landed. Shipping owns POD/landed. |

**Not yet owned as product surfaces — halt and ask before building (or extend scaffolds deliberately):**
forecasting productization (B1; `/forecasts` exists as scaffold) · lineup + budget authoring (B2) ·
promotion plan builder (B4; `/promotions` Plans/Readiness parked) · report builder / semantic layer (P3) ·
app shell landing surface (P2-4) · scaffold modules not in ownership table (`/inventory`, `/pricing`,
`/competition`, `/roadmap`, `/market`, `/budgets`, `/budget-requests`, `/buy-plans`, `/exceptions`,
`/getting-started`, legacy `/admin/mappings`).

---

## Axis discipline (the specific trap that caused this)

`fact_inbound_shipment` / shipment evidence carries two independent time axes. They are
never conflated and they do not share an owner:

| Axis | Meaning | Used for | Owner |
|---|---|---|---|
| **Shipped** (`line_state='shipped'`) | left the factory | fill rate, plan execution | Plan vs Executed (consumes shipped facts) |
| **Landed** (`pod_date` present / quarter) | arrived in country | budget consumption, landing measurement | **Shipping** (measurement) · budget layer (consumption, later) |

A metric "mattering to A1" means A1 may **consume** it. It does not mean A1 **owns**
it or renders it.

---

## Pre-build existence audit — mandatory

Before writing any UI for a metric, tile, filter or lifecycle state:

```
grep -rn "<concept>" apps/web/src
grep -rn "<concept>" apps/api/app/services
```

- **Hit found** → STOP. Report where it lives. Extend that surface, or explain why a
  genuine category mismatch requires a new home and wait for Warren.
- **No hit** → check this map. Owner listed → build there. No owner → halt and ask.

Also open the **owning route** in the browser (and `navConfig.ts`) before claiming the
concept is unowned.

The audit result is printed in the unit report. A UI change claimed without it is
rejected.
