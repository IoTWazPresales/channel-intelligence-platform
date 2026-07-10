# Current state

**Last updated:** 2026-07-10 (U-B2 Fable PASS — next U-B3 dist bulk promote/disposition)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/backlog-061-entity-promote-in-place` |
| **HEAD** | `c54c32f` |
| **PR** | Not opened yet |
| **Alembic (DB)** | **`20260710_0071`** on cip |

---

## Units

| Unit | Tip | Fable verify |
|------|-----|--------------|
| BACKLOG-061-U-B2 products+dist shell | `c54c32f` | **PASS** |
| BACKLOG-061-U-G2 shell + customers | `d58e38c` | **PASS** |
| BACKLOG-061-U3 / U-D1 disposition | `063c19b` | **PASS** · 0071 |
| BACKLOG-061-U2b mint | `66003db` | **PASS** · 0070 |

---

## Next

1. **U-B3** — distributor bulk promote + disposition UI (mirror customers; API first if missing).
2. Deferred: BACKLOG-073 import-job fact purge.

**Do not re-audit:** U2a/U2b/U-D1/U-G2/U-B2 PASSes.
