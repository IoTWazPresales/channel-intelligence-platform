# Dual-agent workflow — CIP overlay (Cursor ↔ CLI Opus | Fable)

**Purpose:** Channel Intelligence Platform standing rules for the dual-agent loop.  
**Operational skill (any app):** `~/.cursor/skills/dual-agent-fable` — run `dual-agent-fable` or `cip-dual-agent-fable`.  
**Status:** Active · 2026-07-20  

**Consultant default: Opus.** Use Fable when Warren names Fable, or to finish an in-flight Fable VERIFY chain. Cursor states `Consultant: Opus|Fable` in every sync pin.

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
7. **VERIFY walks the contract, not the prompt.** For steward/import units the
   verifier iterates S1–S14 against the shipped tree regardless of what the unit
   prompt's own checklist contains. REQUIRED row absent/PARTIAL without a waiver
   line → `VERDICT: STOP`, naming the row.

**VERIFY must STOP when:** the unit prompt named a canonical (e.g. `DsiImportJobResolutionSection` / shipment resolution section / `dsi-progress` poll) and the shipped UI/API does not match that experience — even if tests are green and shared components are imported.

Record waivers only as `Fable verify: WAIVED <YYYY-MM-DD>` (or Opus) in `CURRENT.md` with Warren’s written OK.

## Product / architecture bar (CONSULT + IMPLEMENT) — locked 2026-07-16

**Never default to thin, lazy, or “smallest diff.”** That bias is **forbidden** in this workflow. It is not in any CIP rule, skill, or standing instruction.

Standing engineering bar (also in Cursor user rules):

- **Best practice is the default**, not an upgrade.
- **Always propose the better path — not the quicker or safer one.**
- **Patches are a last resort** — only when the problem is local and the fix creates no debt.

### CONSULT must

1. State the **operator experience** in one sentence before any unit plan.
2. Ask: **does this pattern already exist at another grain** (sheet / file / job / distributor / importer)? If yes → **generalise that pattern** — do not invent a weaker parallel UX or write path.
3. Recommend the **best product/architecture** that preserves governance (steward, no auto-create dims, FLAG≠BLOCK where required, idempotent apply).
4. Mention a thinner alternative **only to reject it**, with why — never as the recommended READY path.
5. If the plan requires N steward/mapping sessions for the **same layout**, justify that or reject it.

### Cursor must

- Seed CONSULT with the bar above (copy into every mushy CONSULT seed).
- **Refuse** consultant READY that picks “thin queue / hop between jobs / chrome patch” when a correct unified architecture is available and governance-safe.
- On Human challenge: re-CONSULT — do not defend the thin plan by default.

**Incident that locked this:** DSI multi-file — first Fable READY kept one-job-per-file + “Next job”; Human correctly required unified multi-file job (extend multi-sheet union). Thin was consultant risk-bias + bad seed framing, not documented policy.

---

## Roles (fixed)

| Role | Where | Owns | Must not |
|------|--------|------|----------|
| **Warren** | Human | Priorities, merge/promote, cip writes, alembic upgrade approval | — |
| **Cursor** | This IDE | Phase A → implement → tests → SELECT-only validate → CURRENT/CONTEXT → commit/push → seed consultant | Start next unit before PASS; apply alembic without Warren; `git add -A`; half-parity PASS |
| **CLI consultant** | `claude -p --model opus` (default) or `--model fable` | CONSULT (interview/scope/prompt), VERIFY (PASS/STOP) | Edit files during consult/verify; run migrations; invent schema against locked specs; PASS a thin mount when clone bar was locked |

**Browser Claude / claude.ai project chat is retired for this loop.** Interviews run in the Cursor chat via CLI consultant. Warren stays in one thread.

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
0. Sync pin (Cursor) — include Consultant: Opus|Fable
1. CONSULT (CLI Opus default) — interview if mushy; short scope lock if BACKLOG complete
2. Unit prompt → Warren skims → Cursor IMPLEMENT
3. Cursor: tests → CURRENT/CONTEXT → explicit git add → commit → push → report
4. VERIFY (same consultant family) → VERDICT: PASS | STOP
5. On PASS: next prompt or queue empty; on STOP: fix and re-verify
```

**Hard gate:** no next-unit implementation until consultant writes **`VERDICT: PASS`**.  
Warren may waive in writing only — record `<Opus|Fable> verify: WAIVED <YYYY-MM-DD>` in CURRENT.md.

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

| Situation | CONSULT does |
|-----------|----------------|
| Greenfield / mushy | Interview (max 5 questions/round) → READY with **best-path** unit prompt (see product bar above) |
| BACKLOG entry complete | Short scope lock only — do not re-interview the whole idea |
| Large effort | Prefer split into 2–4 Cursor units **along the best architecture**, not along the smallest patch |

Copy BACKLOG **Regression traps** / **Out of scope** into the unit prompt verbatim.

**Contract scoping (steward/import surfaces):** CONSULT must enumerate the
S-rows of `docs/STEWARD_EXPERIENCE_CONTRACT.md` in the unit prompt. Rows not
listed are in scope by default. A row may be excluded ONLY by a verbatim line
`Warren waived S<id> <date>: <reason>` written by Warren. CONSULT proposing a
reduced scope ("lean", "chrome-only", "defer intelligence") without waiver lines
is a defective prompt — Cursor must bounce it back, not implement it.

---

## Artifacts

| File | Owner |
|------|--------|
| `.tmp/<topic>_consult_<opus\|fable>_*.md` | Cursor / CLI consultant |
| `.tmp/<unit>_cursor_prompt.md` | Consultant (CONSULT READY) |
| `.tmp/<unit>_cursor_report.md` | Cursor |
| `.tmp/<unit>_verify_<opus\|fable>_*.md` | Cursor / CLI consultant |
| `docs/memory/CURRENT.md` | Cursor after unit + verify line |
| `CONTEXT.md` changelog | Cursor |

CONSULT seeds are instantiated from `.cursor/templates/consult_seed_template.md`.
Cursor fills ONLY the marked fields. CONSULT must read
`docs/STEWARD_ENGINE_DECISIONS.md` (all entries) before scoping any steward/import
unit; a proposal that contradicts a locked decision without citing and
superseding it is a defective prompt.

VERIFY seeds are instantiated from `.cursor/templates/verify_seed_template.md`.
Cursor fills ONLY the marked fields (branch, commit, unit id, changed paths,
waiver lines copied verbatim from the unit prompt). Cursor does not author
free-form verify framing.

`.tmp/` is never committed. Legacy `*_fable_*` names OK when Consultant is Fable.

---

## Invoke (repo root, PowerShell)

**Opus (default):**

```powershell
Get-Content .tmp\<name>_consult_opus_seed.md -Raw |
  claude -p --model opus --output-format text --dangerously-skip-permissions |
  Out-File .tmp\<name>_consult_opus_response.md -Encoding utf8
```

**Fable:**

```powershell
Get-Content .tmp\<name>_consult_fable_seed.md -Raw |
  claude -p --model fable --output-format text --dangerously-skip-permissions |
  Out-File .tmp\<name>_consult_fable_response.md -Encoding utf8
```

---

## Handover / new chat

```
Run cip-session-handover
Run cip-dual-agent-fable
Branch: <name> @ <short SHA>
Next: <unit from CURRENT>
Skip: <do not re-audit>
Consultant: Opus
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
