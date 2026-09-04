CONSULT: READY

`OBSERVATION_TRANSPORT: deny_crash` ÔÇö and **argv/event-name on the launcher IS required before `allow_crash` is lawful for any event.**

**Operator experience:** On a corrupted or empty payload the agent sees a distinct `HOOK_INPUT_INVALID` / `eif_guard_class=crash` deny ÔÇö never a policy verdict ÔÇö so a transport failure reads as "the guard couldn't hear the request," not "the file was foreign/secret/sensitive."

## Locked decision

Keep the current behavior: unparseable **or** path-less stdin resolves to `deny('HOOK_INPUT_INVALID')` with `eif_guard_class=crash`. Do not flip observation hooks to `allow_crash` today, because **today the guard cannot know it is on an observation hook.** The event name lives *inside* the payload that failed to parse. You cannot scope an allow to observation using the very bytes you couldn't read. A "scoped allow" that infers its own scope from a corrupted payload is not scoped ÔÇö it is a global allow-on-unparseable wearing an observation label.

That global allow-on-unparseable would fail-open `beforeReadFile`, `beforeShellExecution`, and `preToolUse` writes on any truncation or zero-byte read ÔÇö the exact enforcement gates `FAILCLOSED_BEFORE_READ: keep_true` was set to hold shut. So the decision is forced: **deny_crash until event identity arrives out of band.**

`allow_crash` becomes the *better* architecture ÔÇö but only after the launcher (argv or `hooks.json` wiring) tells the guard its event name before stdin is read. Then a genuine observation/after-event hook, whose payload happens to arrive empty, can allow-with-crash-metadata (the observed action already occurred; denying it only drops telemetry and blocks a non-blocking event), while `beforeReadFile` / `beforeShellExecution` / write gates keep denying-on-crash regardless of stdin. That is the path to build toward: **move event identity off stdin and onto the launcher, then split the crash verdict by event class.** Until that lands, deny_crash is the only lawful answer for *all* unparseable/path-less input.

## Thinner alternatives ÔÇö rejected

- **`beforeReadFile failClosed:false`** ÔÇö REJECTED. This is trading a transport-boundary decision for a policy-boundary hole. It would let a mute or crash open `SENSITIVE_READ` / `SECRET_IN_READ` / `FOREIGN_READ` on genuinely unknown paths. Prior `keep_true` stands and is orthogonal to this consult.
- **Treat empty stdin as `IDENTITY_TOOL`** ÔÇö REJECTED. It collapses crash into policy and destroys the required crash-vs-policy distinguishability. A transport failure must never surface as an identity/foreign/sensitive verdict. `HOOK_INPUT_INVALID` + `eif_guard_class=crash` stays its own class.
- **Fail-open all hook events on unparseable stdin** ÔÇö REJECTED. Same failure as the global allow above: it opens the write and shell-execute gates, not just observation. Unacceptable while enforcement identity is unavailable out of band.

## Why deny is safer even with "no path to leak"

The operator's premise ÔÇö "a path-less payload has nothing in the JSON to leak" ÔÇö confuses the guard's *visibility* with the filesystem's *exposure*. Cursor still holds the real path and will still perform the read; our copy arriving empty or truncated does not cancel the read, it only blinds the gate meant to stop it. On a fail-closed read hook the guard's job is to **deny the read before it happens**, so allowing-on-crash lets an unguarded read proceed precisely when we have the least information about it. Absence of a path in a corrupted payload is absence of *evidence*, not evidence of *absence of a target* ÔÇö and on a fail-closed boundary that must resolve to deny. "No path in our copy" is not "no file will be read," so deny_crash is the correct safety-boundary resolution until the launcher can prove, out of band, that the event carries no gate to hold shut.

*(Guard-only. No unit prompt. The separate concurrent-Read `IDENTITY_TOOL path:null` symptom is not folded into this verdict ÔÇö it is a preToolUse identity-ordering issue to be matched to the existing `beforeReadFile` identity-skip, and does not alter deny_crash.)*
