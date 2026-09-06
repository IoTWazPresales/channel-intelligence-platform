# CURRENT state

**Last updated:** 2026-09-07 (N-0011 complete)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `edef697` (N-0011 Data & Stewardship chrome)

**Last ledger pin:** `37c6286` (N-0011 independent GOV-008)

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514. **N-0011 complete**. **N-0018 in_progress** implement (lease `NS9_SUPPLY_20260907` / gov-001, charter `331cd76`). **N-0017 complete**. **N-0010 rejected**. **Do not start N-0006. Do not reopen N-0013.**
- **Product (Data & Stewardship):** Lab chrome on `/admin/imports|mappings|masters|steward-audit`. NUMBER RULE on `cip`: jobs last 7d **88**, failed 7d **12** / all **38**, pending 7d **0** / all **64**, completed 7d **47**, templates **17**, tab **102**, products **18177**, customers **5196**, distributors **101**, stores **0** UNCOVERED. 1280×800 + 390×844 import status. Idle wizard CSS-hidden at xs. 390 bottom-nav third item is **Promotions** (funding domain `short`), not the word Funding.
- **Product (Stock Movement / Execution / Cover):** as previously pinned. Cover-breach lookup is a named 390 workflow verified 1280-only this wave.
- **API:** `:8001`. `GET /api/v1/imports/stewardship-summary` read-only.
- **D-0002** remains the open decision.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. Data import status verified 390×844. Do not retrofit 390 onto already-shipped surfaces.

**Next:** N-0018 Supply & Inbound — lab `SupplySurface` in `DomainOverviewSurface.tsx` + `/design-lab/supply`. Production `/stock?lens=inbound`, `/admin/shipment-evidence` (Partly built), `/admin/po-management`. 1280×800 (not a named 390 workflow). D-0002 untouched.

**Design language:** FROZEN v1.1 is **demoted**. Production follows implemented design-lab React.

**Deferred:** BACKLOG-174–177. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. CDP `Emulation.setDeviceMetricsOverride` denied (`BROWSER_UNSAFE`).

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).
