# Current state

**Last updated:** 2026-07-10 (U2b implemented — Fable VERIFY pending session limit ~12:40 SAST)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/backlog-061-entity-promote-in-place` |
| **HEAD** | (see git after U2b commit) |
| **PR** | Not opened yet |
| **Alembic (DB)** | **`20260709_0069`** on cip — **0070 authored, NOT applied** |

---

## Units

| Unit | Tip | Fable verify |
|------|-----|--------------|
| BACKLOG-061-U2b (Candidate A mint) | pending commit | **awaiting VERIFY** (CLI rate limit) |
| BACKLOG-061-U2a (mint research note) | `198507e` | **PASS 2026-07-10** |
| BACKLOG-061 BP1 | `82ef990` | **PASS** |
| BACKLOG-061 B2-B4 | `9cfb67f` | **PASS** |
| BACKLOG-061 B1 | `a824c9a` | **PASS** |
| BACKLOG-072 | `0202098` | **PASS** |

---

## Locked decisions

- Format: **Candidate A** `CUST-{SEQ:06d}` (Warren pick)
- Settings: `tenant_id` + seeded `default`; next_seq=1 + silent bump
- Mint UX: Select-N ? dry-run ? confirm; cap 500; client chunks
- No-code disposition: deferred
- **STOP:** do not `alembic upgrade` 0070 on cip until Warren approves

---

## Next

1. Re-run Fable VERIFY for U2b after CLI session limit (~12:40 SAST).
2. Warren applies `20260710_0070` on cip.
3. Optional dry-run mint smoke on a small TMP selection.

**Do not re-audit:** BP1/B1–B4/072/U2a PASSes; Candidate A pick; 0069 applied.
