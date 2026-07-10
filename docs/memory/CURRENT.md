# Current state

**Last updated:** 2026-07-10 (U-D1 Fable PASS; U-G1 matrix written; Warren applies 0071)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/backlog-061-entity-promote-in-place` |
| **HEAD** | `063c19b` (+ matrix commit pending) |
| **PR** | Not opened yet |
| **Alembic (DB)** | **`20260710_0070`** on cip · **`0071` authored, NOT applied** (awaiting Warren) |

---

## Units

| Unit | Tip | Fable verify |
|------|-----|--------------|
| BACKLOG-061-U3 / U-D1 disposition | `063c19b` | **PASS 2026-07-10** |
| BACKLOG-061-U-G1 capability matrix | docs pending | review gate before U-G2 |
| BACKLOG-061-U2b mint | `66003db` | **PASS** · **0070 applied** |
| Prior 061/072 | — | **PASS** |

---

## Next

1. **Warren applies `20260710_0071` on cip** (confirm `.env` points at `cip` first).
2. Review U-G1 matrix ? then U-G2 shell + U-B2 (distributor batch) in a **fresh chat** (large).
3. Soak: **Warren owns**.

**Do not re-audit:** U2a/U2b/U-D1 PASSes; Candidate A; 0070 applied.
