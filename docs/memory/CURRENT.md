# Current state

**Last updated:** 2026-07-10 (U-B3a on cip 0072 ù commit+push then Fable VERIFY)
**Verify git:** `git branch --show-current` ù `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/backlog-061-entity-promote-in-place` |
| **HEAD** | `66ae66d` |
| **PR** | Not opened yet |
| **Alembic (DB)** | **`20260710_0072`** on cip (seed DIST pad6 next_seq=1) |

---

## Units

| Unit | Tip | Fable verify |
|------|-----|--------------|
| BACKLOG-061-U-B3a dist bulk+mint+disposition API | `66ae66d` | pending |
| BACKLOG-061-U-B2 products+dist shell | `c54c32f` | **PASS** |
| BACKLOG-061-U-G2 shell + customers | `d58e38c` | **PASS** |
| BACKLOG-061-U3 / U-D1 disposition | `063c19b` | **PASS** ù 0071 |
| BACKLOG-061-U2b mint | `66003db` | **PASS** ù 0070 |

---

## Next

1. Fable VERIFY U-B3a after push.
2. **U-B3b** ù distributor bulk promote + disposition UI (after U-B3a PASS).
3. Deferred: BACKLOG-073 import-job fact purge.

**Do not re-audit:** U2a/U2b/U-D1/U-G2/U-B2 PASSes.
