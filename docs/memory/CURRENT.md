# CURRENT state

**Last updated:** 2026-07-27 (E2 + Unit F Tier 0; VERIFY deferred)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-listing-status-audit` |
| **Alembic (DB)** | **`20260727_0074` on cip** |
| **HEAD** | *(set after E2/F0 commits)* |
| **Pushed?** | pending |
| **Next** | Unit F remainder ([BACKLOG-075](../BACKLOG.md) Tier 1–3). Opus VERIFY Unit E when usage resets. |

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.**  
Authoritative steward slot inventory: `docs/STEWARD_EXPERIENCE_CONTRACT.md` (**v1.5**).

**No-Opus mode:** E1+E2 **implemented, VERIFY deferred** — do **not** claim PASS. C PASS @ `4a63a30`; D PASS @ `cc0138a`.

**Consolidation arc:** A–D PASS; **E1+E2 implemented (VERIFY deferred)**; **F Tier 0 shipped**; F remainder = BACKLOG-075.

---

## Unit E2 / E1

| Label | Fact |
|-------|------|
| **E2** | Resolution-plan compute/apply-async + `SLOT_CST_RESOLUTION_PLAN` (D-019); BACKLOG-074 shipped |
| **E1** | Suggestions + resolve/ignore/bulk + Import Centre UI (D-018) |
| **Opus VERIFY** | **Deferred** |

---

## Unit F (Tier 0)

| Label | Fact |
|-------|------|
| **Shipped** | Orphan/deprecated retirements + DSI section inlines Steward bulk/drawer |
| **Remainder** | BACKLOG-075 — inboundEvidence move, DSI cluster relocate, rename shared helpers |

---

## Do not

- Claim Unit E PASS without Opus VERIFY
- Put importer-prefixed modules under `features/import-steward/` (D-006)
- Change DSI product tier order
