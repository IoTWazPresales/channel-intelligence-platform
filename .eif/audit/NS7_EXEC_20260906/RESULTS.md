# NS7_EXEC_20260906 — Execution lens

## Programme

- Node **N-0017** staged **implement** (run is the implementer). Lease `NS7_EXEC_20260906`. Not complete.

## NUMBER RULE (read-only, cip)

Command: `apps/api/.venv/Scripts/python.exe .eif/audit/NS7_EXEC_20260906/number_rule.py`

```
current_database()=cip
default_period=26Q3
drill_row_count=233
planned_units=32509.0
shipped_units_in_plan=6586.0
pct_of_plan=20
customers_under_70pct=10
lab_fixture_p09_used=false
```

Same path as the lab strip: `resolve_default_period` + `collect_execution_rows` + `compute_scorecard_from_execution_rows`.

## Browser

- `/stock?lens=execution`: Execution vs plan tab selected; lab empty-state copy; relocated workspace caption; PlanVsExecutedView chrome (filters) present.
- `/plan-vs-executed` redirects to `/stock?lens=execution`.
- Cover lens still mounts.
- `/api/v1/plan-vs-executed` returns 500 in the running API (pre-existing `/api/v1/*` 500). Figures not rendered.

## Tests

`pnpm --filter @cip/web test -- src/features/stock/executionRollup.test.ts src/features/stock/ExecutionLensView.test.tsx` — 3 passed.
