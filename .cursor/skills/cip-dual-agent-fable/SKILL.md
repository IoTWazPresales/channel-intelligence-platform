---
name: cip-dual-agent-fable
description: >-
  CIP entry point for the Cursor ↔ CLI Fable dual-agent loop. Use when Warren
  says Fable, Opus, dual-agent, consult, interview, verify unit, or multi-unit
  CIP work. Loads personal skill dual-agent-fable plus CIP overlay
  docs/WORKFLOW_DUAL_AGENT.md.
---

# CIP Dual-agent Fable

1. **Read first:** personal skill `dual-agent-fable`
   (`~/.cursor/skills/dual-agent-fable/SKILL.md`).
2. **Then apply CIP overlay:** `docs/WORKFLOW_DUAL_AGENT.md` + `docs/memory/CURRENT.md`.
3. **Default mode for mushy product work:** CONSULT in this chat (CLI Fable interview) — not browser Claude.
4. **After a unit ships:** VERIFY before starting the next unit.

## Quality bar (always)

- Optimize for UX / architecture / best-in-market — **never** for speed or smallest diff.
- **Canonical clone or STOP** — if a living reference exists (DSI steward, shipment apply, progress poll), clone that operator experience. Importing a shared primitive without the section behaviour is **not done**.
- **No half-PASS** — thin mounts, stub wizards, missing async/progress when the bar requires them → incomplete; VERIFY must **STOP**.
- **Never skim** — double- and triple-check against named canonical files before claiming ship.
- **Own surface ≠ weaker UX** — different route/CTA only.
- **Code is evidence; docs are claims** — CURRENT/BACKLOG/commits saying “done” or “parity” are claims. Confirm in the tree (filled props / section shape vs canonical). Do not self-PASS; seed VERIFY.

## Confirmation before claim (Cursor)

When the unit touches steward/import UX, Cursor’s report must list a **comparative slot checklist** (canonical → shipped + path:line) vs the named canonical (viewport shell · entity tabs · filters · columns · drawer chrome · drawer body · plan/bulk · progress). Missing or PARTIAL slots → do not claim done; do not ask VERIFY for PASS. VERIFY independently re-reads each cited path — the filled table is a claim, not proof.

New chat starter:

```
Run cip-session-handover
Run cip-dual-agent-fable
Branch: <from CURRENT>
Next: <from CURRENT>
Skip: <do not re-audit>
Mode: CONSULT
```
