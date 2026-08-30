# CIP Navigation Containment Map v1

Companion to CIP_DESIGN_LANGUAGE.md. This restates the completed disposition
work (route audit + fresh SHOULD-BE) as navigation: five job containers + two
utilities, with every disposed surface assigned. The five nav words label these
containers — they do not need to "describe" their contents, because the
contents are enumerated here. Rename any container at will; the containment
does not change.

Legend: (lens) = tab within the surface · (record) = opens in place, context
preserved · (context) = appears as evidence/strip on a parent, not a page ·
(retired) = capability absorbed or removed per disposition.

---

## 1. TODAY  [placeholder name — signal blotter, grammar 3]
- Landing signal queue: failed imports, stale vintages, recon-not-run, cover
  breaches, funding blocks, missing assumptions, sell-out gaps
- Absorbs: Dashboard/Control tower (retired as cards), Exceptions inbox
  (retired as a place), Getting-started coach (retired), activity feed /
  running jobs
- Identity exceptions arrive here as work items (gaps, duplicates, alias
  queues, CST slots due) and open the relevant record

## 2. CHANNEL  [placeholder name — instrument + grid, grammar 2]
One surface, sticky From/To/BU filter bar, lenses:
- (lens) Cover — derived SOH, WOC distribution instrument, replenish flags
- (lens) Movement — sell-out, DSI movements (absorbs /sell-out and the
  Sell-Through duplicate)
- (lens) Execution — Plan vs Executed (kept and improved), fill vs plan,
  over-ship annotations
- (lens) Inbound — shipments, PO recon bands (short/over/unshipped), inbound
  not received; absorbs /shipping and PO Management out of Admin
- (context) Forecast as demand input chip; CST velocity at customer grain
  (absorbs /channel-intelligence); lineup net-requirement (absorbs planner
  Lineup-coverage tab and /buy-plans)
- (retired) /inventory paste as a second SOH — reported SOH remains a recon
  check only

## 3. FUNDING  [name settled]
- Queue + case split (grammar 1): the 310-case settlement book
- (record) Case: Lines / Evidence / Assumptions / Activity; settle flow with
  preview-confirm; FX declaration; readiness checks
- Absorbs: CPOR list redesign, historical + payment-evidence import as
  evidence ingest on the case (not orphan routes), promo export
- (context) Budgets as money ceiling (tick on book shape + regime figure);
  administration of budgets lives in ADMIN

## 4. PLANNER  [placeholder name — ranked actions + calculator, grammar 4]
- Ranked commercial actions; do-nothing is a first-class recorded action
- Calculators unparked as evidence-backed tools: buy/cover math, promo
  support composition (B4 compose → creates a Funding case), pricing recs,
  competition/listing intelligence as evidence on actions
- (context) Roadmap parked as portfolio intent notes
- (retired) /promotions scaffold as a standalone module

## 5. IMPORTS  [placeholder name — factory, grammar 5]
- Import Center: jobs, failures, retry/archive (grammar 5 grid)
- Steward engine: DSI / CST / shipment / lineup worklists (grammar 1
  queue+case per worklist); shipment evidence merged in; unified lineup +
  bulk backfill as contextual ingest; Customer Reports as a wizard template;
  listing capture as a data job
- Identity masters as records: products, customers, distributors,
  channels/regions — gaps and duplicates surface in TODAY, resolve here
- (retired, on trigger) /admin/mappings once steward is the only queue

## UTILITIES
- REPORTS: report builder, saved views, scheduled deliveries/inbox digest
- ADMIN: users, settings, SQL, ops, audit, planner defaults, budget
  administration, semantic overlay

---

## Completeness rule

This map is complete only if every live route in apps/web maps to exactly one
line above (container / lens / record / context / retired). That is verified
mechanically against the repo route inventory — not asserted from this
document. Any unmapped route is a disposition gap to resolve before charter,
not a nav-naming problem.

## Open naming decisions (Warren)
Container labels for 1, 2, 4, 5 (Funding is settled; utilities are settled).
Defaults in use: Today · Channel · Funding · Planner · Imports. Lens and tab
names above are proposals and equally renameable.
