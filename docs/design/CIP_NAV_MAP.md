# CIP Navigation Containment Map v1

Companion to CIP_DESIGN_LANGUAGE.md. This restates the completed disposition
work (route audit + fresh SHOULD-BE) as navigation: **six job containers** plus
Reports and Admin utilities, with every disposed surface assigned.

**Container labels are confirmed** (Warren, 2026-08-30; see
`docs/design/NAMING.md`). **LINEUP** was settled earlier. The **STRUCTURE**
below is decided — rename containment only through an explicit disposition,
not ad hoc.

Confirmed spine labels: Brief · Lineup · Stock · Settlement · Response ·
Steward · Reports · Admin.

Legend: (lens) = tab within the surface · (record) = opens in place, context
preserved · (context) = appears as evidence/strip on a parent, not a page ·
(retired) = capability absorbed or removed per disposition · (parked) = route
exists as a stub; not a job container.

---

## 1. Landing / attention blotter  [Brief — grammar 3]

Roles: landing / attention blotter. Signal blotter grammar.

- Landing signal queue: failed imports, stale vintages, recon-not-run, cover
  breaches, funding blocks, missing assumptions, sell-out gaps
- Absorbs: Dashboard/Control tower (retired as cards), Exceptions inbox
  (retired as a place), Getting-started coach (retired), activity feed /
  running jobs
- Identity exceptions arrive here as work items (gaps, duplicates, alias
  queues, CST slots due) and open the relevant record

## 2. LINEUP  [label settled — operator vocabulary — grammar 2]

Plan origination. Instrument + grid.

**Rationale:** Lineup is an origination surface — the plan first exists as data
here; position, response and funding all derive from it, so it cannot be a
lens on a surface that measures execution against it.

Contents:

- Plan composition
- Lineup items grid
- Net requirement (B2) calc / export / apply
- Half-year periods always split Q1+Q2
- BU derivation product-first from `dim_product.product_line`
- Approval history
- Supersession / revision history

Lineup **file ingest** remains a data job under container (6); the resulting
plan surfaces here.

**Boundary:** LINEUP owns the plan; (3) measures execution against it; (5)
ranks commercial responses — both read, neither edits.

Absorbs: `/lineup`; commercial-planner **Lineup coverage** tab; `/buy-plans`
(net-requirement).

## 3. Channel position & execution  [Stock — grammar 2]

One surface, sticky From/To/BU filter bar. Measures execution against LINEUP;
does not edit the plan. Lenses:

- (lens) Cover — derived SOH, WOC distribution instrument, replenish flags
- (lens) Movement — sell-out, DSI movements (absorbs /sell-out and the
  Sell-Through duplicate)
- (lens) Execution — Plan vs Executed (kept and improved), fill vs plan,
  over-ship annotations
- (lens) Inbound — shipments, PO recon bands (short/over/unshipped), inbound
  not received; absorbs /shipping and PO Management out of Admin
- (context) Forecast as demand input chip; CST velocity at customer grain
  (absorbs /channel-intelligence)
- (retired) /inventory paste as a second SOH — reported SOH remains a recon
  check only

## 4. Funding & settlement  [Settlement — grammar 1]

- Queue + case split: the 310-case settlement book
- (record) Case: Lines / Evidence / Assumptions / Activity; settle flow with
  preview-confirm; FX declaration; readiness checks
- Absorbs: CPOR list redesign, historical + payment-evidence import as
  evidence ingest on the case (not orphan routes), promo export
- (context) Budgets as money ceiling (tick on book shape + regime figure);
  `/budget-requests` as ceiling/request workflow context on this book
- Administration of budgets lives in ADMIN — not this container

## 5. Commercial response  [Response — grammar 4]

- Ranked commercial actions; do-nothing is a first-class recorded action
- Calculators unparked as evidence-backed tools: buy/cover math, promo
  support composition (B4 compose → creates a Funding/Settlement case),
  pricing recs, competition/listing intelligence as evidence on actions
- Absorbs: commercial-planner **Plans & lines** (retired as a standalone
  planner page; the action list + calculators live here)
- (context) Roadmap parked as portfolio intent notes
- (retired) /promotions scaffold as a standalone module
- Reads LINEUP; does not edit the plan

## 6. Ingest & steward  [Steward — grammar 5 + grammar 1 worklists]

- Import Center: jobs, failures, retry/archive (grammar 5 grid)
- Steward engine: DSI / CST / shipment / lineup worklists (grammar 1
  queue+case per worklist); shipment evidence merged in; unified lineup +
  bulk backfill as contextual ingest (file ingest only — the resulting plan
  is LINEUP); Customer Reports as a wizard template; listing capture as a
  data job
- Absorbs: commercial-planner **Data map** (field map is an ingest/steward
  concern, not a planner page)
- Identity masters as records: products, customers, distributors,
  channels/regions — gaps and duplicates surface in (1), resolve here
- Customer commercial terms (dealer margin and rebate) are a **customer
  record**, not a standalone admin page; consumed by containers (4) and (5)
- (retired, on trigger) /admin/mappings once steward is the only queue

## UTILITIES

- REPORTS: report builder, saved views, scheduled deliveries/inbox digest
- ADMIN: users, settings, SQL, ops, audit, **planner defaults**, budget
  administration, semantic overlay

## SHELL / UTILITY  [not containers]

Redirect and auth. These are not job containers and do not appear on the
spine.

- `/` — redirect to the landing blotter (container 1)
- `/login` — auth shell

## PARKED

- `/market` — static placeholder stub (source confirms: API returns static
  JSON; “syndicated panel, share, and macro feeds are not connected yet”).
  Not a job container. Do not build a seventh job around it.

---

## Completeness rule

This map is complete only if every live route in apps/web maps to exactly one
line above (container / lens / record / context / retired / parked / shell).
That is verified mechanically against the repo route inventory — not asserted
from this document. The UNMAPPED section of `NAV_COVERAGE.md` must be empty.
Any new unmapped route is a disposition gap to resolve before charter, not a
nav-naming problem.

## Naming (settled)

Container labels confirmed 2026-08-30 (`docs/design/NAMING.md`). Stock lens
switcher (instrument control): Sell-out · Fill vs plan · Cover · Inbound
(spec §5). Map lens names (Cover · Movement · Execution · Inbound) are
internal job names; operator-facing switcher uses the spec labels above.
