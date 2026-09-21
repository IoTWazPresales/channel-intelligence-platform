---
eif: runtime-capabilities
version: 0.3
status: failed
last_updated: null
owner: null
review_after: runtime-change
project_id: channel-intelligence-platform
runtime: cursor
runtime_version: 2.1.278
mode: local
observed_at: '2026-09-21T15:17:31Z'
probe_run_id: R20260921170432_BDEF22
probe_evidence_path: .eif/runtime-probes/R20260921170432_BDEF22/observations.json
hook_config_sha256: d7d7c183e44342e4674a83e969a1d79400b3af2763fa1a352239afc2f7a58167
guard_sha256: 0da256940cd2e3a929fdd75f2f94935480c5805ea43f2bafd2f43e5a0f2bebcf
launcher_sha256: 0824e387321fb87d7400a4c77b1d5878b7a794648d34a2130fb47c411b05ff29
runtime_policy_sha256: a476389d5e57d007085c1cc3d4c546d01b456f479611cb80d3d097f559793af9
probe_result: failed
probes_passed: 0
probes_total: 14
---

# Runtime Capability / Enforcement Report

> **Measured artifact.** ENFORCED means the named control was observed through actual Cursor hook invocation with the recorded guard/config/policy hashes in this runtime/mode. Offline guard tests alone do not qualify.
>
> **Freshness is not proof.** `runtime_probe.py verify` reports CURRENT when hashes/runtime/mode still match. PASSED requires every mandatory probe in this run to succeed. A CURRENT+failed run must not be treated as capability evidence. ENFORCED rows are written only from a complete passing run.

| Control | Status | Observed evidence | Compensating control / limitation |
|---|---|---|---|
| Project identity before state-changing action | UNVERIFIED | `.eif/runtime-probes/R20260921170432_BDEF22/observations.json` |  |
| Project-boundary read guard | UNVERIFIED | `.eif/runtime-probes/R20260921170432_BDEF22/observations.json` |  |
| Pre-tool state-change blocking | UNVERIFIED | `.eif/runtime-probes/R20260921170432_BDEF22/observations.json` |  |
| Shell high-consequence / workspace | UNVERIFIED | `.eif/runtime-probes/R20260921170432_BDEF22/observations.json` | L1 denies shell. L3 workspace allows ordinary repo commands. High-consequence classifiers are defense-in-depth, not process containment. SHELL_COMPENSATING_SANDBOX is not an allow. |
| Shell process containment | UNAVAILABLE |  | Telemetry only. File-tool path checks may be ENFORCED; arbitrary child processes launched through workspace shell are not contained. UNAVAILABLE on unsandboxed hosts. Does not block L3. compensating_sandbox never mints COMPENSATING. |
| File-write/path guard | UNVERIFIED | `.eif/runtime-probes/R20260921170432_BDEF22/observations.json` |  |
| Pre-write secret scan | UNVERIFIED | `.eif/runtime-probes/R20260921170432_BDEF22/observations.json` |  |
| MCP execution guard | UNVERIFIED | `.eif/runtime-probes/R20260921170432_BDEF22/observations.json` | Requires observed allow of a granted MCP tool through Cursor, or deny of an ungranted tool. Policy JSON is not evidence. Family grant, aimed destinations, and harvested page-origin gating may be ENFORCED; first-gesture and Chromium egress are not this row. |
| Browser first-gesture / Chromium egress | UNAVAILABLE |  | UNAVAILABLE. First in-page gesture (click/link/form/`window.open`) is not classifiable at beforeMCPExecution. App-initiated XHR and Chromium process network are not EIF-firewalled. Aimed URL input and harvested page origin remain under mcp_guard/network. Do not mint ENFORCED from last-loopback navigate. |
| Network policy | UNVERIFIED | `.eif/runtime-probes/R20260921170432_BDEF22/observations.json` | High-consequence shell (ssh/push/infra) and destination classes on MCP tool input and harvested page origin. public_read allows ordinary HTTPS research; it is not a cloud-mutate grant or a Chromium firewall. |
| Credential scoping | UNVERIFIED |  |  |
| Tool-call / wall-clock budget | UNVERIFIED |  |  |
| Debug-iteration budget | ADVISORY |  | No Cursor event maps directly to EIF debug-hypothesis iterations. |
| Evidence-pointer resolver | ADVISORY |  | GOV-008 + deterministic resolver tooling; not a runtime action hook. |
| Independent verifier separation | UNVERIFIED | `.eif/runtime-probes/R20260921170432_BDEF22/observations.json` | Observed subagent lifecycle can support separation but does not itself prove independent verification. |
| Release mechanism restriction | UNAVAILABLE |  | L5 disabled unless separately proven. |
| sessionStart identity block | UNAVAILABLE |  | Cursor sessionStart is fire-and-forget and cannot be a blocking boundary. |
