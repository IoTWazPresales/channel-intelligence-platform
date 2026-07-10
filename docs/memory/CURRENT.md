# Current state

**Last updated:** 2026-07-10 (0071 applied on cip — ready for U-G2 handover)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/backlog-061-entity-promote-in-place` |
| **HEAD** | `beb537e` |
| **PR** | Not opened yet |
| **Alembic (DB)** | **`20260710_0071`** on cip (disposition columns live) |

---

## Units

| Unit | Tip | Fable verify |
|------|-----|--------------|
| BACKLOG-061-U3 / U-D1 disposition | `063c19b` | **PASS** · **0071 applied** |
| BACKLOG-061-U-G1 capability matrix | `beb537e` | docs — review before U-G2 |
| BACKLOG-061-U2b mint | `66003db` | **PASS** · **0070 applied** |
| Prior 061/072 | — | **PASS** |

---

## Next (new chat)

1. **U-G2** — `MasterDataGridShell` + customers parity (matrix reviewed).
2. **U-B2** — products/distributors shell + distributor batch + disposition wiring.
3. Soak: **Warren owns**.

**Do not re-audit:** U2a/U2b/U-D1 PASSes; 0070+0071 applied; Candidate A; matrix at `docs/design/BACKLOG-061-U4_master_grid_capability_matrix.md`.
