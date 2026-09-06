# CURRENT state

**Last updated:** 2026-09-06 (N-0017 complete + ledger housekeeping)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `3008c83` (proxy 502; Execution chrome remains `6317040`)

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **Product (Stock Execution):** Lab PairedBars chrome on `/stock?lens=execution`. Workspace relocated, not deleted. `/plan-vs-executed` redirects here. NUMBER RULE 26Q3 / 32509 / 6586 / under-70 10. Browser-verified 1280×800.
- **Product (Stock Cover):** Match vs cip SQL (64121 / 27.0w / 453 / 44 / 333) at 1280×800.
- **Product (Stock Movement):** Lab W24 sell-out **0** vs proven SQL **1119**; nested Channel Ops chart still ~1119. Shipped W35 1477 and SOH 64121 match. Not fixed this session.
- **API 500:** Predates this branch (Next proxy uncaught fetch + FastAPI down). Proxy now 502 when upstream refused. API listening on `:8001`.
- **Programme:** PRG-20260831T145514. **N-0017 complete** — independent GOV-008 `NS7_GOV008_20260906` / `gov-008` vs `implementation_run` `NS7_EXEC_20260906`. **N-0010 rejected** (D-0009). **N-0011 ready** (BL-0002 closed; contract stale; do not start / patch / reject / recharter until classified). **Do not start N-0006. Do not reopen N-0013.**
- **D-0002** remains the open decision.

**N-0011 classification (inspect only):** intent survives (patch the contract). Original charter was import factory + resolution worklists; D-0008 still has Data & Stewardship. ACs still cite FROZEN Steward. Not N-0010-class abolish.

**Mobile contract (not decided):** DIRECTION §6 = desktop-primary with named 390px workflows (attention, funding approve/return, cover lookup, import status, palette, bottom nav). Full parity does not fit. Evidence: `.eif/audit/MOBILE_CONTRACT_EVIDENCE_20260906/NOTES.md`. Reconcile before Design Language v2.

**Next:** Do not start N-0011. Do not start Sell-through / Forecasts / Supply until Warren picks. Movement lab-vs-SQL delta is open. EIF-R1–R4 parked as BACKLOG-174–177. D-0002 untouched.

**Design language:** FROZEN v1.1 is **demoted**. Production follows implemented design-lab React.

**Deferred:** BACKLOG-174–177 (EIF-R1–R4). BACKLOG-173 (NO_PROGRESS fingerprint). Budget ledger writer not chartered. Floating FX re-rate after approval not implemented. Leftover `/market` stub (finding.defer on N-0015). Movement lab vs nested Channel Ops week totals.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).
