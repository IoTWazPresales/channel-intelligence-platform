# Dual-agent workflow — CIP overlay (Cursor ↔ CLI Fable)

**Purpose:** Channel Intelligence Platform standing rules for the dual-agent loop.  
**Operational skill (any app):** `~/.cursor/skills/dual-agent-fable` — run `dual-agent-fable` or `cip-dual-agent-fable`.  
**Status:** Active · 2026-07-20  

**Do not put here:** current branch, HEAD, job IDs, Alembic tip — those live in `docs/memory/CURRENT.md`.

---

## Quality bar (non-negotiable — Warren 2026-07-20 / hardened 2026-07-22)

Optimize for **UX, design, architecture, scalability, flexibility, best business practice, best solution, best intelligence, and best-in-market** — never for speed or “smallest diff.”

| Rule | Meaning |
|------|---------|
| **Canonical clone or STOP** | When a feature has a living reference (DSI steward, shipment apply, Import Centre progress, etc.), Cursor must **clone that behaviour and operator experience**, not merely import a shared primitive. Naming the shared file is not done. |
| **No half-PASS** | Thin mounts, stub wizards, sync-only paths where the bar is async+progress, missing tabs/bulk/debounce/error summaries — **incomplete unit**. Do not claim PASS; do not start the next unit. |
| **Never skim** | Double- and triple-check against the named canonical files before shipping. Side-by-side the operator path (upload → map → validate → steward → apply → progress). |
| **Own surface ≠ weaker UX** | Own route/CTA only. Same steward/apply/progress bar as the canonical importer. |
| **Code is evidence; docs are claims** | `CURRENT.md`, BACKLOG “Done”, commit messages, ROADMAP, and “parity” prose are **claims**. Confirmation and audit must prove the claim in the **running tree** (section files, props filled, API shape). A document saying it is done does **not** make it done. |

### Confirmation / audit discipline (Warren 2026-07-22)

Before Cursor claims “done,” “parity,” “shipped,” or “PASS-ready”:

1. **Open both sides** — named canonical section (e.g. `DsiImportJobResolutionSection`) and the target section. Compare slot-by-slot: viewport shell, entity tabs, filters (chips vs TextField), columns density, drawer chrome + body richness, plan toolbar, bulk, progress poll.
2. **Filled experience, not imports** — `import { ImportStewardCandidateWorkspace }` is not evidence. What was passed into `columns` / `filtersSlot` / `drawer` is evidence.
3. **Do not trust paper** — if BACKLOG/CURRENT/commit says complete and the section is thin, report **incomplete** and keep/restore the backlog item. Never remove a backlog entry on doc status alone.
4. **No screenshot requirement** — attention to code structure and props is enough; do not substitute screenshots for reading the tree.
5. **Cursor must not self-PASS** — after a clone/parity unit, seed CLI Opus/Fable VERIFY. Only `VERDICT: PASS` closes the unit.
6. **Verifier re-reads, does not trust the table** — CLI VERIFY opens each cited `path:line` itself and compares canonical→shipped values; Cursor’s filled checklist is a claim under test, not evidence. Unlocatable or PARTIAL slot on a locked bar → STOP.

**VERIFY must STOP when:** the unit prompt named a canonical (e.g. `DsiImportJobResolutionSection` / shipment resolution section / `dsi-progress` poll) and the shipped UI/API does not match that experience — even if tests are green and shared components are imported.

Record waivers only as `Fable verify: WAIVED <YYYY-MM-DD>` (or Opus) in `CURRENT.md` with Warren’s written OK.

---

## Roles (fixed)

| Role | Where | Owns | Must not |
|------|--------|------|----------|
| **Warren** | Human | Priorities, merge/promote, cip writes, alembic upgrade approval | — |
| **Cursor** | This IDE | Phase A → implement → tests → SELECT-only validate → CURRENT/CONTEXT → commit/push → seed Fable | Start next unit before PASS; apply alembic without Warren; `git add -A`; half-parity PASS |
| **CLI Fable** | `claude -p --model fable` | CONSULT (interview/scope/prompt), VERIFY (PASS/STOP) | Edit files during consult/verify; run migrations; invent schema against locked specs; PASS a thin mount when clone bar was locked |

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

**Unit prompts must name the clone target file(s)** when parity applies (e.g. “clone `ShipmentImportJobResolutionSection` behaviour”). Keyword-only (“use shared workspace”) is insufficient.

---

## CIP standing rules (always unless Warren waives in writing)

- Spec / BACKLOG entry read-only unless Warren says edit
- No cip writes without Warren approval (SELECT-only OK)
- No alembic upgrade without Warren; author migration only after Phase A proves need + STOP before apply
- `ALLOW_TESTS_ON_DEV_DB` unset for normal unit tests
- Explicit `git add <paths>` — never `-A` / `.`
- FLAG ≠ BLOCK where domain requires
- Never auto-create `dim_product` / `dim_customer` / `dim_distributor` from import evidence
- Import / steward / apply work: obey `.cursor/rules/import-parity.mdc` at the **DSI/shipment experience bar**, not checkbox imports of shared files

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
- `.cursor/rules/import-parity.mdc` — importer experience bar
- `.cursor/skills/cip-session-handover` — orient new chat
