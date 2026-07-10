# Current state

**Last updated:** 2026-07-10 (BACKLOG-061 BP1 bulk promote + Products default columns)
**Verify git:** `git branch --show-current` ù `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/backlog-061-entity-promote-in-place` |
| **HEAD** | (local ù commit pending Warren) |
| **PR** | Recommend open/merge after BP1 commit |
| **Alembic (DB)** | **`20260709_0069`** on cip; `cip` role GRANTed on listing tables |

---

## Units

| Unit | Tip | Fable verify |
|------|-----|--------------|
| BACKLOG-061 BP1 (bulk CSV promote + Products cols) | pending commit | pending |
| BACKLOG-061 B2ùB4 | `9cfb67f` | **PASS 2026-07-10** |
| BACKLOG-061 B1 | `a824c9a` | **PASS** |
| BACKLOG-072 | `0202098` | **PASS** |

---

## Locked decisions (Warren 2026-07-10)

- Codes: **import when available OR system mint** (multi-tenant).
- Unit 1 = CSV/paste mapping only ù **no mint** (mint = BACKLOG-061-U2).
- Batch semantics: **partial success** + per-row report.
- Theme A (bulk promote) before Theme B (grid shell).

---

## Next

1. Open/merge PR for `feat/backlog-061-entity-promote-in-place`.
2. Unit 2 mint when TRIGGER fires (`docs/BACKLOG.md` BACKLOG-061-U2).
3. Theme B grid shell later (capability matrix first).

---

## Workflow

`docs/WORKFLOW_DUAL_AGENT.md` active.
