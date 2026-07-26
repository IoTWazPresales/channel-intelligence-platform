# CONSULT seed — <UNIT_ID>

> Instantiate from this template. Cursor fills ONLY the marked fields. Cursor does
> not author framing, does not summarise the codebase in its own words, and does
> not propose the answer inside the seed.

Branch: <BRANCH> @ <SHORT_SHA> (pushed: <YES/NO>)
Alembic on cip: <REV>
Mode: CONSULT · Consultant: Opus
Prior unit + verdict: <PREV_UNIT> — <PASS/STOP>

## Mandatory reads (open these yourself; do not trust this seed's summary)

1. `docs/STEWARD_EXPERIENCE_CONTRACT.md` — current version `<CONTRACT_VERSION>`
2. `docs/STEWARD_ENGINE_DECISIONS.md` — **all** entries, especially any bearing on
   this unit
3. `docs/memory/CURRENT.md` — branch state, standing constraints
4. Canonical paths named below

## Unit under consideration

<UNIT_NAME_AND_ONE_LINE_GOAL>

Contract rows believed in scope: <S_ROWS>
Existing waivers carried in: <WAIVER_LINES_VERBATIM_OR_NONE>

## Evidence attached (claims, not proof)

- Discovery report: `<PATH>` — **this is Cursor's claim.** Open the files it cites
  and confirm at path:line before relying on any statement in it.
- Prior VERIFY response: `<PATH>`
- Relevant canonical paths: `<PATHS>`

## Your task

1. **Grade the discovery, don't accept it.** Confirm or challenge each proposed
   seam at path:line. State explicitly where the report is wrong or incomplete.
2. **Check every proposal against `STEWARD_ENGINE_DECISIONS.md`.** If a proposed
   seam contradicts a locked decision, reject it and cite the D-number. If you
   believe a locked decision should change, say so explicitly as a supersede
   proposal — never silently work around it.
3. **Apply the D-002 test** to every divergence between consumers: domain variance
   (compose it) vs capability gap (hold local, waive, schedule). Demand evidence —
   for a gap to be waived as "the consumer doesn't have this concept," the payload
   or service must be shown not to carry it.
4. **Scope only as a subset of contract rows.** You may not narrow the bar. Any row
   excluded needs a `Warren waived S<id> <date>: <reason>` line — you may *propose*
   one, you may not author it as decided.
5. **Refuse thin paths.** Proposing "lean", "chrome-only", "defer the intelligence",
   or a flag that makes a known gap a supported mode is a defective recommendation.
6. Output the Cursor unit prompt: hard constraints first, discovery gate (unless
   D-009 light-weight applies), baseline harness per D-007, phases, done-state
   checklist, non-goals, self-check, VERIFY rows.

## Deliverable format

Line 1 must be exactly one of:
- `CONSULT: NEED_HUMAN` — then at most 5 numbered questions, no essays. Use this
  for domain calls only Warren can make (e.g. "does this entity genuinely have no
  region concept, or is that a gap?").
- `CONSULT: READY` — then: locked decisions (with any new D-entries to append),
  rejected alternatives and why, then the full unit prompt.
- `CONSULT: STOP` — what is blocked and why.

Do not edit files. Advisory only.
