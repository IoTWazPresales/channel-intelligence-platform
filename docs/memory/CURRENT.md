# CURRENT state

**Last updated:** 2026-09-06 (Stock Execution vs plan lab chrome)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `6317040` (Execution vs plan lab chrome)

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
- **N-0017:** chartered then leased; stage **implement**; run `NS7_EXEC_20260906`; BLN-0001 attached. **Not complete** — no GOV-008 this session.
- **D-0002** remains the open decision.

**Next:** Do not complete N-0017 without GOV-008. Local API `/api/v1/*` 500s so Execution figures are not rendered in the browser (Python NUMBER RULE on `cip` did run). Then sell-through/forecast polish, then Unit D Supply. Do not start those until Execution product is committed.

**Design language:** FROZEN v1.1 is **demoted**. Production follows implemented design-lab React.

**Deferred:** BACKLOG-173 (EIF NO_PROGRESS fingerprint). Budget ledger writer not chartered. Floating FX re-rate after approval not implemented. CIP cases absent from pending report (47) observed. C23C16234 not auto-flagged. Leftover `/market` stub (finding.defer on N-0015).

**Env:** local Windows. Web `:3000` + API `:8001`. API currently 500s on `/api/v1/*` including `/auth/me` and `/plan-vs-executed`. Sync/async engine on `cip` still works (`current_database()=cip`).
