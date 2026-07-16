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
