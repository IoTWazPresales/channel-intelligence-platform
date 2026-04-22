# Platform Feature Status Matrix

Legend: `working`, `partial`, `scaffold-only`, `risky`, `unclear`.

| Feature/workflow | Current status | Notes |
|---|---|---|
| Product Master upload/map/validate | working | Dedicated constrained workflow and mapper logic with explicit row results. |
| Product Master background commit | working | Async queued/running/fail semantics with DB-backed progress and idempotency guards. |
| Generic import templates/sources/jobs listing | working | Templates/sources/jobs APIs and UI flow are present. |
| Generic import processing (`/imports/jobs/{id}/process`) | working | Sync path in API process; Celery variant registered but not default. |
| Mapping queue (admin) | working | Queue list, approve, clear/delete flows present. |
| Inventory module | working | CRUD + bulk ingestion UX and API. |
| Forecast module | working | CRUD + bulk ingestion UX and API. |
| Pricing module | working | Facts + recommendations shown with maintenance actions. |
| Promotions + CPOR export events | working | Multi-tab page with export history/events path. |
| Line-up planning + audit events | working | Bulk endpoints and event trail integration present. |
| Budgets (allocations/health/requests) | partial | Functional data surfaces; deeper approval/finance workflow maturity appears limited. |
| Roadmap planning | partial | Grid workflow exists, limited strategic planning affordances. |
| Exceptions control tower | working | Explainable exception list and management controls. |
| Dashboard control tower | partial | KPI/summary present but still relatively lightweight/presentation-first. |
| Market intelligence page | scaffold-only | Explicit static stub contract, not real feed integration. |
| Settings dev ops (wipe/API hints) | working | Useful operational controls and diagnostics for local dev. |
| Auth/RBAC | partial | Stub-header approach; production auth integration not implemented. |
| E2E journey coverage | risky | Playwright available, but no broad page-by-page confidence evidence in current suite. |
