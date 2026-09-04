ROLE: CLI Opus. CONSULT mode. Do NOT edit files. Do NOT migrate.

Context: CIP-owned Cursor hook guard at `.cursor/hooks/eif_guard.py` (do not touch `C:\AI\engineering-intelligence-framework`). Operator authorized a guard-only repair. Do not record D-0009. Do not start Promotions.

Sync pin: branch feat/ns-2-brief-nav-collapse · Consultant: Opus
Next: observation-hook transport-crash allow vs deny

Goal: one safety-boundary decision.

Question (verbatim from operator):
"When the guard receives an unparseable or path-less payload on an
observation hook, is denying safer than allowing, given that there is
no identifiable target to protect?"

Known so far:
- Live `hook-guard.log`: HOOK_INPUT_INVALID empty stdin; JSONDecodeError Unterminated string (e.g. line 1 col 49). stdout_wrote true. Inbound Cursor payload empty or truncated; outbound emit works.
- Parse failures already call deny('HOOK_INPUT_INVALID') with eif_guard_class=crash. prove_stdin.py does not cover zero-byte stdin or mid-string truncation.
- `beforeReadFile` failClosed:true was kept on prior CONSULT (FAILCLOSED_BEFORE_READ: keep_true) so a mute/crash cannot open SENSITIVE_READ / SECRET_IN_READ / FOREIGN_READ. That still stands for reads of *unknown paths*.
- Operator challenge: a payload with *no path at all* has nothing in the JSON to leak. Does deny still win?
- Counter-evidence the consultant must challenge: Cursor still knows the file it is about to read. The hook only failed to *receive* that path. Allowing on empty/truncated stdin skips SENSITIVE_READ/SECRET_IN_READ/FOREIGN_READ for that call even though Cursor will still perform the read. "No path in our copy" is not "no file will be read".
- Second counter: unparseable stdin does not identify the hook event. Allow-on-unparseable cannot be scoped to observation unless the launcher is told the event name out of band (argv/hooks.json). A global allow-on-unparseable would also fail-open beforeShellExecution / preToolUse writes.
- Separate live symptom (do not collapse into the stdin question): concurrent preToolUse Read/Grep at the same ts, one IDENTITY_TOOL deny with path:null, siblings TOOL_OK with real paths. Cause: identity_ok() runs before path is extracted; git snapshot can flake under hook burst. beforeReadFile already skips git-identity. This is not the CONSULT question; Cursor will skip identity on Read/Grep preToolUse to match beforeReadFile. Do not let that steal the verdict.

Constraints:
- Crash vs policy must stay distinguishable (HOOK_INPUT_INVALID + eif_guard_class=crash, never IDENTITY_TOOL / FOREIGN_READ / SENSITIVE_READ for unparseable or path-less payloads).
- Do not set beforeReadFile failClosed:false as a substitute for this decision (prior keep_true stands for unknown-path crashes).
- Do not edit C:\AI\engineering-intelligence-framework.
- CONTROL_PLANE_PROTECTED on hook source remains for unauthorized edits; this CONSULT does not grant product writes.

PRODUCT BAR (locked): Best practice is default. Propose the better path — not the
quicker or safer one. Patches are last resort. Never recommend a thin/lazy/smallest-diff
path when a stronger architecture exists and keeps governance. Ask: does this pattern
already exist at another grain (sheet/file/job/importer)? If yes, generalise it.
State operator experience in one sentence before unit plans. Thin alternatives only
to REJECT with why — never as the READY recommendation.

Deliverable:
1. Line 1: `CONSULT: NEED_HUMAN` | `CONSULT: READY` | `CONSULT: STOP`
2. If READY: locked decision in one of these exact tokens:
   `OBSERVATION_TRANSPORT: deny_crash`  (emit deny HOOK_INPUT_INVALID crash-class; tool does not proceed)
   `OBSERVATION_TRANSPORT: allow_crash` (emit allow with HOOK_INPUT_INVALID crash-class metadata; tool proceeds; agent still sees crash)
   plus whether argv/event-name on the launcher is required before allow_crash is lawful.
3. Explicitly reject the thinner alternatives (failClosed:false on beforeReadFile; treat empty stdin as IDENTITY_TOOL; fail-open all hook events).
4. One paragraph: why this is safer given Cursor still holds the real path when stdin is empty.
5. No unit prompt for product work. Guard-only.
