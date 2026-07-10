# Current state

**Last updated:** 2026-07-10 (U-B2 shell adopt ready to commit)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/backlog-061-entity-promote-in-place` |
| **HEAD** | `d58e38c` (+ U-B2 uncommitted) |
| **PR** | Not opened yet |
| **Alembic (DB)** | **`20260710_0071`** on cip |

---

## Units

| Unit | Tip | Fable verify |
|------|-----|--------------|
| BACKLOG-061-U-G2 shell + customers | `d58e38c` | **PASS** |
| BACKLOG-061-U-B2 products+dist shell | local | tests green · VERIFY after commit |
| BACKLOG-061-U3 / U-D1 | `063c19b` | **PASS** · 0071 |
| BACKLOG-061-U2b mint | `66003db` | **PASS** · 0070 |

---

## Next

1. Commit + Fable VERIFY U-B2 (shell adopt only).
2. Dist bulk promote + disposition UI (follow-on after PASS).
3. Deferred: BACKLOG-073 import-job fact purge.

**Do not re-audit:** U2a/U2b/U-D1/U-G2 PASSes.
