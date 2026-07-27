---
name: cip-dual-agent-fable
description: >-
  CIP entry point for the Cursor ↔ CLI dual-agent loop (Opus default, Fable
  optional). Use when Warren says Fable, Opus, dual-agent, consult, interview,
  verify unit, or multi-unit CIP work. Loads personal skill dual-agent-fable
  plus CIP overlay docs/WORKFLOW_DUAL_AGENT.md.
---

# CIP Dual-agent (Opus | Fable)

1. **Read first:** personal skill `dual-agent-fable`
   (`~/.cursor/skills/dual-agent-fable/SKILL.md`).
2. **Then apply CIP overlay:** `docs/WORKFLOW_DUAL_AGENT.md` + `docs/memory/CURRENT.md`.
3. **Default consultant: Opus.** Use Fable when Warren names Fable or to finish an in-flight Fable VERIFY queue.
4. **Default mode for mushy product work:** CONSULT in this chat — not browser Claude.
5. **After a unit ships:** VERIFY (same consultant family) before starting the next unit.
6. **Product bar (locked 2026-07-16):** Never thin-default. Best path only — see
   `docs/WORKFLOW_DUAL_AGENT.md` § Product / architecture bar. Paste PRODUCT BAR into
   every mushy CONSULT seed. Refuse READY that picks hop-between-jobs / chrome patches
   when a unified architecture exists (e.g. DSI multi-file = extend multi-sheet union).

## Quality bar (always)

- Optimize for UX / architecture / best-in-market — **never** for speed or smallest diff.
- **Contract or STOP** — steward/import surfaces are graded against
  `docs/STEWARD_EXPERIENCE_CONTRACT.md` S-rows. Consume/extend the shared engine;
  never fork or copy-rename reference modules.
- **No half-PASS** — thin mounts, stub wizards, missing async/progress when the bar requires them → incomplete; VERIFY must **STOP**.
- **Never skim** — double- and triple-check against named canonical files before claiming ship.
- **Own surface ≠ weaker UX** — different route/CTA only.
- **Code is evidence; docs are claims** — CURRENT/BACKLOG/commits saying “done” or “parity” are claims. Confirm in the tree (filled props / section shape vs canonical). Do not self-PASS; seed VERIFY.

## Confirmation before claim (Cursor)

When the unit touches steward/import UX, the checklist IS the contract's S-rows; Cursor's report
lists S1–S14 with path:line; VERIFY re-walks them from the template seed. Missing or PARTIAL slots → do not claim done; do not ask VERIFY for PASS.

New chat starter:

```
Run cip-session-handover
Run cip-dual-agent-fable
Branch: <from CURRENT>
Next: <from CURRENT>
Skip: <do not re-audit>
Consultant: Opus
Mode: CONSULT
```
