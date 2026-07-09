# Dual-agent workflow — Cursor ↔ Fable (browser + CLI)

**Purpose:** Shared operating procedure for multi-unit product work. Readable by **browser Fable**, **CLI Fable**, and **Cursor**. This is the durable process doc — not a Cursor-only skill (skills come later, after more units prove what is stable).

**Status:** Active · 2026-07-09  
**Do not put here:** current branch, HEAD, job IDs, Alembic tip — those live in `docs/memory/CURRENT.md`.

---

## Roles (fixed)

| Role | Where | Owns | Must not |
|------|--------|------|----------|
| **Warren** | Human | Priorities, paste gate, merge/promote, cip writes, alembic upgrade approval | — |
| **Browser Fable** | Claude.ai / project chat (GitHub-synced) | Interview / scope lock when needed; author Cursor unit prompts | Implement; invent schema against locked specs; skip sync pin |
| **Cursor** | This IDE | Phase A discovery → implement → tests → SELECT-only validate → CURRENT/CONTEXT → commit/push → unit report | Start next unit before Fable verify PASS; apply alembic without Warren; `git add -A` |
| **CLI Fable** | `claude -p --model fable` | Verify Cursor report against repo + spec; PASS/STOP; author next unit prompt only on PASS | Edit files during verify; run migrations; invent schema |

Separation of thinking from typing is intentional. The paste from browser → Cursor is a **review checkpoint**, not waste.

---

## When to use this loop

- Multi-unit roadmap / BACKLOG Large items (e.g. CPOR units, BACKLOG-072)
- Spec-locked work where inventing schema is expensive
- Any unit that needs an independent verify before the next unit starts

**Not required for:** one-line fixes, typo commits, pure docs typos, single-file obvious bugs with no architectural choice.

---

## Loop (one unit)

```
0. Sync pin (Warren → browser Fable)
1. Scope lock (browser Fable) — interview ONLY if mushy; else short split/lock
2. Unit prompt authored (browser Fable) → Warren reads → pastes into Cursor
3. Cursor: Phase A quotes → PROCEED/STOP → implement → tests → SELECT-only cip
4. Cursor: CURRENT.md + CONTEXT changelog → explicit git add → commit → push
5. Cursor writes .tmp/<unit>_cursor_report.md + seeds CLI Fable
6. CLI Fable: PASS or STOP (written verdict)
7. On PASS: CLI Fable authors next prompt (or STOP queue) → CURRENT verify line
8. Warren decides: continue / merge / new chat handover
```

**Hard gate:** no next-unit implementation until CLI Fable writes a **PASS**. Warren may waive verify for a unit, but only in writing — record `Fable verify: WAIVED <YYYY-MM-DD>` in the CURRENT.md unit table. No verbal waivers.

---

## Step 0 — Sync pin (kills silent drift)

Before every browser-Fable design session, paste:

```
Branch: <git branch --show-current>
HEAD: <git rev-parse --short HEAD>
git log --oneline -3
git status -sb
Alembic code head: <from CURRENT.md>
Alembic DB (cip): <from CURRENT.md>
Pushed? yes/no — GitHub must match what we discuss
Next candidate: <BACKLOG-ID or unit name>
```

Browser Fable sees **GitHub**, not an unpushed working tree. If Cursor has not pushed, say so explicitly.

---

## Step 1 — Scope lock (interview is optional)

| Situation | Browser Fable does |
|-----------|-------------------|
| Greenfield / mushy problem | Full interview → then prompt |
| BACKLOG entry already complete (traps, retain, out-of-scope written) | **Short scope lock only:** unit split, sources in v1, merge posture, open gates (e.g. unapplied migration). Do **not** re-interview the whole idea. |
| Large effort | Prefer **split into 2–3 Cursor units** over one mega-prompt |

Never paraphrase away BACKLOG **Regression traps** / **Out of scope** — copy them into the unit prompt verbatim.

---

## Unit prompt skeleton (every Cursor paste)

