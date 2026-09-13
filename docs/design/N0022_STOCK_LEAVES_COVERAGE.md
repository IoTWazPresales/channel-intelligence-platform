# N-0022 Stock leftover leaves coverage map

**Source (lab, primary):** `apps/web/src/design-lab/surfaces/StockSurface.tsx` ThinLens branches `sellthrough` and `forecast` + `apps/web/src/design-lab/shell/labNav.ts` stock leaves. Lab page `apps/web/src/app/(design-lab)/design-lab/stock/page.tsx` renders `StockSurface` (lens from `?lens=`).

Cover, Movement, and Execution vs plan are **N-0016 / N-0017 — out of this map**. Judge leftover leaves against ThinLens honesty, not LabShell rail (BACKLOG-181).

**NUMBER RULE** (`current_database()=cip`, measured 2026-09-13, tz Africa/Johannesburg). Lab figures are class **(i) fixture**. Production ThinLens copy is class **(iii)**. Never change a number to make two surfaces agree.

| Figure / gate | Lab fixture (i) | Production grain | cip (iii) | Class |
|---|---|---|---|---|
| Current ISO week | FY26 P09 · W36 | SAST today ISO week | **2026-W37** (today 2026-09-13) | (iii) |
| Sell-through current week | W36 not imported; TechMart W35 latest | `fact_customer_sellthrough.period_start_date` in current ISO Monday..+6d | **0** rows in W37 | (iii) |
| Latest CST period | TechMart W35 | max `period_start_date` | **2026-09-28 / W40**, 75 rows (Computer Mania 56 · Game 19) | (iii) — future-dated vs today; not TechMart |
| Forecast trailing 8 weeks | “need 8 weeks of applied sell-out” | distinct ISO Mondays of `fact_sales_sellout.transaction_date` in current Monday−49d .. current week | **0 of 8** | (iii) |
| Latest sell-out | (fixture) | max `transaction_date` | **2026-06-12 / W24** | (iii) |
| Forecast rows (workspace only) | not a working lens | `fact_demand_forecast` count | **38625** (velocity 26974 · analogue 11650 · manual 1) | (iii) — not a complete trailing window |

---

## Lab routes

| Route | Lab SOURCE | Production analog | Coverage |
|---|---|---|---|
| `/design-lab/stock?lens=sellthrough` | ThinLens empty: W36 not imported | `/channel-intelligence` ThinLens with cip W37 gate | **COVERED** (structure) / PARTIAL (copy is cip, not W36/TechMart) |
| `/design-lab/stock?lens=forecast` | ThinLens empty: 8-week sell-out gate | `/forecasts` ThinLens with cip trailing-week gate | **COVERED** |
| `/design-lab/stock?lens=cover` | Cover lens | N-0016 | **out of map** |
| `/design-lab/stock?lens=movement` | Movement lens | N-0016 | **out of map** |
| `/design-lab/stock?lens=execution` | Execution lens | N-0017 | **out of map** |

## Production routes (AS-IS → migrate)

| Route | AS-IS | After N-0022 | Coverage |
|---|---|---|---|
| `/channel-intelligence` | CST grid under StockChrome | ThinLens honesty (lab Sell-through) | **COVERED** |
| `/channel-intelligence/workspace` | (none) | Relocated CST grid | **COVERED** (relocate, not deleted) |
| `/forecasts` | Forecast grid + compute-from-history | ThinLens honesty (lab Forecasts) | **COVERED** |
| `/forecasts/workspace` | (none) | Relocated forecast workspace | **COVERED** (relocate, not deleted) |
| `/stock?lens=sellthrough` | redirect → `/channel-intelligence` | unchanged redirect (now honesty landing) | **COVERED** |
| `/stock?lens=forecast` | redirect → `/forecasts` | unchanged redirect (now honesty landing) | **COVERED** |
| `/stock?lens=cover\|movement\|execution` | N-0016/N-0017 | untouched | **out of map** |
| Rail Stock hrefs/labels | `/channel-intelligence`, `/forecasts` | unchanged | **COVERED** (no rail IA change) |
| D-0002 mapping queue | `/admin/mappings` | untouched | **out of map** |

BACKLOG-181 lab rail is not the production bar.

---

## Browser 1280×800

These leftover leaves are **not** named DIRECTION section 6 390px workflows — 1280 only.

Viewport via Playwright MCP `browser_resize` 1280×800 (not `browser_cdp`). Waits via Playwright `browser_wait_for`. 2026-09-13.

| Check | Result |
|---|---|
| `/design-lab/stock?lens=sellthrough` ThinLens vs `/channel-intelligence` | **VERIFIED** — both ModuleDataSection empty ThinLens. Lab fixture “W36 / TechMart”; production cip **W37 not yet imported**, latest applied **W40** 2026-09-28 (Computer Mania · Game). Playwright 1280 |
| `/channel-intelligence` Open workspace → `/channel-intelligence/workspace` | **VERIFIED** — `/url: /channel-intelligence/workspace`. Import Center `/admin/imports?template=customer_sell_through` |
| `/channel-intelligence/workspace` still mounts CST grid | **VERIFIED** — `data-testid="channel-intelligence-workspace"`; Customer id filters; Cover tab still 453 |
| `/design-lab/stock?lens=forecast` ThinLens vs `/forecasts` | **VERIFIED** — both “Forecasts need 8 weeks of applied sell-out”. Production body is cip **0 of 8** trailing weeks, latest sell-out **W24** |
| `/forecasts` does not mount compute-from-history CTA | **VERIFIED** — `forecast-honesty` present; `forecast-compute-from-history` absent; Open workspace `/forecasts/workspace` |
| `/forecasts/workspace` still mounts forecast workspace | **VERIFIED** — Compute from history CTA present under StockChrome |
| Cover / Movement / Execution unchanged | **VERIFIED** — `/stock?lens=cover` still Network cover headlines |
| 390 named workflow | not required |

D-0002 mapping-queue disposition untouched. `navConfig.ts` Stock hrefs and labels unchanged. Rail Sell-through remains `/channel-intelligence` (honesty landing).
