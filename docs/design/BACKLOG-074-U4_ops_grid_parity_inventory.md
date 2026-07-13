# BACKLOG-074 U4 — Ops / admin grid parity inventory

**Unit:** U4 (docs)  
**Purpose:** Inventory matrix for ops/admin surfaces **outside** Theme B masters.  
**Status (2026-07-12):** **SUPERSEDED lock** — Warren: real parity = adopt **`MasterDataGridShell`** on ops **list** surfaces (same component as Customers / Products / Distributors). Prior “composed chrome without shell” baseline is **revoked** as the definition of done.

**Still excluded:** chart-only Channel Ops **Overview**; import **`ImportStewardCandidateWorkspace`** (steward candidate UI). Domain master-only actions (promote / disposition) stay optional — do not drag them onto ops by default.

**Reference:** `docs/design/BACKLOG-061-U4_master_grid_capability_matrix.md` — shell contract.

---

## Parity bar (authoritative)

| Surface class | Bar |
|---------------|-----|
| Masters + ops **list/workbench** grids | **`MasterDataGridShell`** |
| Chart-only Overview | Not a grid surface — no shell |
| Import steward candidate workspace | Keep `ImportStewardCandidateWorkspace` — do not shell-swap |

---

## Surfaces in scope for shell adoption

| Surface | Status (2026-07-13) | Notes |
|---------|---------------------|--------|
| Inbound shipping `/shipping` | **Done** + columns | Optionals in shell Columns (Additional); skip/limit adapted |
| Channel Ops Sell-out / Inventory / Movements | **Done** + columns | Catalogue specs discovery on sell-out; not Overview |
| CST steward list tabs | **Done** + key-account bulk | batch-patch; aliases confirm/reject |
| PVE exception lists | **Done** + polish | Per-category storage key; drill deferred |
| CPOR cases list | **Done** | Shell; create + row→detail retained |
| PM gaps worklist | **Done** | Inline selection; shell modal bulk off |
| Shipment evidence list | **Done** | Shell + keep raw Additional columns dialog |
| PO gap grid | **Deferred** | Opus: mid-page friction; separate opt-in later |
| PVE drill | **Deferred** | Client nested drill |
| Follow-on | — | PO gap opt-in when Warren asks |

**Review pack:** `.tmp/OPS_MASTER_GRID_SHELL_AUDIT.md` · Consultant default **Opus**

---

## Historical note (revoked)

Earlier U4 ranking treated “composed chrome” (`EnterpriseDataGrid` + `ModuleDataSection` + `ModuleGridToolbar`) and “no shell on CST” as the beachhead. Waves 1–5 / Units 1–5 shipped that stack. **Warren 2026-07-12:** that is **not** parity vs master grids — proceed with shell adoption.

Explicit non-goals that **remain:** `ColumnSelectorModal`; DSI steward checkbox semantics on masters; schema without approval; default-hide dispositioned rows.
