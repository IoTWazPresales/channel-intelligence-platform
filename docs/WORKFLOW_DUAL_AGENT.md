# Dual-agent workflow — CIP overlay (Cursor ↔ CLI Fable)

**Purpose:** Channel Intelligence Platform standing rules for the dual-agent loop.  
**Operational skill (any app):** `~/.cursor/skills/dual-agent-fable` — run `dual-agent-fable` or `cip-dual-agent-fable`.  
**Status:** Active · 2026-07-10  

**Do not put here:** current branch, HEAD, job IDs, Alembic tip — those live in `docs/memory/CURRENT.md`.

---

## Roles (fixed)

| Role | Where | Owns | Must not |
|------|--------|------|----------|
| **Warren** | Human | Priorities, merge/promote, cip writes, alembic upgrade approval | — |
| **Cursor** | This IDE | Phase A → implement → tests → SELECT-only validate → CURRENT/CONTEXT → commit/push → seed Fable | Start next unit before PASS; apply alembic without Warren; `git add -A` |
| **CLI Fable** | `claude -p --model fable` | CONSULT (interview/scope/prompt), VERIFY (PASS/STOP) | Edit files during consult/verify; run migrations; invent schema against locked specs |

**Browser Claude / claude.ai project chat is retired for this loop.** Interviews and brainstorming run in the Cursor chat via CLI Fable (CONSULT mode). Warren stays in one thread.

---

## When to use

- Multi-unit roadmap / BACKLOG Large items
- Spec-locked work where inventing schema is expensive
- Mushy product decisions (CONSULT interview before IMPLEMENT)
- Any unit that needs an independent verify before the next unit

**Not required for:** one-line fixes, typo commits, single-file obvious bugs with no architectural choice.

---

## Loop (one unit) — see skill for full recipes

```
0. Sync pin (Cursor)
1. CONSULT (CLI Fable) — interview if mushy; short scope lock if BACKLOG complete
2. Unit prompt (Fable) → Warren skims → Cursor IMPLEMENT
3. Cursor: tests → CURRENT/CONTEXT → explicit git add → commit → push → report
4. VERIFY (CLI Fable) → VERDICT: PASS | STOP
5. On PASS: next prompt or queue empty; on STOP: fix and re-verify
```

**Hard gate:** no next-unit implementation until CLI Fable writes **`VERDICT: PASS`**.  
Warren may waive in writing only — record `Fable verify: WAIVED <YYYY-MM-DD>` in CURRENT.md.

---

## CIP standing rules (always unless Warren waives in writing)

- Spec / BACKLOG entry read-only unless Warren says edit
- No cip writes without Warren approval (SELECT-only OK)
- No alembic upgrade without Warren; author migration only after Phase A proves need + STOP before apply
- `ALLOW_TESTS_ON_DEV_DB` unset for normal unit tests
- Explicit `git add <paths>` — never `-A` / `.`
- FLAG ≠ BLOCK where domain requires
- Never auto-create `dim_product` / `dim_customer` / `dim_distributor` from import evidence

---

## Scope lock

| Situation | CLI Fable CONSULT does |
|-----------|------------------------|
| Greenfield / mushy | Interview (max 5 questions/round) → READY with unit prompt |
| BACKLOG entry complete | Short scope lock only — do not re-interview the whole idea |
| Large effort | Prefer split into 2–3 Cursor units |

Copy BACKLOG **Regression traps** / **Out of scope** into the unit prompt verbatim.

---

## Artifacts

| File | Owner |
|------|--------|
| `.tmp/<topic>_consult_fable_*.md` | Cursor / CLI Fable |
| `.tmp/<unit>_cursor_prompt.md` | Fable (CONSULT READY) |
| `.tmp/<unit>_cursor_report.md` | Cursor |
| `.tmp/<unit>_fable_*.md` | Cursor / CLI Fable |
| `docs/memory/CURRENT.md` | Cursor after unit + verify line |
| `CONTEXT.md` changelog | Cursor |

`.tmp/` is never committed.

---

## Invoke (repo root, PowerShell)

```powershell
Get-Content .tmp\<name>_fable_seed.md -Raw |
  claude -p --model fable --output-format text --dangerously-skip-permissions |
  Out-File .tmp\<name>_fable_response.md -Encoding utf8
```

---

## Handover / new chat

```
Run cip-session-handover
Run cip-dual-agent-fable
Branch: <name> @ <short SHA>
Next: <unit from CURRENT>
Skip: <do not re-audit>
Mode: CONSULT
```

---

## Related

- Personal skill: `~/.cursor/skills/dual-agent-fable`
- Project skill: `.cursor/skills/cip-dual-agent-fable`
- `docs/memory/CURRENT.md` — now
- `docs/BACKLOG.md` — deferred + TRIGGER
- `.cursor/skills/cip-session-handover` — orient new chat
