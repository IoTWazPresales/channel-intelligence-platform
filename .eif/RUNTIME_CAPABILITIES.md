---
eif: runtime-capabilities
version: 0.3
status: unverified
last_updated: null
owner: null
review_after: runtime-change
project_id: channel-intelligence-platform
runtime: cursor
runtime_version: null
mode: local
observed_at: null
probe_run_id: null
probe_evidence_path: null
hook_config_sha256: null
guard_sha256: null
launcher_sha256: null
runtime_policy_sha256: null
probe_result: null
probes_passed: null
probes_total: null
---

# Runtime Capability / Enforcement Report

> **Measured artifact:** do not mark a control `ENFORCED` because a hook/configuration exists. `ENFORCED` requires an observed control event from the same runtime, version and mode, produced by a **complete passing** `runtime_probe.py` run. Generate/refresh this report through `tools/runtime_probe.py` and retain the underlying observations.
>
> **Freshness is not proof.** `verify` reporting CURRENT means the bound hook/config/launcher/policy hashes, runtime, and mode still match. It does not mean mandatory probes passed. `verify` exits nonzero when the report is STALE, incomplete, or any mandatory probe failed. ENFORCED rows are not written from a failed or incomplete run.

| Control | Status | Observed evidence | Compensating control / limitation |
|---|---|---|---|
| Project identity before state-changing action | UNVERIFIED | | |
| Project-boundary read guard | UNVERIFIED | | |
| Pre-tool state-change blocking | UNVERIFIED | | |
| Shell high-consequence / workspace | UNVERIFIED | | L1 denies shell. L3 workspace allows ordinary repo commands. High-consequence classifiers are defense-in-depth, not process containment. |
| Shell process containment | UNAVAILABLE | | Telemetry only. File-tool path checks may be ENFORCED; unsandboxed child processes are not contained. Does not block L3. compensating_sandbox never mints COMPENSATING. |
| File-write/path guard | UNVERIFIED | | |
| Pre-write secret scan | UNVERIFIED | | |
| MCP execution guard | UNVERIFIED | | Default deny. mcp.browser observe/interact is a family grant. public_read is not a UI-mutate grant. Aimed destinations and harvested page origin may be ENFORCED; this row is not Chromium containment. |
| Browser first-gesture / Chromium egress | UNAVAILABLE | | First in-page gesture is not classifiable at beforeMCPExecution. App-initiated XHR and Chromium process network are not EIF-firewalled. Do not mint ENFORCED from last-loopback navigate. |
| Network policy | UNVERIFIED | | Destination classes on MCP tool input and harvested page origin. public_read is ordinary HTTPS research, not a cloud-mutate grant or a Chromium firewall. |
| Credential scoping | UNVERIFIED | | |
| Tool-call / wall-clock budget | UNVERIFIED | | |
| Debug-iteration budget | ADVISORY | runtime has no direct EIF debug-iteration counter | model/process cap only |
| Evidence-pointer resolver | ADVISORY | | GOV-008 + validation tooling |
| Independent verifier separation | UNVERIFIED | | |
| Release mechanism restriction | UNAVAILABLE | | L5 disabled unless environment policy + runtime control exist |
| sessionStart identity block | UNAVAILABLE | Cursor sessionStart is fire-and-forget | actionable hooks re-check identity |
| Programme ledger file-tool deny | UNVERIFIED | | Requires same-mode probe that Write to `.eif/program/**` is denied |
| Child-process programme immutability | UNAVAILABLE | | Unsandboxed host children are ordinary processes. Never mark ENFORCED. Detect divergence with `program.py verify` |
| Generic-git remote identity | UNVERIFIED | | `python tools/platform_probe.py` |
| GitHub/GitLab/ADO/Bitbucket controls | UNAVAILABLE | | Adapter present; ENFORCED only after a same-mode probe of that host |
| CI workflow detect | UNVERIFIED | | Presence of CI config is detection, not enforcement |

A local capability report must not be reused for cloud, remote, sandboxed, CLI, or another Cursor version without re-probing. A change to the hook configuration, guard implementation, invoked platform launcher, or derived runtime policy invalidates this report even when the Cursor version is unchanged.
