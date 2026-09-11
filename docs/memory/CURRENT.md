# CURRENT state

**Last updated:** 2026-09-12 (N-0018 complete — independent GOV-008)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `2a59ce0` (N-0018 implementer validate; product `9e93c77`)

**Last ledger pin:** programme snapshot rev **406** (N-0018 complete)

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514. **N-0018 complete** (impl `NS9_SUPPLY_20260907` / gov-001; independent GOV-008 `GOV008_N0018_20260912` / gov-008, evidence `.eif/audit/gov-008-n0018.md`). **N-0011 complete**. **N-0017 complete**. **N-0010 rejected**. **Do not start N-0006. Do not reopen N-0013.** No ready unblocked leaves.
- **Product (Supply & Inbound):** Lab `SupplySurface` chrome on `/supply`; inbound workspace at `/supply/shipments`; `/admin/shipment-evidence` and `/admin/po-management` wrapped. Loading/`data_unavailable` empty states on the hub. NUMBER RULE `cip` 2026-09-12 re-exec: open **1964**, ETA-past-no-POD **873** / oldest **128d**, POD this ISO week **0**, PO linked/observed **322/2308** (~14%), pipeline units **118024**. Lifecycle three disjoint bars. Arrived UNCOVERED (BACKLOG-178). Plan-unit PO% UNCOVERED (BACKLOG-179). Receipts stays **Partly built**. Open-shipments click → `/supply/shipments`. `/stock?lens=inbound` and `/shipping` → `/supply/shipments`.
- **API:** `:8001`. `GET /api/v1/supply/overview` read-only, not behind commercial-planner flag.
- **D-0002** remains the open decision (untouched). Live `/admin/mappings` still the deferred legacy queue leaf.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. Supply is **not** a named 390 workflow.

**Next:** Operator choice on **D-0002** (mapping-queue restore vs retire). Do not invent a next NS node. Frontier empty.

**Design language:** FROZEN v1.1 is **demoted**. Production follows implemented design-lab React.

**Deferred:** BACKLOG-174–179. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. CDP `Emulation.setDeviceMetricsOverride` denied (`BROWSER_UNSAFE`). `cursor-ide-browser` has no `browser_resize` (Playwright MCP does).

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).
