---
name: cip-context-update
description: >-
  Update CONTEXT.md after significant Channel Intelligence Platform work using
  insert-only rules. Use when the user asks update CONTEXT, memory palace,
  record session outcome, or at end of a significant task. Never delete or
  rewrite prior CONTEXT sections.
disable-model-invocation: true
---

# CIP CONTEXT.md Update

Record **what happened** in the memory palace. `CONTEXT.md` is operational history
for agents — not user-facing docs.

## Hard rules

1. **INSERT ONLY** — add a new `## CURRENT STATE` section at the **top** of
   `CONTEXT.md` (immediately after the `# Channel Intelligence Platform` title line).
2. **NEVER** delete, rewrite, or reorder prior sections.
3. **NEVER** replace the file wholesale.
4. New section **must** include: `— supersedes every block below` in the heading.
5. Do not update CONTEXT for trivial changes (typo, comment-only) unless user asked.

## When to run

- End of significant implementation, audit, or soak
- User: "update CONTEXT", "record this in memory palace"
- After merge-worthy commit (note hash if committed/pushed)

**Defer to user** if unsure whether the task was significant enough.

## Required fields in new top block

Use this checklist — omit only what truly does not apply:

```markdown
## CURRENT STATE — [Mon D, YYYY] ([short title]) — supersedes every block below

- **Branch:** `branch-name` @ `short-hash` ([pushed | local uncommitted | N ahead])
- **[Incident / goal]:** one-line summary
- **What shipped / found:**
  - bullet list
- **Tests:** what ran, pass/fail counts; note if no DB execution
- **Proven vs unproven:** label live soak vs unit-tested only
- **Next:** single concrete next step
- **Blockers:** ops restart, migration approval, user decision (if any)
```

## Language discipline

| Say | When |
|-----|------|
| **Proven live** | Soaked on real DB / user confirmed behaviour |
| **Wired + unit-tested** | Merged, tests pass, failure path not exercised |
| **Planned** | Approved direction, not started |
| **Ops required** | Code done but needs API/worker restart |

Avoid claiming a hang is fixed if only unit tests passed.

## Git / Alembic fields

- Branch + short HEAD from `git rev-parse --short HEAD`
- Note push state: `git status` / compare to `origin`
- Alembic: migration file id if created; **never** claim applied unless user confirmed `alembic current`

## What NOT to put in CONTEXT

- Full procedure docs → skills or `docs/`
- Intentional deferrals → `docs/BACKLOG.md` with TRIGGER
- Secrets, `.env` values, connection strings

## Procedure

1. Read current top block (do not duplicate unchanged facts unnecessarily).
2. Draft new section with today's date and accurate status.
3. **StrReplace** only the insertion point — insert new block **above** the
   previous top `## CURRENT STATE` section:

```
# Channel Intelligence Platform — Current Context

## CURRENT STATE — [NEW] ...
...

## CURRENT STATE — [OLD] ...
```

4. Verify no prior sections were modified or removed.
5. Tell user: new top heading title + one-line summary.

## Related skills

| Invoke | When |
|--------|------|
| `Run cip-session-handover` | Next chat reads the block you just wrote |
| `Run cip-git-handoff` | Before CONTEXT update if switching environments |
| `Run cip-skills-index` | List all CIP skills |

See [reference.md](reference.md) for a filled example.
