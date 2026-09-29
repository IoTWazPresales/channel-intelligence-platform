# N-0041 — shared grid search matches a8755854

Code check 2026-09-29. No product edit. Ledger close only.

## What the node asks

One shared toolbar search in `features/workbench-ui`, used by the Tier A fact grids. No migration. No write to `cip`.

## What the tree has

`useFactGridChrome` / `GridFindField` in `apps/web/src/features/workbench-ui/gridFind.tsx`. The field is labelled Find, updates immediately, and the query follows 300ms later. Hosts put `filters` on the Scope bar and apply `query` as `quickFilterText` or as the existing server search (`product_search` on commercial sell-out, `q` on customer terms).

Wired: forecasts, pricing facts, pricing recommendations, roadmap, buy-plans, inventory, cover, sell-out commercial lines, channel-ops sell-out / inventory / movements, plan-vs-executed drill, channel intelligence, customer terms, listings.

Left as they are, on purpose:

- Inbound shipments keep `shipping-search`. That field is the shipment query (distributor, product, SKU, order, partner) sitting with partner, date, and line filters. It is not a second Find component for the fact grids.
- Exceptions stay unwired. That route redirects to the brief.

Unit tests: `gridFind.test.ts` covers saved-find parsing. The search debounce is the `useGridFind` effect in the same module.

Shipped in `a8755854`. This pass did not rebuild the column picker and did not open the design lab.
