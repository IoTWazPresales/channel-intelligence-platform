# Commercial Planner Program

Living program doc for the Commercial Planner evolution (imports, steward UX, intelligence).

## Feature flag

- API: `CIP_COMMERCIAL_PLANNER_ENABLED` (default `true`). When `false`, `/api/v1/commercial-planner/*` returns 404.
- Web: `NEXT_PUBLIC_CIP_COMMERCIAL_PLANNER_ENABLED` (default on). Hides nav link when off.

## Current lineup import

| Step | Endpoint | Behaviour |
|------|----------|-----------|
| Preview | `POST /lineup-cases/{id}/parse-preview` | Parse file in memory; no `CommercialLineupLine` writes |
| Apply | `POST /lineup-cases/{id}/parse-apply` | Requires `confirm=true`; writes lines + ImportJob audit |
| Legacy | `POST /lineup-cases/{id}/parse-upload` | Same as apply (backward compatible) |

## Intelligence (v1)

Deterministic product rankings per customer for a plan.

- `GET /commercial-planner/plans/{plan_id}/intelligence/customer/{customer_id}/product-rankings?limit=50`
- Signals: sell-out history, forecast, historical lineup, current lineup case lines, hypothetical GP from defaults
- Every row includes `opportunity_score`, `confidence`, `trust_tier`, `explanation_factors`

Suggestions (`GET /plans/{id}/suggestions`) also use **current lineup case** lines when the plan has linked accepted cases.

## Principles

- No auto-create of master dimensions from uploads
- DAP is evidence only — never `controlled_cost_amount`
- Human applies suggestions; no silent bulk plan writes from scores

## Phases (delivery)

1. **Phase 1:** flag, preview/apply (retry + create-case), intelligence rankings, suggestion precedence, intelligent add UI
2. **Phase 2 (complete on branch):**
   - Celery `commercial_planner.parse_lineup_case` + HTTP 202 for large files; activity feed `lineup_parse_task`
   - Rankings: candidate product union (sellout, lineup, forecast, pricing, promo, budget, buy plan); customer-scoped forecast
   - Steward export: `GET …/lineup-cases/{id}/steward-export` + web download
   - Dashboard KPI: `kpis.commercial_planner` on `/dashboard/summary`
   - Intelligence snapshots: POST/GET ranking snapshot (in-process audit)
   - Router modules: `commercial_planner_lineup_routes.py`, `commercial_planner_intelligence_routes.py`, `commercial_planner_auth.py`
   - Shared readiness: `plan_readiness.py`

See **`docs/COMMERCIAL_PLANNER_GAP_ANALYSIS.md`** for residual risks (RBAC, full router monolith split, durable snapshot store).
