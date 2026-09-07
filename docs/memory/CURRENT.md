# CURRENT state

**Last updated:** 2026-09-07 (N-0018 implement, not complete)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `9e93c77` (N-0018 Supply & Inbound chrome)

**Last ledger pin:** `37c6286` (N-0011 independent GOV-008)

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514 rev **383**. **N-0018 in_progress** implement (lease `NS9_SUPPLY_20260907` / gov-001, expires `2026-09-07T15:15:22Z`). **N-0011 complete**. **N-0017 complete**. **N-0010 rejected**. **Do not start N-0006. Do not reopen N-0013.** Independent GOV-008 for N-0018 is **not** this implementer pass.
- **Product (Supply & Inbound):** Lab `SupplySurface` chrome on `/supply` hub; inbound workspace relocated to `/supply/shipments` (not deleted); `/admin/shipment-evidence` and `/admin/po-management` wrapped. NUMBER RULE on `cip`: open **1964**, ETA-past-no-POD **770** / oldest **123d**, POD this ISO week **0**, PO linked/observed **322/2308** (~14%, not plan units), pipeline units **118024**. Lifecycle three disjoint bars (pipeline/shipped/landed). Arrived UNCOVERED (BACKLOG-178). Plan-unit PO% UNCOVERED (BACKLOG-179). Browser 1280×800 vs lab. Receipts stays **Partly built**.
- **Product (Data & Stewardship / Stock):** as previously pinned.
- **API:** `:8001`. `GET /api/v1/supply/overview` read-only, not behind commercial-planner flag.
- **D-0002** remains the open decision.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. Supply is **not** a named 390 workflow.

**Next:** Independent GOV-008 vs `NS9_SUPPLY_20260907` (new chat). Do not complete N-0018 from this implementer pass.

**Design language:** FROZEN v1.1 is **demoted**. Production follows implemented design-lab React.

**Deferred:** BACKLOG-174–179. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. CDP `Emulation.setDeviceMetricsOverride` denied (`BROWSER_UNSAFE`).

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).
