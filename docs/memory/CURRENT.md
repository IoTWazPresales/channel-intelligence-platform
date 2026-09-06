# CURRENT state

**Last updated:** 2026-09-06 (API 500 + 1280×800 Cover/Movement/Execution browser)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `3008c83` (proxy 502 when FastAPI upstream is down; Execution chrome remains `6317040`)

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **Product (Stock Execution):** Lab PairedBars chrome on `/stock?lens=execution` (`ExecutionLensView`). `PlanVsExecutedView` relocated below, not deleted. `/plan-vs-executed` still redirects to this lens. Headlines use `scorecard.planned_units` / `shipped_units_in_plan` and customer rollup under 70% — not lab P09. Nav Partly built / Planned labels untouched.
- **Product (Stock Cover / Movement):** Unchanged this unit. Cover: `weeks_of_cover_observation` on cip. Movement: movement-lens + Channel Ops nested below.
- **Product (Stock chrome):** DomainHeader + lenses on `/stock`, `/channel-intelligence`, `/forecasts`. Default lens cover. `/stock?lens=inbound` stays Supply.
- **Product (Unit 5):** Seven fixture cases `intelligence_exclude`. Commercial-only lists. Do not ILIKE `%test%`.
- **Product (Units 0–4):** Funding dimensions, booked FX, evidence_basis, settlement Est. units.
- **I1–I5:** I1/I3/I4/I5 remain closed. **I2 closed** (BACKLOG-164).
- **Programme:** PRG-20260831T145514. UNIT 1 retroactive recording: N-0006 complete with no `implementation_run`. N-0014–16 complete. `verify` expected non-ok (independence/gates). **Do not start N-0006. Do not reopen N-0013 / D-0008 / D-0009.**
- **N-0017:** chartered then leased; stage **implement**; run `NS7_EXEC_20260906`; BLN-0001 attached. **Not complete** — GOV-008 still required. Lease expired 19:36:20Z; reclaim before mutating.
- **D-0002** remains the open decision.

**API 500 (Unit 1):** Predates this branch. Same-origin Next proxy (`0403713` / `af32bf7` on main) had no try/catch around `fetch`; FastAPI not listening on `:8001` became HTTP 500 with empty body, including `/auth/me`. This branch did not introduce it (no `route.ts` commits vs `origin/main` before the 502 catch). Fix: start local API + proxy catch → **502** `{detail: API upstream unreachable}`. With API up, `/auth/me` is 200 when sessioned (401 unauthenticated).

**Browser 1280×800 vs proven SQL (`current_database()=cip`):**
- **Cover — match:** Network SOH 64 121, 27.0w, under-2w 453, 2–4w 44, over-8w 333. Histogram 8w+ is drawn (SQL lab_buckets 335 `≥8` vs headline 333 `>8` — known bucket split, not a screen/SQL mismatch).
- **Execution — match:** Plan units 26Q3 32 509, shipped to date 6 586 (20%), customers under 70% 10. Relocated workspace present. `/plan-vs-executed` → `/stock?lens=execution`.
- **Movement — delta:** Lab strip Sell-out W24 **0** units, families growing **0 of 8**. Proven CONTEXT SQL was W24 **1119** vs W23 **2095**, families **1 of 8**. Same page nested Channel Ops “Sell-out by week” still shows ~2095 / ~1119. Shipped W35 **1 477** and Network SOH **64 121** match. Do not “fix” Movement in this unit.

**Next:** Independent GOV-008 on N-0017 through the engine (`NS7_GOV008_20260906` / `gov-008`), then N-0010 reject, N-0011 inspect, mobile evidence, BACKLOG EIF-R1–R4. Do not start Sell-through / Forecasts / Supply.

**Design language:** FROZEN v1.1 is **demoted**. Production follows implemented design-lab React.

**Deferred:** BACKLOG-173 (EIF NO_PROGRESS fingerprint). Budget ledger writer not chartered. Floating FX re-rate after approval not implemented. CIP cases absent from pending report (47) observed. C23C16234 not auto-flagged. Leftover `/market` stub (finding.defer on N-0015). Movement lab vs nested Channel Ops week totals.

**Env:** local Windows. Web `:3000` + API `:8001` (API was down; now listening). Sync/async engine on `cip` (`current_database()=cip`).
