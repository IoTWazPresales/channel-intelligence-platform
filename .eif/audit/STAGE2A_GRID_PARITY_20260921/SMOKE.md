# N-0031 smoke and verification record — Stage 2a

**Run:** `STAGE2A_GRID_PARITY_20260921` · **Actor:** `stage2a-001` · **Date:** 2026-09-21 · **Baseline:** `BLN-0002` @ `83ff3c5`
**Browser:** Chrome via `claude-in-chrome`, viewport 1488×812, `localhost:3000` (Next dev) → same-origin proxy → FastAPI `:8001` (stub auth, `admin@local`). All measurements are `getComputedStyle` / `getBoundingClientRect` readings from the live DOM, not screenshots.

## 1. Grid heights — one source (AC 1)

| Density | `--ag-row-height` (inline var) | `--ag-header-height` | rendered `.ag-row` | rendered `.ag-header` | Page / rows |
|---|---|---|---|---|---|
| comfortable | **42px** | **42px** | **42** | 43 (42 + 1px border) | `/admin/customers`, 22 rows |
| compact | **34px** | **36px** | **34** | 37 (36 + 1px border) | `/admin/customers`, 25 rows |

Both readings come from the same `gridDensityCssVars(theme.density)` + `gridRowMetrics(theme.density)` path in `EnterpriseDataGrid`; the CSS variables and the rendered pixels agree in both densities. **No visual change** from the pre-change values (42/42, 34/36). `tsc --noEmit` exit 0 (run without a pipe); focused vitest on `plan-vs-executed`, `shipping`, `EnterpriseDataGrid` green — those exercise `gridRowMetrics` / `paginatedGridHeight` through the re-exports.

Design-lab cross-check (`/design-lab/density`, API-independent): while the browser was on compact, both lab frames read `--ag-row-height: 34px` while rendering 42 and 36 — the lab passes explicit `rowHeight` props, and **props win over the variable**, exactly as the density proposal §3.1 states.

**Paginated shell** (`ExceptionCategoryGrid` / `PlanVsExecutedView` via `paginatedGridHeight`): `/stock?lens=execution` was still in its loading state at 9s and 20s on two attempts — the Execution-vs-plan query is slow on this machine. Covered by `ExceptionCategoryGrid.test.tsx` (3 tests, green) which sizes through the re-exported constants; **not** browser-proven this run. Recorded honestly as UNABLE_THIS_RUN, not as pass.

## 2. MarketSurface competitor-mappings grid (AC 2, BACKLOG-199)

`/competition` (lens `competition` by path; `?tab=` is only `prices` / `competitor-listings`):
`emptyState: true` ("No competitor mappings yet"), `importCta: true` (Import Center), `mappingsChip: "0 mappings"`, `errorAlert: false`, grid not mounted. Screenshot `ss_70652wb3t`. The `SubstrateOrPlanned` competitor-prices fallback is unchanged (not touched in the diff).

## 3. LineupScopeBar (AC 3, BACKLOG-156) — the defect was in dead code

`features/lineup/LineupScopeBar.tsx` had **zero importers**: `workbench-ui/controls.tsx:67` names it only in a comment ("Shared scope bar replacing LineupScopeBar / SettlementScopeBar / SettlementShapeBar"). Production `/lineup/cases` renders `LineupContainer.tsx:141` → shared `ScopeBar` (chips "All lines" / "Pending approval · N" + Clear) — **no inert Apply exists on the live surface**; DOM probe on `/lineup/cases` found `lineup-scope-bar` with none of the old component's children. The honest fix is deletion, not a restyle: `git rm` `LineupScopeBar.tsx`; `tsc` exit 0; lineup tests 7/7. `lineupViews.ts` exports stay in use by `LineupContainer` and `LineupTaskCrumb`. `SettlementScopeBar` is in the same replaced set but is reachable only via the unmounted `SettlementContainer` — noted for BACKLOG, not touched.

## 4. market.py readiness (AC 4, BACKLOG-160)

`competitor_price_import` → `status: "substrate"` with note. `pytest tests/test_market_placeholders.py tests/test_health.py` → 5 passed (`/api/v1/market/placeholders` via `TestClient`). `fact_competitor_price` = 0 rows on `cip` (read-only, measured in N-0030).

## 5. Incidents during verification (all resolved, none in product code)

- **API down.** Mid-smoke `:8001/health` returned `000`, the Next proxy `502`, and the API PID was gone; every surface showed loading/empty and the footer read "Signed out". Restarted with `CIP_SKIP_API_PORT_PREFLIGHT=1 pnpm dev:api`; healthy at `t=0.22s`. Not caused by this node's changes.
- **Hidden toggle.** `AppShell` renders the density toggle twice (desktop toolbar + mobile bar, `display:none` at md+); `querySelector` returned the hidden copy, so early probe clicks did nothing and one stray click left the persisted `cip-ui` density on **compact**. Located the visible toggle on `/settings` (`offsetParent` test), flipped back to **comfortable**, confirmed "Current: comfortable". Observation for CURRENT, not this node: at 1488px the desktop toolbar density icon is not rendered (only `/settings` exposes it).
- **Guard blocks.** `javascript_tool` reading `location.search` or `localStorage` is denied (`BLOCKED: Cookie/query string data`); probes rewritten to use `location.pathname` and DOM state only.
- **Batch ceiling.** A `browser_batch` with 34s of waits timed out; split into ≤20s batches.
- **tsc pipe.** My `492795c` "tsc clean" claim read `tail`'s exit code. Real run showed 8 narrowing errors in `SettlementDeskLive.tsx`; fixed in this node, and `tsc` now runs with its own exit code.

## 6. Independence

`verification.referent` on N-0031 requires an independent run (R2). This record is implementation-side evidence; it does not claim that gate.
