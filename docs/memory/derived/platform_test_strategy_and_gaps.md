# Platform Test Strategy And Gaps

## Current test landscape by layer
- **API/backend pytest** (`apps/api/tests`): health, openapi, imports/product master mapping+workflow, async dispatch regression, dev wipe, product delete semantics, lineup behaviors, buy/wos units.
- **Web Vitest** (`apps/web/src/**/*.test.ts*`): API helper parsing/base URL, PM mapping helper logic, UI component behavior (grid/toolbars/cards/dialogs), provider integration.
- **E2E**: Playwright wiring exists (`apps/web`), with root scripts for execution.

## Strongest protected areas
- Product Master mapper/validation utility behavior and commercial regressions.
- Product Master dev-dispatch + shared task helper behavior (`run_product_master_commit_job`).
- Core low-level utility correctness (`json_safe`, schema inference, query error handling).
- Several module-level API mutation semantics (lineup approvals, product delete guard behavior).

## Weak/fragile coverage areas
- End-to-end user journeys across multiple pages/modules are lightly evidenced.
- Many page components are not directly tested as integrated workflows (especially for stateful multi-step pages).
- Async failure-path resilience beyond unit-level assertions (broker outages, worker restarts, retry semantics) is only partially covered.
- Cross-module data lineage expectations (import -> downstream planning pages) are mostly untested as an integrated contract.

## Page-level protection posture
- **Better covered**: admin imports helper logic, shared UI primitives, certain API domain units.
- **Thin coverage**: dashboard, market, roadmap, budget requests, broad multi-tab promotion interactions, complex admin page end-to-end states.

## Tooling/safety checks
- Backend: pytest configured in `apps/api/pytest.ini`.
- Frontend: vitest + testing-library.
- Repo-level scripts support API/web tests and combined verification commands.

## Future test priorities (for page-by-page pass)
1. High-value end-to-end happy/failed paths for Product Master and key planning modules.
2. Integration tests for critical page state transitions and API error states.
3. Async operational tests around dispatch/broker/worker edge scenarios.
4. Contract tests validating import-output effects consumed by downstream pages.
