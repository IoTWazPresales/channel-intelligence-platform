# Memory palace — read this first

**Purpose:** One index for humans and agents. Stops contradictory reads across
`CONTEXT.md`, session handovers, and derived truth docs.

---

## Read order (every significant task)

| Order | File | Use for |
|-------|------|---------|
| 1 | **`docs/memory/CURRENT.md`** | Authoritative **now**: branch, DB target, topology, what works, blockers, next step |
| 2 | **`docs/memory/ROADMAP.md`** | Phased **what to do next** — all themes with **done vs open** (links BACKLOG IDs) |
| 3 | **`AGENTS.md`** | Agent protocol, fix protocol, git/DB safety, ports |
| 4 | **`.cursor/rules/branch-and-pr-lifecycle.mdc`** | When to merge PR / open new branch |
| 5 | **`.cursor/rules/context-handover-discipline.mdc`** | When to recommend new chat |
| 6 | **`.cursor/rules/Supply-Chain-Intelligence-Project-Rules.mdc`** | Domain architecture, DSI rules, gotchas, stop conditions |
| 7 | **`.cursor/rules/engineering-rules.mdc`** | General engineering behaviour |
| 8 | **`docs/BACKLOG.md`** | **Deferred detail** — full entries + TRIGGER (resume when ROADMAP row is Open) |
| 9 | **`docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md`** | Importer matrix before import/steward changes |

**Do not** read `docs/memory/CONTEXT-archive-*.md` unless you need historical detail.
**Do not** scan old session handover docs for current state — check `CURRENT.md` first.

---

## File roles (no duplicates)

| File | Role | Update when |
|------|------|-------------|
| **`docs/memory/CURRENT.md`** | Single source of truth for **current** state (~100 lines max) | End of every significant task |
| **`CONTEXT.md`** | **Router + changelog** — points here; one-line entries per session | Append changelog line; do not grow unbounded blocks |
| **`docs/memory/ROADMAP.md`** | Phased schedule — open work + done verification | When phases complete or priorities shift |
| **`docs/BACKLOG.md`** | Intentionally **not done** + TRIGGER | Deferring work (see `deferral-discipline.mdc`) |
| **`docs/memory/CONTEXT-archive-*.md`** | Frozen history | Never edit after creation |
| **`docs/memory/derived/*.md`** | Stable architecture truth (async, runtime, data model) | When architecture changes — then bump `last_verified` in file |
| **`docs/DEV_TOPOLOGY.md`** | Supported dev/prod topology matrix | Env or deploy model changes |
| **`docs/ASYNC_AND_BROKER_PATHS.md`** | Short async index → points to derived truth | New Celery enqueue paths |
| Session handovers (`docs/SESSION_HANDOVER_*.md`) | **Point-in-time** snapshots | Do not update for current state |

---

## Conflict resolution (mandatory)

If two sources disagree (e.g. `CURRENT.md` vs code vs `CONTEXT` archive vs a skill):

1. **Stop** — do not implement from the stale source.
2. **Prefer:** running code + git + `CURRENT.md` (newest date wins among docs).
3. **Ask Warren** which source is correct before proceeding.
4. After resolution, update **`CURRENT.md`** and note the fix in **`CONTEXT.md`** changelog.

Never silently pick the older block in an archive or a session handover.

---

## Maintenance workflow (agents)

### After significant work

1. Update **`docs/memory/CURRENT.md`** (replace sections; keep file short).
2. Append **one line** to **`CONTEXT.md` → Changelog** (date + summary + optional commit).
3. New **deferrals** → **`docs/BACKLOG.md`** entry with TRIGGER (not chat-only).
4. Architecture change → update relevant **`docs/memory/derived/*.md`** + `last_verified` date.

### Skills

| Skill | When |
|-------|------|
| `Run cip-session-handover` | New chat, continue, handover, after env switch |
| `Run cip-context-update` | End of session — updates `CURRENT.md` + changelog |
| `Run cip-fix-protocol-audit` | Import/steward/worker bug before coding |

### What does not belong in CURRENT.md

- Long history (→ archive or changelog one-liner)
- Deferred ideas (→ BACKLOG)
- Step-by-step procedures (→ skills or `docs/`)

---

## Topology reminder

Before debugging **worker busy**, **queue timeout**, or **Celery inspect** issues, read
**`docs/DEV_TOPOLOGY.md`**. Windows solo worker + remote Supabase is a **supported but
degraded** dev mode — not production topology.
