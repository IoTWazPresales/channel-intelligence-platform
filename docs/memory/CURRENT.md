# Current state

**Last updated:** 2026-07-10 (U2a Fable PASS — Warren format pick gates U2b)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/backlog-061-entity-promote-in-place` |
| **HEAD** | `198507e` (in sync) |
| **PR** | Not opened yet |
| **Alembic (DB)** | **`20260709_0069`** on cip; listing table GRANTs to `cip` |

---

## Units

| Unit | Tip | Fable verify |
|------|-----|--------------|
| BACKLOG-061-U2a (mint research note) | `198507e` | **PASS 2026-07-10** |
| BACKLOG-061 BP1 (bulk CSV promote + Products cols) | `82ef990` | **PASS 2026-07-10** |
| BACKLOG-061 B2-B4 | `9cfb67f` | **PASS 2026-07-10** |
| BACKLOG-061 B1 | `a824c9a` | **PASS** |
| BACKLOG-072 | `0202098` | **PASS** |

---

## Locked decisions (Warren 2026-07-10)

- Codes: **import when available OR system mint** (multi-tenant).
- BP1 = CSV/paste mapping only — **no mint**.
- Batch: **partial success** + per-row report.
- U2: research-first; settings by `tenant_id` (one seeded row); Select-N ? dry-run ? confirm; mint silent bump; no-code disposition **deferred**.
- Theme A (bulk promote) before Theme B (grid shell).
- Interviews: **CLI Fable in Cursor chat** — not browser Claude.

---

## Next

1. **Warren picks Candidate A / B / C** (recommendation: **A** `CUST-######`).
2. U2b: settings alembic + mint service + batch mint mode (**STOP before cip apply**).
3. Optional: open/merge PR after U2b or before.

**Do not re-audit:** BP1/B1–B4/072/U2a PASSes; 0069 applied + grants; single-row promote contract; TMP-DIST already active on cip.

---

## Proven vs unproven

- **Proven (wired + Fable PASS):** single-row promote; bulk CSV promote API/UI; Products default columns; verified?active remap; U2a research note.
- **Unproven on soak:** bulk promote against full ~4,892 TMP list with real ERP codes (needs Human CSV).
- **Planned:** U2b mint after format pick; Theme B grid shell.
