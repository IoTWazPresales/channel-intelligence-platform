# Current state

**Last updated:** 2026-07-10 (U-G2 shell implemented locally; test-junk cleanup deferred)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/backlog-061-entity-promote-in-place` |
| **HEAD** | `3dd9349` (U-G2 uncommitted locally) |
| **PR** | Not opened yet |
| **Alembic (DB)** | **`20260710_0071`** on cip |

---

## Units

| Unit | Tip | Fable verify |
|------|-----|--------------|
| BACKLOG-061-U-G2 shell + customers | local (uncommitted) | smoke OK · VERIFY pending commit |
| BACKLOG-061-U3 / U-D1 disposition | `063c19b` | **PASS** · **0071 applied** |
| BACKLOG-061-U-G1 matrix | `beb537e` | docs |
| BACKLOG-061-U2b mint | `66003db` | **PASS** · **0070 applied** |

---

## Next

1. **Commit + Fable VERIFY U-G2** (Warren ask).
2. **U-B2** — products/distributors shell + dist batch/disposition.
3. **Deferred:** test-import junk cleanup ? **BACKLOG-073** (import-job fact rollback/purge). Do **not** park/exclude or default-hide as substitute. Search debounce / header?server sort optional later (not cheap junk-hide).

**Do not re-audit:** U2a/U2b/U-D1 PASSes; 0070+0071 applied; Candidate A.
