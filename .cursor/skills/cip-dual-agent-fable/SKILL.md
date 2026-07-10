---
name: cip-dual-agent-fable
description: >-
  CIP entry point for the Cursor ↔ CLI Fable dual-agent loop. Use when Warren
  says Fable, dual-agent, consult, interview, verify unit, or multi-unit CIP
  work. Loads personal skill dual-agent-fable plus CIP overlay
  docs/WORKFLOW_DUAL_AGENT.md.
---

# CIP Dual-agent Fable

1. **Read first:** personal skill `dual-agent-fable`  
   (`~/.cursor/skills/dual-agent-fable/SKILL.md`).
2. **Then apply CIP overlay:** `docs/WORKFLOW_DUAL_AGENT.md` + `docs/memory/CURRENT.md`.
3. **Default mode for mushy product work:** CONSULT in this chat (CLI Fable interview) — not browser Claude.
4. **After a unit ships:** VERIFY before starting the next unit.

New chat starter:

```
Run cip-session-handover
Run cip-dual-agent-fable
Branch: <from CURRENT>
Next: <from CURRENT>
Skip: <do not re-audit>
Mode: CONSULT
```
