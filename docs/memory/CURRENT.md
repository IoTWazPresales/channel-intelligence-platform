# CURRENT state

**Last updated:** 2026-07-27 (Unit F complete; E VERIFY deferred)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-listing-status-audit` |
| **Alembic (DB)** | **`20260727_0074` on cip** |
| **HEAD** | `a80f58a` (Unit F complete / BACKLOG-075) |
| **Pushed?** | yes |
| **Next** | Opus VERIFY Unit E when usage resets; then PR soak / promote when ready. |

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

---

## Unit E2 / E1

| Label | Fact |
|-------|------|
| **E2** | Resolution-plan compute/apply-async + `SLOT_CST_RESOLUTION_PLAN` (D-019); BACKLOG-074 shipped |
| **E1** | Suggestions + resolve/ignore/bulk + Import Centre UI (D-018) |
| **Opus VERIFY** | **Deferred** |

---

## Do not

- Claim Unit E PASS without Opus VERIFY
- Put importer-prefixed modules under `features/import-steward/` (D-006)
- Change DSI product tier order
