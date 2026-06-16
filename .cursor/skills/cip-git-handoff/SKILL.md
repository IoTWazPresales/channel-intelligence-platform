---
name: cip-git-handoff
description: >-
  Git sync between Channel Intelligence Platform local desktop and Cursor cloud
  clones via GitHub. Use when switching environments, before leaving for cloud,
  after arriving from cloud, push before switch, or unpushed commits handoff.
  Explicit path staging only; never git add -A.
disable-model-invocation: true
---

# CIP Git Cloud ↔ Local Handoff

Local folder and cloud agent workspace are **separate clones**. GitHub (`origin`)
is the single source of truth. Never assume the other environment has your commits.

## When to run

- "Switching to cloud" / "back on local" / "handoff git"
- Before ending a session on one machine
- After opening the repo on the other machine
- User mentions unpushed commits or branch out of sync

Pair with `Run cip-session-handover` **after arriving** in the new environment.

## Leaving this environment (local → cloud OR cloud → local)

Run in parallel:

```bash
git status
git branch --show-current
git fetch origin
git rev-parse HEAD
git rev-parse @{u} 2>/dev/null || echo "no upstream"
git log --oneline origin/$(git branch --show-current)..HEAD 2>/dev/null | head -10
git log --oneline HEAD..origin/$(git branch --show-current) 2>/dev/null | head -10
```

### Decision tree

| State | Action |
|-------|--------|
| Dirty working tree | Finish commit, stash **intentionally**, or report — do not switch with unexplained dirt unless user asked to stash |
| Local ahead of origin | Commit if needed (**explicit paths only**), then `git push -u origin HEAD` — do not switch until push succeeds or user opts out |
| Origin ahead of local | `git pull --no-rebase origin <branch>` (or merge `origin/main`) — resolve conflicts before switching |
| In sync | Report branch + hash; safe to switch |

### Closing message (required)

State in chat:

1. **Branch name**
2. **Last pushed commit** (short hash + subject)
3. **Whether other environment should `git pull`**
4. **Dirty/untracked** left behind (if any)

## Arriving in the other environment

```bash
git fetch origin
git branch --show-current
git checkout <same-branch>   # or checkout main per user
git pull origin <branch>     # if behind
git status
git rev-parse HEAD
```

Then: `Run cip-session-handover` or read `CONTEXT.md` top block before task work.

## Branch conventions

- Feature branches for agent work — not direct `main` pushes
- **`main` promotion only** when user says "promote to main" or "merge to main"
- Cloud branches `cursor/cloud-agent-*` may not exist locally — `git fetch origin`,
  checkout tracking branch, or merge via `main`

## Staging rules (always)

```bash
git add path/to/specific/file    # OK
git add -A                       # NEVER
git add .                        # NEVER
```

Never commit: `.env`, dumps, logs, `.next/`, `node_modules/`, `__venv__/`

## Push rules

- Push feature branch: `git push -u origin HEAD` when user asked or handoff requires it
- **Never** `git push` to `main` without explicit promotion instruction
- **Never** force-push `main` without explicit user request

## Output template

```markdown
## Git handoff — [leaving | arriving]

**Environment:** [local desktop | Cursor cloud]
**Branch:** `…`
**HEAD:** `abcdef1` — subject
**Sync:** [in sync | N ahead (unpushed) | N behind origin]

**Actions taken:**
- …

**Other environment:**
- [ ] `git fetch origin && git checkout <branch> && git pull origin <branch>`
- Last pushed: `abcdef1`

**Left untouched:** untracked scripts, .env, etc.
```

## Do not

- Switch with unpushed commits the user expects on the other side
- Run destructive git (`reset --hard`, force push) without explicit instruction
- Update git config

## Related skills

| Invoke | When |
|--------|------|
| `Run cip-session-handover` | After pull on arriving side |
| `Run cip-context-update` | Record handoff outcome if significant |
| `Run cip-skills-index` | List all CIP skills |

Full rule text also lives in `.cursor/rules/cloud-local-git-handoff.mdc`.
