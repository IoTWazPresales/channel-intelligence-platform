---
eif: autonomy-policy
version: 0.3
status: accepted
last_updated: '2026-08-22'
owner: Warren
review_after: 30d
project_id: channel-intelligence-platform
policy_id: AUTONOMY-001
runtime_mode: local
max_authority: L3
max_risk_without_escalation: R3
observation_paths:
- '**'
change_paths:
- apps/api/**
- apps/web/**
- docs/**
artifact_paths:
- .eif/audit/**
adjacent_scope:
  mode: none
  paths: []
action_classes:
  read: true
  write: true
  artifact_write: true
  delete: true
  remote_push: false
  force_vcs: false
  identity_mutation: false
  destructive_data: false
  infrastructure_control: false
  control_plane_change: false
  release: false
shell:
  mode: workspace
mcp:
  browser: interact
  tools: []
network:
  classes:
  - loopback
  - public_read
  destinations: []
secrets:
  mode: none
  names: []
budgets:
  tool_calls: 500
  wall_clock_minutes: 120
  debug_iterations: 10
  improvement_items: 0
---

> **Authoritative policy:** the YAML front matter above is machine-readable and is the only policy input compiled into runtime enforcement. The body is explanatory and must not duplicate competing values.

# Autonomy Policy

This policy is an **accepted authority envelope**, not an agent personality setting. `proposed` policy does not grant additional authority. Change the YAML, review it, mark it `accepted`, then regenerate the runtime policy with `tools/compile_policy.py`.

The product pair is **L1** (audit/recommend) and **L3** (implement and validate inside the accepted development workspace). Compile maps `L2`→`L1` and `L4`→`L3`. `L5` stays disabled unless a separate environment policy exists.

File, write, artifact, and delete classes are derived from `max_authority` plus explicit `change_paths` / `artifact_paths`. Hard-deny classes (`remote_push`, `force_vcs`, `identity_mutation`, `destructive_data`, `infrastructure_control`, `control_plane_change`, `release`) stay false unless explicitly granted. Do not restore exact-command shell allowlists, `require_sandbox` as an admission gate, or `mcp_read` / `mcp_write` / `test` / `commit` operator toggles.

## Shell

```yaml
shell:
  mode: deny        # L1
# mode: workspace   # L3 ordinary repo engineering
```

`deny` blocks shell. `workspace` allows ordinary local engineering (tests, builds, local commits, local lockfile installs) and still denies high-consequence classes: remote push, force VCS, identity mutation, destructive data, infrastructure control, `git clone`, global install, and package publish.

Workspace shell is **not a jail**. File-tool path checks may be ENFORCED. Arbitrary child processes launched through unsandboxed host shell are ordinary local-developer execution; project-boundary claims for those children are UNAVAILABLE. High-consequence classifiers are defense-in-depth, not process containment. Sandbox true/false is telemetry. It must not block L3. Do not add `compensating_sandbox`: compile and the guard reject it. A host process or policy label is not isolation and must not mint `COMPENSATING`.

## MCP and network destination classes

```yaml
mcp:
  tools:
    - tool_pattern: 'browser_navigate'
      server_pattern: '*'
network:
  classes:
    - loopback
    - public_read
  destinations: []
```

MCP is default deny. Grant tools by name/pattern. The MCP server `url` is identity, not a user destination. Granted tools inherit destination classes:

- `loopback` — local UI (`http://127.0.0.1`, `localhost`)
- `public_read` — ordinary HTTPS/HTTP research (docs/search GET-shaped traffic). This is not a cloud-mutate grant.
- `destinations` — optional extra explicit hosts

`about:blank` is not HTTP egress. Destructive MCP payloads stay denied unless `destructive_data` is granted. Do not add a parallel `public_web` class.

## Observation vs change paths

`observation_paths` controls where EIF may inspect/read inside the accepted project boundary. `change_paths` controls where implementation writes may occur. `artifact_paths` / `artifact_write` is a separate opt-in for durable Audit Mode files. Observation scope may be broader; it never authorizes writes. Implementation write never implies artifact write, and artifact write never implies implementation write.

Default L1 remains strictly read-only: `write: false`, `artifact_write: false`, `change_paths: []`, `artifact_paths: []`.

Audit Mode keeps **implementation** change scope at `NONE`. Durable mockups/reports are not application `change_paths`. A recommended opt-in L1 audit envelope (install with `--audit-artifacts`, or set the YAML below and recompile):

```yaml
max_authority: L1
observation_paths:
  - '**'
change_paths: []
artifact_paths:
  - '.eif/audit/**'
action_classes:
  read: true
  write: false
  artifact_write: true
```

Do not grant `write: true` with `.eif/**` for audits. That envelope is invalid: it is not limited to `.eif/audit/**` and would treat canonical `.eif` state as implementation change scope. Canonical files such as `.eif/CONTEXT.md`, `.eif/DECISIONS.md` and `.eif/RUNTIME_CAPABILITIES.md` remain unwritable under artifact authority. Product trees (`src/**`, `apps/**`, `tests/**`, `docs/**`, `migrations/**`, `.cursor/**`) remain denied.

Chat-only L0/L1 audits may keep `artifact_write: false`; the Volume 25 intelligence bar still applies to the conversation output. Missing artifact grant means `UNABLE_TO_PROTOTYPE` / chat-only reports, not product writes.

For L3, `change_paths` must be explicit before product-source writes are granted. Adjacent-scope paths are separate and still require the necessary external change test in Constitution §0.5.

## Policy lifecycle

1. Draft/modify this file.
2. Have the appropriate owner accept it.
3. Run `tools/compile_policy.py`.
4. Run the runtime probe in the same Cursor mode that will execute the work.
5. Grant only authority supported by the **measured** `RUNTIME_CAPABILITIES.md`. Sandbox UNAVAILABLE does not block L3.
