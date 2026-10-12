# N-0079 close note — 2026-10-12

Warren said to continue closing the nodes.

## What was checked this close

- `apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_budget_ledger_balances.py apps/api/tests/test_lineup_budget_position_derived.py -q --tb=line` — 15 passed.
- ESLint on `apps/web/src/app/(app)/budgets/page.tsx` and `apps/web/src/app/(app)/promotions/PromoPlanBuilderPanel.tsx` exited 0 (`ESLINT_USE_FLAT_CONFIG=false`).
- `pnpm --filter @cip/web typecheck` exited 0.

## Already on the branch, not re-clicked in this close

- Budgets shows product line by quarter, a cap, a move, customer by quarter, a drill, and the payment-link coverage sentence.
- The promotion planner for 2026Q2 showed ledger drawn USD 103644.6669.
- Case C24A96486 showed ledger committed US$0, consumed US$574.5956, paid US$0. The case-currency Paid tile stays R0.
- Historical load on clone `cip_n0079` wrote 435, skipped 4, and a second load wrote 0, before the same load on cip. Alembic on cip is `20261012_0034`.

## Still true after close

- The non-campaign view stays empty until the next lineup approval. No lineup was approved to manufacture a row. Past approvals were not backfilled.
- Historical payments were not loaded. The Paid column stays a USD ledger sum.
- Caps flag and do not block. A cap is not money in the campaign draw.
- This verification is the same session as the build, a different programme run, and not a different model. VERIFIED_WITH_LIMITATIONS.
