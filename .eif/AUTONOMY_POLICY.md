---
eif: autonomy-policy
version: 0.3
status: accepted
last_updated: '2026-08-30'
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
- CONTEXT.md
- AGENTS.md
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
  remote_push: true
  force_vcs: false
  identity_mutation: false
  destructive_data: false
  infrastructure_control: false
  control_plane_change: false
  release: false
shell:
  mode: workspace
mcp:
  profile: cursor-review
  browser: interact
  tools:
    - browser_*
network:
  classes:
  - loopback
  - public_read
  destinations: []
secrets:
  mode: none
  names: []
budgets:
  tool_calls: 3000
  wall_clock_minutes: 720
  debug_iterations: 30
  improvement_items: 0
  wrap_up_ratio: 0.85
  repeat_mutating_limit: 12
---

> **Authoritative policy:** the YAML front matter above is machine-readable and is the only policy input compiled into runtime enforcement. The body is explanatory and must not duplicate competing values.

# Autonomy Policy

This policy is an **accepted authority envelope**, not an agent personality setting. `proposed` policy does not grant additional authority. Change the YAML, review it, mark it `accepted`, then regenerate the runtime policy with `tools/compile_policy.py`.

The product pair is **L1** (audit/recommend) and **L3** (implement and validate inside the accepted development workspace). Compile maps `L2`â†’`L1` and `L4`â†’`L3`. `L5` stays disabled unless a separate environment policy exists.

File, write, artifact, and delete classes are derived from `max_authority` plus explicit `change_paths` / `artifact_paths`. Hard-deny classes (`remote_push`, `force_vcs`, `identity_mutation`, `destructive_data`, `infrastructure_control`, `control_plane_change`, `release`) stay false unless explicitly granted. Do not restore exact-command shell allowlists, `require_sandbox` as an admission gate, or `mcp_read` / `mcp_write` / `test` / `commit` operator toggles.

## Shell

```yaml
shell:
  mode: deny        # L1
# mode: workspace   # L3 ordinary repo engineering
```

`deny` blocks shell. `workspace` allows ordinary local engineering (tests, builds, local commits, local lockfile installs) and still denies high-consequence classes: remote push, force VCS, identity mutation, destructive data, infrastructure control, `git clone`, global install, and package publish.

Workspace shell is **not a jail**. File-tool path checks may be ENFORCED. Arbitrary child processes launched through unsandboxed host shell are ordinary local-developer execution; project-boundary claims for those children are UNAVAILABLE. High-consequence classifiers are defense-in-depth, not process containment. Sandbox true/false is telemetry. It must not block L3. Do not add `compensating_sandbox`: compile and the guard reject it. A host process or policy label is not isolation and must not mint `COMPENSATING`.

## MCP, browser interaction, and network destination classes

```yaml
mcp:
  browser: interact          # none | observe | interact
  tools: []              # non-browser MCP (postgres, etc.)
network:
  classes: []            # L1 default
# - loopback             # local rendered app
# - public_read          # HTTPS research; not a UI-mutate grant
  destinations: []
```

MCP is default deny. Non-browser tools are still granted by name/pattern. Browser is a **family**, not a lagging named-tool list:

- `none` â€” no browser family. A nameless `browser_*` glob is a compile error. Named tools such as `browser_navigate` remain valid and do not imply click/type/fill.
- `observe` â€” navigate, snapshot, screenshot, console/network logs, wait, resize, navigate_back. In-page use (click, type, fill, select, press, drag, upload, dialog, evaluate, hover) is denied.
- `interact` â€” observe plus ordinary in-page use of the **current local application**: tabs, drawers, filters, forms, hamburger navigation, row opening, dialogs, record traversal.

Clicking a local tab is observation of the running app. It is not `write` to product source and not a consequential external action. L1 may grant `mcp.browser: interact` while keeping `write: false` and shell `deny`.

The MCP server `url` is identity, not a user destination. HTTP(S) destinations in tool input inherit destination classes:

- `loopback` â€” local UI (`http://127.0.0.1`, `localhost`)
- `public_read` â€” ordinary HTTPS/HTTP research (docs/search GET-shaped traffic). This is **not** permission to click/type on those pages.
- `destinations` â€” optional extra explicit hosts

`interact` requires `loopback`. Compile injects `loopback` when network classes are omitted; it does not inject `public_read`. `interact` plus an explicit `public_read`-only class is a compile error.

Consequence is **not** â€œlast explicit navigate was loopbackâ€:

- **Agent-aimed destinations** (URL-shaped tool input such as `browser_navigate` / `browser_network_request` `url`, including HTTP method) are ENFORCED. `public_read` is GET-shaped research. POST/PUT/PATCH/DELETE to a public origin is `BROWSER_PUBLIC_MUTATE`. Accessible names are not destinations; `element: "https://â€¦"` is not a URL grant.
- **Observed page origin** is recorded from allowed navigate input and from `afterMCPExecution` / `postToolUse` results (`Page URL`, `page.url`, active tab). Interact is allowed on `loopback` or a local fixture (`file://` under the project, `data:text/html`). Proven public/other origin denies later click/type/fill even without `public_read`.
- **First in-page gesture** (click a link, submit a form, open a tab) can change Chromium destination before the after-hook runs. That one gesture is UNAVAILABLE at pre-tool because click payloads have no href. Subsequent interact is gated once the page URL is observed.
- **App-initiated XHR/fetch from a local page** (SPA calling an API without a page-origin change) is product behaviour, not an EIF MCP decision. Chromium network is not the hook.

The measured `RUNTIME_CAPABILITIES.md` records those two residuals as UNAVAILABLE `browser_egress`. ENFORCED `mcp_guard` does not cover them.

`about:blank` is not HTTP egress. Destructive MCP payloads stay denied unless `destructive_data` is granted. `browser_cdp` / `browser_run_code_unsafe` stay denied unless `infrastructure_control` is granted. Do not add a parallel `public_web` class. Do not restore `mcp_read` / `mcp_write` as operator toggles.

Recommended L1 UI-audit envelope (still no product writes):

```yaml
max_authority: L1
change_paths: []
shell:
  mode: deny
mcp:
  browser: interact
  tools: []
network:
  classes:
    - loopback
```

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
mcp:
  browser: interact
  tools: []
network:
  classes:
    - loopback
```

Do not grant `write: true` with `.eif/**` for audits. That envelope is invalid: it is not limited to `.eif/audit/**` and would treat canonical `.eif` state as implementation change scope. Canonical files such as `.eif/CONTEXT.md`, `.eif/DECISIONS.md` and `.eif/RUNTIME_CAPABILITIES.md` remain unwritable under artifact authority. Product trees (`src/**`, `apps/**`, `tests/**`, `docs/**`, `migrations/**`, `.cursor/**`) remain denied.

Chat-only L0/L1 audits may keep `artifact_write: false`; the Volume 25 intelligence bar still applies to the conversation output. Missing artifact grant means `UNABLE_TO_PROTOTYPE` / chat-only reports, not product writes.

For L3, `change_paths` must be explicit before product-source writes are granted. Adjacent-scope paths are separate and still require the necessary external change test in Constitution Â§0.5.

## Policy lifecycle

1. Draft/modify this file.
2. Have the appropriate owner accept it.
3. Run `tools/compile_policy.py`.
4. Run the runtime probe in the same Cursor mode that will execute the work.
5. Grant only authority supported by the **measured** `RUNTIME_CAPABILITIES.md`. Sandbox UNAVAILABLE does not block L3.
