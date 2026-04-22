# Platform Page Inventory

Status key used here: `working`, `partial`, `scaffold-only`.

## Core shell/start pages
- `/dashboard` (Control tower): KPI cards + stock snapshot + recommended actions from `/api/v1/dashboard/summary`; **partial** (functional but lightweight presentation, JSON-heavy snapshot).
- `/getting-started`: onboarding/instructions with links and workflow guidance; **working** (documentation-oriented page).
- `/settings`: API base/runtime hints, density status, guarded DB wipe UX; depends on `/api/v1/dev/database-wipe*`; **working** for dev ops.

## Planning/commercial pages
- `/inventory`: customer inventory CRUD/bulk paste against `/api/v1/inventory/customer`; **working**.
- `/forecasts`: forecast CRUD/bulk paste against `/api/v1/forecasts`; **working**.
- `/buy-plans`: buy recommendation grid and delete/clear operations on `/api/v1/buy-plans`; **partial** (consumer UI for recommendations, limited scenario tooling).
- `/pricing`: pricing facts + recommendation grids and bulk paste; `/api/v1/pricing/*`; **working**.
- `/promotions`: plan/readiness grids plus promo export + export events; `/api/v1/promotions/*`; **working**.
- `/lineup`: lineup items, bulk import, event audit stream; `/api/v1/lineup/*`; **working**.
- `/budgets`: allocation and health grids with clear/delete; `/api/v1/budgets/*`; **working**.
- `/budget-requests`: request queue view and clear/delete on `/api/v1/budgets/requests`; **partial** (workflow basics present, deeper approval UX still thin).
- `/roadmap`: roadmap rows CRUD-style grid `/api/v1/roadmap`; **partial**.
- `/exceptions`: exception inbox with explanation drawer and clear/delete; `/api/v1/exceptions`; **working**.

## Market/competition pages
- `/competition`: mapping approvals and competitor prices management (`/api/v1/competition/*`); **working**.
- `/market`: renders static placeholder contract from `/api/v1/market/placeholders`; explicitly marked stub in UI; **scaffold-only**.

## Admin pages
- `/admin/imports`: highest-complexity page; generic imports + full Product Master flow (upload/mapping/validate/background commit/progress polling); **working** with advanced controls.
- `/admin/mappings`: mapping queue review/approve/delete/clear; **working**.
- `/admin/products`: product grid + channel placement support + delete semantics; **working**.
- `/admin/customers`: customer/channel/region admin grid + import helper; **working**.
- `/admin/distributors`: distributors, sellout, inbound shipments operational admin grids; **working**.

## Cross-page dependency truth
- Almost all pages depend on module-scoped FastAPI endpoints and `ModuleDataSection` + `EnterpriseDataGrid`.
- State freshness is query-cache driven (invalidations after mutations), no centralized domain event bus.
- Strongest cross-cutting integration currently sits in Admin Imports -> downstream module data surfaces.
