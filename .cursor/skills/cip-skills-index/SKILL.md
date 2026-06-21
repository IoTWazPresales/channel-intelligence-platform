---
name: cip-skills-index
description: >-
  List all Channel Intelligence Platform Cursor skills with exact invocation
  names and when to use each. Use when the user asks which skill, list skills,
  how to invoke skills, Run cip, or skill names.
disable-model-invocation: true
---

# CIP Skills Index

Catalog of project skills in `.cursor/skills/`. Invoke by saying **`Run <name>`**
in any chat with this repo open.

## Quick reference

| Skill name | Invoke exactly | Use when |
|------------|----------------|----------|
| **cip-skills-index** | `Run cip-skills-index` | You want this list |
| **cip-session-handover** | `Run cip-session-handover` | New chat, continue, what's next, orient from CONTEXT |
| **cip-fix-protocol-audit** | `Run cip-fix-protocol-audit` | Importer bug/perf — path map **before** code |
| **cip-read-only-audit** | `Run cip-read-only-audit` | Report only, verify hypothesis, find query emitter |
| **cip-context-update** | `Run cip-context-update` | End of session — update `CURRENT.md` + CONTEXT changelog |
| **cip-git-handoff** | `Run cip-git-handoff` | Switching local ↔ cloud, push/pull sync |

## Typical session flows

### New chat, continuing work
```
Run cip-session-handover
```

### Importer hang or slow apply
```
Run cip-read-only-audit
```
(then, after report)
```
Run cip-fix-protocol-audit
```

### Done for the day, switching to cloud
```
Run cip-git-handoff
Run cip-context-update
```

### Arrived on other machine
```
Run cip-git-handoff
Run cip-session-handover
```

## Auto vs explicit invocation

| Skill | Loads automatically? |
|-------|----------------------|
| cip-session-handover | Often — description matches "continue", "what's next" |
| cip-fix-protocol-audit | Often — description matches importer bugs / fix protocol |
| cip-read-only-audit | **Explicit only** — say `Run cip-read-only-audit` |
| cip-context-update | **Explicit only** |
| cip-git-handoff | **Explicit only** |
| cip-skills-index | **Explicit only** |

If auto-invoke does not fire, use **`Run <skill-name>`** — always works when
the skill file exists in `.cursor/skills/<name>/SKILL.md`.

## Skill locations

```
.cursor/skills/
├── cip-skills-index/
├── cip-session-handover/
├── cip-fix-protocol-audit/
├── cip-read-only-audit/
├── cip-context-update/
└── cip-git-handoff/
```

Project skills (committed to repo) sync to cloud clone after `git pull`.
Personal skills live in `~/.cursor/skills/` (cross-repo) — not used for these.

## What skills are NOT

| Mechanism | Holds |
|-----------|--------|
| **Skills** | Repeatable *how* (procedure) |
| **`docs/memory/CURRENT.md`** | Authoritative current *what* |
| **`CONTEXT.md`** | Router + changelog |
| **`.cursor/rules/`** | Always-on architecture and safety |
| **`docs/BACKLOG.md`** | Deferred work + TRIGGER |

Do not put job IDs or current branch inside skills — those go in CURRENT.md.

## Planned skills (not created yet)

Mentioned in prior planning; invoke names reserved for future:

| Future name | Purpose |
|-------------|---------|
| `cip-dsi-validate-diagnose` | Read-only hang diagnosis (py-spy, pg_stat, job metadata) |
| `cip-import-job-soak` | Monitor validate/apply soak runs |
| `cip-alembic-migration-safe` | Smoke DB + conflict pre-check before upgrade |
| `cip-supabase-remote-ops` | MCP diagnostics on EU project |
| `cip-backlog-triage` | Summarise BACKLOG entries before implementation |
| `cip-import-parity-implement` | Scoped importer feature at parity bar |

## Copy-paste cheat sheet

```
Run cip-skills-index
Run cip-session-handover
Run cip-fix-protocol-audit
Run cip-read-only-audit
Run cip-context-update
Run cip-git-handoff
```
