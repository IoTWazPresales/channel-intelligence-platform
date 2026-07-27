# CURRENT state

**Last updated:** 2026-07-27 (Merged feat/dsi-unified-multifile into this branch)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-listing-status-audit` |
| **Alembic (DB)** | **`20260727_0074` on cip** |
| **HEAD** | `7f04c79` — merge feat/dsi-unified-multifile into this branch |
| **Pushed?** | pending push |
| **Next** | Warren smoke-test (DSI multifile + steward); then PR → main when ready. |

---

## Merge note (2026-07-27)

Merged `feat/dsi-unified-multifile` (`2c2391e`) into this branch (base `618448c`).  
**Kept:** Unit F layout (`steward*` / `admin/imports/dsi/` / `shipment-evidence/`); CPOR + Units A–F; shipping KPIs.  
**Restored:** DSI multi-file batch, coverage, header sniff, file stamps, nested mapping skip in pipeline.  
**BACKLOG ID remap:** multifile `074`→**077** (email ingest), `075`→**078** (layout-coalesce follow-ons) — this branch already owned 074/075 (CST E2 / Unit F shipped) and **076**.

---

## Shipping commercial KPIs (wired)

| Label | Fact |
|-------|------|
| **Contract** | `docs/SHIPPING_COMMERCIAL_KPI_CONTRACT.md` |
| **Predicates** | `shipping_commercial_kpis.py` — current-incoming ≤90d; overdue = promise past ∩ not stale ∩ ETA in window; arriving hero = **qty** |
| **API** | `/commercial-summary` + `/eta-shifts` + `/lines` full filter parity (lineup + `cohort=`) |
| **Phase 0 (cip)** | All-scheduled **$288M** → gated **~$63.4M**; arriving **6,653 units** / 57 lines; overdue 1049→884 |
| **BACKLOG** | **076** amount scale junk; **062** re-measured open+shipped pairs |
| **Out of scope** | MasterDataGridShell migration (not done) |

---

## DSI unified multifile (restored onto this branch)

| Label | Fact |
|-------|------|
| **Batch** | `dsi_batch.py` + Import Centre `DsiBulkUploadDialog` capability-merge |
| **Coverage** | `dsi_coverage.py` + `DsiCoveragePanel` |
| **Stamps** | `dsi_file_*` distributor + snapshot period |
| **Workbook** | header sniff / nested `file::sheet` mapping; pipeline skips re-infer when premapped |
| **Follow-ons** | BACKLOG-**078** layout-coalesce UI; BACKLOG-**077** email ingest |

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.**  
Authoritative steward slot inventory: `docs/STEWARD_EXPERIENCE_CONTRACT.md` (**v1.6**).

**No-Opus mode:** E1+E2 **implemented, VERIFY deferred** — do **not** claim PASS. C PASS @ `4a63a30`; D PASS @ `cc0138a`.

**Consolidation arc:** A–D PASS; **E1+E2 implemented (VERIFY deferred)**; **Unit F shipped** (BACKLOG-075).

---

## Unit F (complete)

| Label | Fact |
|-------|------|
| **Tier 0** | Orphan/deprecated Dsi wrappers retired; DSI uses Steward bulk/drawer |
| **Tier 1** | `inboundEvidence*` → `admin/shipment-evidence/`; shared context utils → `stewardEvidenceContextDisplayUtils` |
| **Tier 2** | DSI-only cluster → `admin/imports/dsi/` (+ domain barrel) |
| **Tier 3** | Shared helpers → `steward*` names; DSI filter logic → `dsi/dsiStewardCandidateFilterLogic` |
| **Engine** | Zero `dsi*` / `Dsi*` filenames remain under `features/import-steward/` |
