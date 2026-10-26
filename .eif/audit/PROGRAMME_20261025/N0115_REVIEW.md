# N-0115 original-scope review — 25 October 2026

Review of `d069f86c9232a735b87c64bb8f3fe3c7b5916b08` on `feat/ns-2-brief-nav-collapse`.
Read-only product analysis; this report is the only deliberate write by this specialist. No lease,
ledger mutation, database connection, service operation, migration, commit or deployment.
Applied architecture-specialist (module/solution), data-architect and verification-controller contracts.
Fresh-context review of earlier implementation, same model as this review's orchestrator; no attested
different-model verification. Verdict: **VERIFIED_WITH_LIMITATIONS for sampled implementation;
original N-0115 acceptance is incomplete. No R3 gate or operator acceptance.**

Original scope anchor is `.eif/audit/PROGRAMME_20261023/N0115_PANEL_BRIEF.md:25` (operator mandate).
`docs/DATA_MODEL_SPEC.md` section 10 and `N0115_CHALLENGE.md` contain temporary reductions, not approved
permanent exclusions. The current operator explicitly restores original scope. Parent reconciliation
reports D-0116–D-0130 remain proposed and D-0131 accepts the original scope, not the individual choices.

## New independently reproduced findings

### F1 — governed CPOR accepts filters it does not consistently apply

Pure, database-free probe on final source called `plan_request` and `a2_cpor.handle_a2` with a mocked
portfolio return (fictional total 100, customer 10 = 40, customer 20 = 60; NB = 40, NR = 60). The actual
planner and handler were used; only the session factory and portfolio I/O were mocked.

* `support_spend`, breakdown `customer`, filter `bu=NB`: planner accepts; handler returns both
  customers and total 100. Expected filter application or honest refusal; the current all-customer
  result is not filtered.
* Same metric and breakdown, filter `customer=999`: planner accepts; handler returns no rows but
  total 100. A nonexistent match retains the original all-customer headline.

Cause: `graph.py` advertises a handler-wide filter whitelist, but `a2_cpor.py` applies a filter only
when the relevant field is present in its already-aggregated rows. It updates the total only for
exactly one matching row. This is a real query-contract defect, not an unresolved commercial formula.
Correct the canonical governed handler (or refuse unsupported filter/grain combinations at planning),
retain its formulas, and add regressions through v1, v2, export and delivery. Do not replace support
spend with the differently dated `cpor.support_usd` measure merely to make results agree.

### F2 — v2 model measures bypass tenant semantic restrictions on their legacy equivalents

Pure final-source probe created an in-memory tenant catalog with `sellout_units` hidden, relabelled
and restricted to product grain, then called the real v1 validator, v2 planner and v2 catalog builder.
v1 refused the hidden metric; v2 accepted `dsi_sellout.units` by customer and exposed its default label
to a non-admin catalog caller. No database or tenant configuration was modified.

Cause: `default_model()` is tenant-independent; model measures are resolved before legacy catalog
validation and emitted before governed metric overlay filtering. Scope-aware query cache keys do
not supply the missing semantic policy. This proves a governance parity gap, not a demonstrated row
data leak. Define and implement the constrained model-overlay mapping with versioned cache invalidation.

### F3 — background governed queries need tenant and recipient-scope proof

`a2_cpor.handle_a2` ignores its `QueryRequest.tenant_id`, opening a sync `SessionLocal()` and calling
the portfolio service without a tenant argument. Authenticated calls **do** inherit ORM tenant
criteria from `core/tenant_scope.py`; absence of an explicit handler parameter is therefore not
proof of an authenticated tenant leak. Background scheduled delivery passes `user=None`; default
tenant/product scope ContextVars are unset, and the runner does not bind recipient identity.
The portfolio query then has no explicit tenant predicate. This is a source-supported background
isolation risk needing a rollback-only two-tenant schedule reproduction before claiming exploitation.
Recipient visibility is an explicit policy decision; preserving isolation to the report's tenant is
an engineering invariant and must not wait on that decision.

## Evidence work log

Read required handoffs/context, original panel brief/challenge/spec, implementation and historical
verification reports, final Unit C execution evidence, model YAML, loader/graph/compiler/calc/catalog/
execute/cache, v1 registry/handlers/engine, tenant/product scope, portfolio, delivery/schedule and caller
sources/tests. No broad test suite was rerun. The new probes above were chosen because historical
passing tests do not cover those input combinations. Command: PowerShell here-string piped to
`apps/api/.venv/Scripts/python.exe -`, importing final-source modules with `sys.path` set to `apps/api`;
`unittest.mock.patch` replaced CPOR I/O. Exit 0; exact observed values are recorded above. Aggregate
and calculation enumerations in the same probe: `count,count_distinct,latest_sum,sum`; `difference,
pct_change,per_week_rate,prior_period,ratio`; models `dsi_sellout,cst_sellthrough,cpor`.

The remaining acceptance matrix and bounded execution units follow in the final version of this report.