1. **Context / HEAD pin** — branch base tip, Alembic code vs DB, standing rules  
2. **Goal** — one sentence product outcome  
3. **What the work is** — scoped bullets  
4. **Regression traps** — from BACKLOG/spec, verbatim  
5. **Behavior to retain**  
6. **Out of scope**  
7. **Done-when** — tests, SELECT-only printout, CURRENT/CONTEXT, report path, STOP for Fable verify  

Standing rules (always include unless Warren waives in writing):

- Spec / BACKLOG entry read-only unless Warren says edit  
- No cip writes without Warren approval (SELECT-only OK)  
- No alembic upgrade without Warren; author migration only after Phase A proves need + STOP before apply  
- `ALLOW_TESTS_ON_DEV_DB` unset  
- Explicit `git add <paths>` — never `-A` / `.`  
- FLAG ≠ BLOCK where domain requires  
- New feature branch per unit off stated tip  

---

## Cursor implementer bar

1. Phase A discovery: quote real code; PROCEED/STOP per item **before** edits  
2. One fix/architecture direction — no patch stacks on the wrong path  
3. Premium quality: correct contracts, idempotent writes, explainability, no silent auto-create of masters  
4. Tests for what changed; ALLOW unset  
5. SELECT-only cip validation when data-touching; print `current_database()=cip` first  
6. Update `docs/memory/CURRENT.md` + one `CONTEXT.md` changelog line  
7. Report → `.tmp/<unit>_cursor_report.md`  
8. Push before claiming GitHub-visible  

---

## CLI Fable verify bar

Invoke:

```powershell
Get-Content .tmp\<unit>_fable_seed.md -Raw |
  claude -p --model fable --output-format text --dangerously-skip-permissions |
  Out-File .tmp\<unit>_fable_response.md -Encoding utf8
```

Run from the **repo root** so CLI Fable can read files and git history itself — the report is a claim; the repo is the evidence.

Seed must include: branch, commit hash, pushed y/n, Phase A summary, scope status, verbatim SELECT printout, test counts, standing-rules affirmation, path to full report. Seed must also state: **read-only verify — no file edits, no migrations, verdict only.**

**Verdict format:** line 1 of the response must be `VERDICT: PASS` or `VERDICT: STOP` — greppable, never buried in prose.

**PASS** only if independently checked (not honor-system): spec/BACKLOG untouched as required, no unexpected migrations, tests claim plausible, cip evidence SELECT-only, non-goals untouched.

On PASS: author **next** Cursor prompt (or state queue empty).  
On STOP: defects only — do not author next prompt.

After verify, Cursor (or Warren) records in CURRENT.md unit table:

`Fable verify: PASS <YYYY-MM-DD> · next: <unit or none>` (or `STOP` / `WAIVED`)

---

## Artifacts (per unit)

| File | Owner |
|------|--------|
| `.tmp/<unit>_cursor_prompt.md` | Browser Fable / paste |
| `.tmp/<unit>_cursor_report.md` | Cursor |
| `.tmp/<unit>_fable_seed.md` | Cursor |
| `.tmp/<unit>_fable_response.md` | CLI Fable |
| `docs/memory/CURRENT.md` | Cursor after unit + after verify line |
| `CONTEXT.md` changelog line | Cursor |

`.tmp/` is working transcript — never committed; not a substitute for this doc or CURRENT.md.

---

## Skills / rules (deferred)

- **This doc first** — shared by all three agents.  
- **Cursor skill later** — after ≥2 more units (e.g. BACKLOG-072 + 061) under this doc; extract only mechanical kickoff/handoff that repeated verbatim.  
- **Do not** put judgment (interview quality, “is it done?”) into a skill.  
- Always-on `.cursor/rules` stay for architecture/safety; do not duplicate this whole loop into an always-on rule.

---

## Handover / new chat

When context is long or theme changes:

```
Run cip-session-handover
Branch: <name> @ <short SHA>
Next: <unit from CURRENT>
Skip: <do not re-audit>
Workflow: docs/WORKFLOW_DUAL_AGENT.md
```

---

## Related

- `docs/memory/CURRENT.md` — now  
- `docs/BACKLOG.md` — deferred + TRIGGER  
- `docs/memory/MEMORY_PALACE.md` — read order  
- `CONTEXT.md` — changelog  
- `.cursor/skills/cip-session-handover` — orient new chat  
