---
name: cip-session-handover
description: >-
  Orient a new or continuing Channel Intelligence Platform session from the memory
  palace. Use when the user says continue, what's next, handover, read CONTEXT,
  new chat, where were we, outstanding tasks, or starts work without stating
  branch or current incident. Also use after switching local desktop ↔ Cursor cloud.
---

# CIP Session Handover

Orient before doing any implementation. **Read first, act second.**

## When to run

- New chat continuing prior work
- User asks "what's next?", "outstanding tasks?", "continue from CONTEXT"
- User arrives from another environment (local ↔ cloud)
- User gives a task but not branch, Alembic head, or current incident context

**Do not** run a full handover when the user gave a narrow, self-contained task with
enough context (e.g. "fix typo in README.md").

## Read order (mandatory)

1. **`CONTEXT.md`** — read only the **top `## CURRENT STATE` block** first (newest
   section supersedes everything below it). Scan older blocks only if the user
   asks for history or the top block is ambiguous.
2. **`AGENTS.md`** — operating protocol; note fix-protocol requirement for bug/perf work.
3. **`docs/BACKLOG.md`** — only entries whose **TRIGGER** appears fired or the user
   explicitly asked about backlog/outstanding work.

Do **not** read the entire CONTEXT history unless asked — it is append-only and long.

## Git orientation (parallel commands)

Run these in parallel before reporting state:

```bash
git status
git branch --show-current
git rev-parse HEAD
git fetch origin
git rev-parse @{u} 2>/dev/null || git rev-parse origin/main
git log --oneline origin/$(git branch --show-current)..HEAD 2>/dev/null | head -5
git log --oneline HEAD..origin/$(git branch --show-current) 2>/dev/null | head -5
```

Report:

| Field | Source |
|-------|--------|
| Branch | `git branch --show-current` |
| HEAD | short hash + subject |
| Pushed? | local ahead / remote ahead / in sync |
| Working tree | clean / dirty (summarise untracked vs modified) |

If switching environments: follow `.cursor/rules/cloud-local-git-handoff.mdc` —
state whether the other side should `git pull`.

## Alembic (report only — do not upgrade)

If the top CONTEXT block mentions Alembic head, note it. Optionally verify code
head from latest file in `apps/api/alembic/versions/`. **Do not run
`alembic upgrade`** unless the user explicitly instructs.

## Classify current work

From the top CONTEXT block, separate:

| Label | Meaning |
|-------|---------|
| **Proven live** | Soaked on real DB / user confirmed in production-like run |
| **Wired + unit-tested** | Code merged; tests pass; not yet proven on failure path or soak |
| **Planned / approved** | Direction agreed; implementation not started |
| **Blocked** | Needs user decision, migration approval, or service restart |

Use this language in the handover — avoids treating "tests pass" as "hang is fixed".

## Output template

Reply with this structure (adjust sections that don't apply):

```markdown
## Session handover

**Branch:** `…` @ `abcdef1` — [in sync | N commits ahead (unpushed) | N behind origin]

**Current focus:** [one sentence from top CONTEXT block]

**Proven vs unproven:**
- Proven: …
- Wired but unproven: …

**Alembic:** code head `…` — [matches CONTEXT | drift — report]

**Recommended next step:** [single concrete action]

**Outstanding (if asked):**
- [ ] …

**Blockers / needs your call:**
- …
```

Keep the handover **short** (under ~30 lines). Link to CONTEXT sections; don't
paste the whole file.

## Environment detection

Before suggesting service commands:

| Signal | Mode |
|--------|------|
| `WINDIR` set / Windows / `docker info` fails | **Local** — no Docker; `pnpm dev:api`, Postgres on `:5432` |
| `CURSOR_CLOUD` or `docker info` succeeds | **Cloud** — Docker Compose via `pnpm docker:up:detached` |

Ports: web `:3000`, API local `:8001`, API Docker `:8010`, DB `cip` on `:5432`.

## After handover

- If the user's implied next step is a **bug/perf fix on an importer** →
  `Run cip-fix-protocol-audit` before writing code.
- If the user only wanted orientation, **stop** — do not start implementation
  unless they ask.
- End of significant work → `Run cip-context-update`
- Switching machines → `Run cip-git-handoff`
- All skill names → `Run cip-skills-index`

## Do not

- Run migrations, seeds, or import validate/apply without explicit approval
- Assume cloud and local share the same working tree
- Treat stale CONTEXT blocks below the top section as current truth
- Start coding before reporting handover when this skill was triggered

## Additional resources

- Git handoff detail: [reference.md](reference.md)
- Fix protocol (importer bugs): `AGENTS.md` § Fix protocol
- Deferred work triggers: `docs/BACKLOG.md`
