# Navigation coverage — live routes vs CIP_NAV_MAP.md

Mechanical check against `apps/web/src/app/**/page.tsx` (Next.js App Router). Route
groups such as `(app)` do not appear in URLs. Dynamic segments use `[param]`
notation. Generated 2026-08-30 on branch `design-language-v1`.

**Convention evidence:** one `page.tsx` per URL segment under
`apps/web/src/app/`; 47 `page.tsx` files found (46 app surfaces + root redirect +
login). API proxy `apps/web/src/app/api/v1/[[...path]]/route.ts` is not a page.

**Map source:** `docs/design/CIP_NAV_MAP.md` v1 — each route must map to exactly
one disposition line (container / lens / record / context / retired / utility).

---

## UNMAPPED — disposition gaps (do not implement without Warren)

| Route | `page.tsx` evidence | Why unmapped |
|---|---|---|
| `/` | `apps/web/src/app/page.tsx` | Redirect-only (`redirect('/dashboard')`); not a disposed surface. Target landing is §1 TODAY but this route is not the Today blotter. |
| `/login` | `apps/web/src/app/login/page.tsx` | Auth shell; no line in CIP_NAV_MAP.md. |
| `/commercial-planner` | `apps/web/src/app/(app)/commercial-planner/page.tsx` | Ambiguous: §2 CHANNEL `(context)` lineup net-requirement **and** §4 PLANNER promo/support composition (B4) both claim planner surfaces. |
| `/lineup` | `apps/web/src/app/(app)/lineup/page.tsx` | Ambiguous: §5 IMPORTS unified lineup ingest **and** §2 CHANNEL `(context)` lineup net-requirement. |
| `/market` | `apps/web/src/app/(app)/market/page.tsx` | No line in CIP_NAV_MAP.md. |
| `/budget-requests` | `apps/web/src/app/(app)/budget-requests/page.tsx` | No explicit line (nearest: §3 FUNDING `(context)` budgets **or** UTILITIES ADMIN budget administration — not named). |
| `/admin/customer-commercial-terms` | `apps/web/src/app/(app)/admin/customer-commercial-terms/page.tsx` | No explicit line (ADMIN “semantic overlay” is not specific enough for this route). |

---

## Mapped routes

| Route | CIP_NAV_MAP.md line |
|---|---|
| `/dashboard` | §1 TODAY — Absorbs: Dashboard/Control tower (retired as cards) |
| `/exceptions` | §1 TODAY — Absorbs: Exceptions inbox (retired as a place) |
| `/getting-started` | §1 TODAY — Absorbs: Getting-started coach (retired) |
| `/sell-out` | §2 CHANNEL — (lens) Movement — absorbs /sell-out and the Sell-Through duplicate |
| `/plan-vs-executed` | §2 CHANNEL — (lens) Execution — Plan vs Executed (kept and improved) |
| `/shipping` | §2 CHANNEL — (lens) Inbound — absorbs /shipping and PO Management out of Admin |
| `/admin/po-management` | §2 CHANNEL — (lens) Inbound — absorbs /shipping and PO Management out of Admin |
| `/forecasts` | §2 CHANNEL — (context) Forecast as demand input chip |
| `/channel-intelligence` | §2 CHANNEL — (context) CST velocity at customer grain (absorbs /channel-intelligence) |
| `/inventory` | §2 CHANNEL — (retired) /inventory paste as a second SOH |
| `/buy-plans` | §2 CHANNEL — (context) lineup net-requirement (absorbs planner Lineup-coverage tab and /buy-plans) |
| `/commercial-planner/cpor-cases` | §3 FUNDING — Queue + case split (grammar 1): the 310-case settlement book |
| `/commercial-planner/cpor-cases/[id]` | §3 FUNDING — (record) Case: Lines / Evidence / Assumptions / Activity |
| `/commercial-planner/cpor-cases/historical-import` | §3 FUNDING — Absorbs: … historical + payment-evidence import as evidence ingest on the case |
| `/commercial-planner/cpor-cases/payment-evidence-import` | §3 FUNDING — Absorbs: … historical + payment-evidence import as evidence ingest on the case |
| `/budgets` | §3 FUNDING — (context) Budgets as money ceiling (tick on book shape + regime figure) |
| `/promotions` | §4 PLANNER — (retired) /promotions scaffold as a standalone module |
| `/pricing` | §4 PLANNER — Calculators unparked … pricing recs |
| `/competition` | §4 PLANNER — competition/listing intelligence as evidence on actions |
| `/roadmap` | §4 PLANNER — (context) Roadmap parked as portfolio intent notes |
| `/admin/imports` | §5 IMPORTS — Import Center: jobs, failures, retry/archive (grammar 5 grid) |
| `/admin/shipment-evidence` | §5 IMPORTS — Steward engine … shipment evidence merged in |
| `/listing-capture` | §5 IMPORTS — listing capture as a data job |
| `/admin/products` | §5 IMPORTS — Identity masters as records: products, customers, distributors, channels/regions |
| `/admin/product-master-gaps` | §5 IMPORTS — … gaps and duplicates surface in TODAY, resolve here |
| `/admin/customers` | §5 IMPORTS — Identity masters as records: products, customers, distributors, channels/regions |
| `/admin/customers/duplicates` | §5 IMPORTS — Identity masters … gaps and duplicates surface in TODAY, resolve here |
| `/admin/distributors` | §5 IMPORTS — Identity masters as records: products, customers, distributors, channels/regions |
| `/admin/distributors/duplicates` | §5 IMPORTS — Identity masters … gaps and duplicates surface in TODAY, resolve here |
| `/admin/cst-steward` | §5 IMPORTS — Steward engine: DSI / CST / shipment / lineup worklists |
| `/admin/channels-regions` | §5 IMPORTS — Identity masters … channels/regions |
| `/admin/mappings` | §5 IMPORTS — (retired, on trigger) /admin/mappings once steward is the only queue |
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
| Mapped (unique routes) | 40 |
| UNMAPPED / ambiguous | 7 |
| API `route.ts` (excluded) | 1 |

Activity feed / running jobs (§1 TODAY) has no dedicated `page.tsx` — shell chrome only.
