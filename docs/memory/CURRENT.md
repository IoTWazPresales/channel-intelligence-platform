# Current state

**Last updated:** 2026-07-10 (handover — dual-agent skill + BP1 done; Unit 2 next chat)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/backlog-061-entity-promote-in-place` |
| **HEAD** | `7ef261c` (in sync with origin; feature tip `82ef990`) |
| **PR** | Not opened yet — recommend open/merge when ready |
| **Alembic (DB)** | **`20260709_0069`** on cip; listing table GRANTs to `cip` |

---

## Units

| Unit | Tip | Fable verify |
|------|-----|--------------|
| BACKLOG-061 BP1 (bulk CSV promote + Products cols) | `82ef990` | **PASS 2026-07-10** |
| BACKLOG-061 B2-B4 | `9cfb67f` | **PASS 2026-07-10** |
| BACKLOG-061 B1 | `a824c9a` | **PASS** |
| BACKLOG-072 | `0202098` | **PASS** |

---

## Locked decisions (Warren 2026-07-10)

- Codes: **import when available OR system mint** (multi-tenant).
- BP1 = CSV/paste mapping only — **no mint**.
- Batch: **partial success** + per-row report.
- Theme A (bulk promote) before Theme B (grid shell).
- Interviews: **CLI Fable in Cursor chat** — not browser Claude.

---

## Workflow

- Personal skill: `~/.cursor/skills/dual-agent-fable` (any app)
- CIP entry: `.cursor/skills/cip-dual-agent-fable` + `docs/WORKFLOW_DUAL_AGENT.md`

---

## Next (new chat)

1. **BACKLOG-061-U2** — per-tenant customer code mint convention (see `docs/BACKLOG.md`).
2. Optional: open/merge PR for this branch before or after U2.
3. Theme B grid shell later (capability matrix first).

**Do not re-audit:** BP1/B1–B4/072 PASSes; 0069 applied + grants; single-row promote contract; TMP-DIST already active on cip.

---

## Proven vs unproven

- **Proven (wired + Fable PASS):** single-row promote; bulk CSV promote API/UI; Products default columns; verified?active remap.
- **Unproven on soak:** bulk promote against full ~4,886 TMP list with real ERP codes (needs Human CSV).
- **Planned:** U2 mint; Theme B grid shell.
