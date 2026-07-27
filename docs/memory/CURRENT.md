# CURRENT state

**Last updated:** 2026-07-27 (Shipping commercial KPI contract rebuild)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-listing-status-audit` |
| **Alembic (DB)** | **`20260727_0074` on cip** |
| **HEAD** | `26dbf99` (shipping commercial KPI rebuild) |
| **Pushed?** | yes |
| **Next** | Merge `feat/dsi-unified-multifile` **into this branch** (expect heavy conflict from Unit F renames); then PR → main. |

---

## Shipping commercial KPIs (implemented, uncommitted)

| Label | Fact |
|-------|------|
| **Contract** | `docs/SHIPPING_COMMERCIAL_KPI_CONTRACT.md` |
| **Predicates** | `shipping_commercial_kpis.py` — current-incoming ≤90d; overdue = promise past ∩ not stale ∩ ETA in window; arriving hero = **qty** |
| **API** | `/commercial-summary` + `/eta-shifts` + `/lines` full filter parity (lineup + `cohort=`) |
| **Phase 0 (cip)** | All-scheduled **$288M** → gated **~$63.4M**; arriving **6,653 units** / 57 lines; overdue 1049→884 |
| **BACKLOG** | **076** amount scale junk; **062** re-measured open+shipped pairs |
| **Out of scope** | MasterDataGridShell migration (not done) |

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
