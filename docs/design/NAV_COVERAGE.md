# Navigation coverage — live routes vs CIP_NAV_MAP.md

Mechanical check against `apps/web/src/app/**/page.tsx` (Next.js App Router). Route
groups such as `(app)` do not appear in URLs. Dynamic segments use `[param]`
notation. Generated 2026-08-30 on branch `design-language-v1`.

**Convention evidence:** one `page.tsx` per URL segment under
`apps/web/src/app/`; 47 `page.tsx` files found (46 app surfaces + root redirect +
login). API proxy `apps/web/src/app/api/v1/[[...path]]/route.ts` is not a page.

**Map source:** `docs/design/CIP_NAV_MAP.md` v1 — each route must map to exactly
one disposition line (container / lens / record / context / retired / parked /
shell / utility). Container **labels** are provisional except LINEUP; numbers
below are structural (1–6 + utilities + shell).

---

## UNMAPPED — disposition gaps (do not implement without Warren)

*(empty — all seven previously unmapped routes resolved 2026-08-30)*

| Route | `page.tsx` evidence | Why unmapped |
|---|---|---|
| — | — | — |

---

## Mapped routes

| Route | CIP_NAV_MAP.md line |
|---|---|
| `/` | SHELL / UTILITY — redirect to landing blotter (container 1). Not a container. |
| `/login` | SHELL / UTILITY — auth shell. Not a container. |
| `/dashboard` | §1 landing — Absorbs: Dashboard/Control tower (retired as cards) |
| `/exceptions` | §1 landing — Absorbs: Exceptions inbox (retired as a place) |
| `/getting-started` | §1 landing — Absorbs: Getting-started coach (retired) |
| `/lineup` | §2 LINEUP — plan composition / items grid / net requirement / history |
| `/buy-plans` | §2 LINEUP — net-requirement (absorbs /buy-plans) |
| `/commercial-planner` | RETIRED as a single page, split: Lineup coverage → §2 LINEUP; Plans & lines → §5 commercial response; Planner defaults → UTILITIES ADMIN; Data map → §6 ingest & steward |
| `/sell-out` | §3 position — (lens) Movement — absorbs /sell-out and the Sell-Through duplicate |
| `/plan-vs-executed` | §3 position — (lens) Execution — Plan vs Executed (kept and improved) |
| `/shipping` | §3 position — (lens) Inbound — absorbs /shipping and PO Management out of Admin |
| `/admin/po-management` | §3 position — (lens) Inbound — absorbs /shipping and PO Management out of Admin |
| `/forecasts` | §3 position — (context) Forecast as demand input chip |
| `/channel-intelligence` | §3 position — (context) CST velocity at customer grain (absorbs /channel-intelligence) |
| `/inventory` | §3 position — (retired) /inventory paste as a second SOH |
| `/market` | PARKED — static placeholder stub (source: `market/page.tsx` “static JSON stub”) |
| `/commercial-planner/cpor-cases` | §4 funding & settlement — Queue + case split (grammar 1): the 310-case settlement book |
| `/commercial-planner/cpor-cases/[id]` | §4 funding & settlement — (record) Case: Lines / Evidence / Assumptions / Activity |
| `/commercial-planner/cpor-cases/historical-import` | §4 funding & settlement — Absorbs: … historical + payment-evidence import as evidence ingest on the case |
| `/commercial-planner/cpor-cases/payment-evidence-import` | §4 funding & settlement — Absorbs: … historical + payment-evidence import as evidence ingest on the case |
| `/budgets` | §4 funding & settlement — (context) Budgets as money ceiling (tick on book shape + regime figure) |
| `/budget-requests` | §4 funding & settlement — (context) ceiling/request workflow; budget administration remains ADMIN |
| `/promotions` | §5 commercial response — (retired) /promotions scaffold as a standalone module |
| `/pricing` | §5 commercial response — Calculators unparked … pricing recs |
| `/competition` | §5 commercial response — competition/listing intelligence as evidence on actions |
| `/roadmap` | §5 commercial response — (context) Roadmap parked as portfolio intent notes |
| `/admin/imports` | §6 ingest & steward — Import Center: jobs, failures, retry/archive (grammar 5 grid) |
| `/admin/shipment-evidence` | §6 ingest & steward — Steward engine … shipment evidence merged in |
| `/listing-capture` | §6 ingest & steward — listing capture as a data job |
| `/admin/products` | §6 ingest & steward — Identity masters as records: products, customers, distributors, channels/regions |
| `/admin/product-master-gaps` | §6 ingest & steward — … gaps and duplicates surface in (1), resolve here |
| `/admin/customers` | §6 ingest & steward — Identity masters as records: products, customers, distributors, channels/regions |
| `/admin/customers/duplicates` | §6 ingest & steward — … gaps and duplicates surface in (1), resolve here |
| `/admin/distributors` | §6 ingest & steward — Identity masters as records: products, customers, distributors, channels/regions |
| `/admin/distributors/duplicates` | §6 ingest & steward — Identity masters as records: products, customers, distributors, channels/regions |
| `/admin/cst-steward` | §6 ingest & steward — Steward engine: DSI / CST / shipment / lineup worklists |
| `/admin/channels-regions` | §6 ingest & steward — Identity masters … channels/regions |
| `/admin/mappings` | §6 ingest & steward — (retired, on trigger) /admin/mappings once steward is the only queue |
| `/admin/customer-commercial-terms` | §6 ingest & steward — customer record (dealer margin and rebate consumed by (4) and (5)); not a standalone admin page |
| `/reports` | UTILITIES REPORTS — report builder |
| `/dashboards` | UTILITIES REPORTS — saved views |
| `/inbox` | UTILITIES REPORTS — scheduled deliveries/inbox digest |
| `/admin/users` | UTILITIES ADMIN — users |
| `/settings` | UTILITIES ADMIN — settings |
| `/admin/sql-viewer` | UTILITIES ADMIN — SQL |
| `/admin/ops` | UTILITIES ADMIN — ops |
| `/admin/steward-audit` | UTILITIES ADMIN — audit |

---

## Summary

| | Count |
|---|---|
| `page.tsx` files (routable) | 47 |
| Mapped (unique routes) | 47 |
| UNMAPPED / ambiguous | 0 |
| API `route.ts` (excluded) | 1 |

Activity feed / running jobs (§1 landing) has no dedicated `page.tsx` — shell chrome only.
Planner defaults have no dedicated `page.tsx` — they live as a tab on the retired
`/commercial-planner` page and map to UTILITIES ADMIN.
