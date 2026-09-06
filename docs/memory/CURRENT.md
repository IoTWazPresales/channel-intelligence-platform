# CURRENT state

**Last updated:** 2026-09-06 (Movement ISO-Monday week keys)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `0981197` (pre-Movement; this session’s product commit follows)

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **Product (Stock Movement):** Lab strip vs nested Channel Ops week totals was a **computation bug**. `date_trunc('week')` timestamptz Sunday 22:00 UTC missed Python Monday lookups (W24 0 / families 0 of 8). ISO-Monday grain: W24 **1119** vs W23 **2095** (−46.6%), families **1 of 8** (NR). Shipped W35 1477 / SOH 64121.2 unchanged. Browser: `/stock?lens=movement` shows 1 119 / 1 of 8; nested Sell-out by week still ~1119. Evidence `.eif/audit/NS7_MOVEMENT_20260906/`.
- **Product (Stock Execution):** Lab PairedBars chrome on `/stock?lens=execution`. Workspace relocated, not deleted. `/plan-vs-executed` redirects here. NUMBER RULE 26Q3 / 32509 / 6586 / under-70 10.
- **Product (Stock Cover):** Match vs cip SQL (64121 / 27.0w / 453 / 44 / 333).
- **API:** Listening on `:8001` after restart (stale uvicorn had served pre-fix 0s).
- **Programme:** PRG-20260831T145514. **N-0017 complete**. **N-0010 rejected** (D-0009). **N-0011 ready** — operator: patch contract against D-0008, then lease/baseline/implement. **Do not start N-0006. Do not reopen N-0013.**
- **D-0002** remains the open decision.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. Movement is not one of them (1280 only this session). Data & Stewardship carries import status → 390 when that node runs.

**Next:** N-0011 Data & Stewardship — patch ACs vs D-0008, then migrate. D-0002 untouched. EIF-R1–R4 parked BACKLOG-174–177.

**Design language:** FROZEN v1.1 is **demoted**. Production follows implemented design-lab React.

**Deferred:** BACKLOG-174–177. BACKLOG-173. Budget ledger writer not chartered. Floating FX re-rate after approval not implemented. Leftover `/market` stub. CDP viewport override denied (`BROWSER_UNSAFE`) — desktop layout verified without Emulation.setDeviceMetricsOverride.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).
