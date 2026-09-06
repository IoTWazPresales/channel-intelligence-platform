# CURRENT state

**Last updated:** 2026-09-06 (N-0011 Data & Stewardship chrome, not complete)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `edef697` (N-0011 Data & Stewardship chrome)

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **Product (Data & Stewardship, N-0011 implement):** Lab chrome on `/admin/imports|mappings|masters|steward-audit`. NUMBER RULE on `cip` (`current_database()=cip`): jobs last 7d **88** (ISO week-to-date 0), failed 7d **12** / all **38**, pending 7d **0** / all **64**, completed 7d **47**, templates **17**, legacy queue **0**, candidates needs_review **2797**, products **18177**, customers **5196** (unverified 56), distributors **101** (unverified 12), stores **0** UNCOVERED. Browser 1280×800 vs `DataSurface.tsx`; 390×844 import status (job cards, bottom nav 4+More). Idle wizard CSS-hidden at xs, relocated not deleted. D-0002 untouched. Independent GOV-008 not yet recorded.
- **Product (Stock Movement):** Lab strip vs nested Channel Ops week totals was a **computation bug**. ISO-Monday grain: W24 **1119** vs W23 **2095**, families **1 of 8**. Browser `/stock?lens=movement` 1280 only.
- **Product (Stock Execution):** Lab PairedBars chrome on `/stock?lens=execution`. Workspace relocated, not deleted.
- **Product (Stock Cover):** Match vs cip SQL (64121 / 27.0w / 453 / 44 / 333). Cover-breach lookup is a named 390 workflow verified 1280-only this wave.
- **API:** `:8001`. `GET /api/v1/imports/stewardship-summary` read-only.
- **Programme:** PRG-20260831T145514. **N-0017 complete**. **N-0010 rejected**. **N-0011 in_progress** implement (lease `NS8_DATA_20260906` / gov-001). **Do not start N-0006. Do not reopen N-0013.**
- **D-0002** remains the open decision.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. Data & Stewardship import status verified 390×844 this node. Do not retrofit 390 onto already-shipped surfaces.

**Next:** Independent GOV-008 on a run other than `NS8_DATA_20260906`, then Supply & Inbound container. D-0002 untouched. EIF-R1–R4 parked BACKLOG-174–177.

**Design language:** FROZEN v1.1 is **demoted**. Production follows implemented design-lab React.

**Deferred:** BACKLOG-174–177. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject (CONSULT vs DIRECTION) until Design Language v2. CDP `Emulation.setDeviceMetricsOverride` denied (`BROWSER_UNSAFE`).

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).
