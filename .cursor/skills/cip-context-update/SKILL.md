---
name: cip-context-update
description: >-
  Update the memory palace after significant Channel Intelligence Platform work.
  Use when the user asks update CONTEXT, memory palace, record session outcome,
  or at end of a significant task. Updates CURRENT.md + CONTEXT changelog.
disable-model-invocation: true
---

# CIP memory palace update

Record **what happened** for the next agent. **`docs/memory/CURRENT.md`** is the
authoritative short state; **`CONTEXT.md`** is router + changelog only.

## Hard rules

1. **Update `docs/memory/CURRENT.md`** — keep under ~120 lines; replace stale sections. Pin only what `git rev-parse` + running code show now. Docs and BACKLOG/ROADMAP “Done” are claims until checked in the tree.
2. **Append one changelog line** to `CONTEXT.md` (newest-first bullets under the router — this repo does not use a changelog table).
3. **NEVER** restore duplicate `## CURRENT STATE — supersedes every block below` blocks in `CONTEXT.md`.
4. **NEVER** edit `docs/memory/CONTEXT-archive-*.md`.
5. If docs conflict with code or each other → **ask Warren** before updating; then fix `CURRENT.md`.
6. Do not update for trivial changes unless user asked.
7. **Hash on the changelog, not as HEAD in CURRENT:** a commit cannot contain its own hash. CURRENT **Branch** is the branch name. After the commit that includes CURRENT, if the CONTEXT changelog line still has no hash, add `git rev-parse --short HEAD` of that pin in a follow-up commit before push. Confirm HEAD with git — never treat a pin hash in CURRENT as HEAD. Do not `git commit --amend` unless the user asked and amend rules are met.

## When to run

- End of significant implementation, audit, or soak
- User: "update CONTEXT", "update memory palace", "record this"
- After merge-worthy commit (note hash in changelog)

**Defer to user** if unsure whether the task was significant enough.

## Required fields in CURRENT.md

Keep these sections (edit in place):

| Section | Content |
|---------|---------|
| Branch and delivery | branch, HEAD, PR, Alembic (code + applied if known) |
| Database and environment | active DB, risks |
| Dev topology | processes Warren uses |
| What is working | bullet list |
| In progress / not proven | open incidents |
| Next | 1–4 concrete steps |
| Blockers requiring Warren | migrations, main promotion, rules changes |

## Language discipline

| Say | When |
|-----|------|
| **Proven live** | Soaked on real DB / user confirmed |
| **Wired + unit-tested** | Tests pass; live path not exercised |
| **Planned** | Approved direction, not started |
| **Ops required** | Needs API/worker restart |

## Git / Alembic

- Branch + `git rev-parse --short HEAD`
- Push state from `git status`
- Alembic: file id if created; applied only if user confirmed `alembic current`

## What NOT to put in CURRENT.md

- Long history → changelog one-liner or leave in archive
- Deferrals → `docs/BACKLOG.md` with TRIGGER
- Secrets, `.env` values

## Procedure

1. Read `docs/memory/CURRENT.md` and `docs/memory/MEMORY_PALACE.md`.
2. Draft updated `CURRENT.md`.
3. Add a newest-first changelog **bullet** to `CONTEXT.md` (`- YYYY-MM-DD — summary`).
4. If architecture changed, bump `last_verified` in relevant `docs/memory/derived/*.md`.
5. Tell user: one-line summary of what changed in CURRENT.md.
6. After commit: if the CONTEXT changelog line has no hash, add `git rev-parse --short HEAD` of that pin before push (see Hard rule 7).

## Related skills

| Invoke | When |
|--------|------|
| `Run cip-session-handover` | Next chat orientation |
| `Run cip-git-handoff` | Before update if switching environments |

See [reference.md](reference.md) for CURRENT.md example.
