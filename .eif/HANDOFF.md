---
eif: handoff
version: 0.3
review_after: ephemeral
owner: Warren
status: blocked
last_updated: 2026-08-23
from: cursor-agent-cip
to: Warren
project_id: channel-intelligence-platform
commit_policy: project-defined
---

> **Artifact safety:** Reference sensitive data; never reproduce secret values, credentials, tokens, private keys or customer PII here.

# Session / Model Handoff

## Task

Upgrade this CIP repo to released **EIF v0.5.0 Programme Release** using EIF’s supported install/migrate path. Preserve CIP identity, product code, authority envelope, and accepted runtime policy except compatible framework-state changes required by v0.5.0. Do not start the CIP North Star product programme. Do not weaken fail-closed guards.

## Scope and authority

Operator-directed EIF framework maintenance. CIP product implementation change scope: **none**. Control-plane writes from this CIP agent: **denied** (`control_plane_change: false`; guard denies control-plane Write/Delete unconditionally). EIF product tree is outside compiled `allowed_roots`.

## Business rule / intended outcome

CIP is on EIF v0.5.0, installation valid, programme state migrated where applicable, project identity/authority preserved, and a **fresh** same-machine Cursor runtime certification exists so a v0.5 programme can be chartered safely.

## Facts established (this session)

- **CIP identity:** `project_id` `channel-intelligence-platform`; VCS `C:/Users/warren_eliason/channel-intelligence-platform`; `root_commit` `8f7f1b53e3555dd3010244c7fe8b398ecb881548`; remote `https://github.com/IoTWazPresales/channel-intelligence-platform.git`.
- **Git:** branch `feat/promote-provisionals-run`; HEAD `29b5fbff6e592afc255eb9cedb3bba6ae79ff8e9`. EIF trees (`.eif/`, `.cursor/hooks*`, `.cursor/eif-runtime-policy.json`, `.cursor/rules/eif-*.mdc`, `.agents/`) are **untracked**.
- **Installed compiled runtime:** `.cursor/eif-runtime-policy.json` `framework_version` **`0.4.0-draft`**, `schema_version` 3, `max_authority` **L3**, `policy_status` **accepted**, `control_plane_change` **false**, `shell.mode` **workspace**, MCP allowlist `browser_*` + `mcp.browser: interact`.
- **Accepted policy source:** `.eif/AUTONOMY_POLICY.md` status **accepted**, owner Warren, dated 2026-08-22, L3 / R3, `runtime_mode: local`. YAML `version: 0.3`. Specialist skills still stamp `framework_version: 0.3.0-draft`.
- **Last runtime certification:** `.eif/RUNTIME_CAPABILITIES.md` probe `R20260822192834_EECF1A` at 2026-08-22T17:37:50Z; result **passed 13/13**; Cursor **3.12.17** local. That evidence is **stale for a v0.5.0 install** (different hooks/policy/launcher hashes) and must not be reused as v0.5 certification.
- **EIF product is not in this workspace:** no `install_project.py` / `compile_policy.py` / `runtime_probe.py`; `python` 3.14.2 has no `eif*` module; `where eif` found nothing; `EIF_HOME`/`EIF_ROOT`/`PYTHONPATH` unset.
- **Live denials this session:**
  - Shell `python C:\AI\engineering-intelligence-framework\tools\install_project.py --help` → `FOREIGN_PATH`
  - Read outside compiled roots → `FOREIGN_PATH`
  - MCP `move_agent_to_root` → `MCP_NOT_GRANTED`
  - Chained identity git (`git status --short; git branch --show-current; …`) → hook **fail-closed exit 1**; single `git status --short` **allowed** (`SHELL_WORKSPACE`)
- Workspace shell for in-repo ordinary commands **works** (this is newer than the 2026-08-22 escalation, which still described allowlist+sandbox L3).

## Assumptions

- The EIF v0.5.0 product checkout still lives on this machine (prior docs name `C:\AI\engineering-intelligence-framework`). That path was **not re-read** this session (`FOREIGN_PATH`).
- v0.5.0 install/migrate CLIs exist only in that product tree (or its documented launcher), not inside CIP.

## Unknowns

- Whether `C:\AI\engineering-intelligence-framework` is actually tagged/released **v0.5.0** right now (unreadable from CIP).
- Exact v0.5.0 `install_project.py` / migrate flags, and whether they rewrite accepted L3 `AUTONOMY_POLICY.md` to L1 defaults.
- v0.5 programme-architecture artifact set (cannot read the release).

## Work completed

In-repo state survey + live boundary proof. No CIP product edits. Hooks not weakened. No fake `ENFORCED`. No reuse of probe `R20260822192834_EECF1A` as v0.5 evidence.

## Files changed

- `.eif/HANDOFF.md` (this file)
- `.eif/ESCALATION.md` (v0.5.0 host-installer grant)
- `docs/memory/CURRENT.md` / `CONTEXT.md` (operational note only)

## Commands/tests run

| Command / tool | Result |
|---|---|
| Read `.eif/PROJECT_MANIFEST.md`, `AUTONOMY_POLICY.md`, `RUNTIME_CAPABILITIES.md`, `.cursor/eif-runtime-policy.json` | OK — identity + 0.4.0-draft L3 accepted |
| `git status --short` | OK — EIF install untracked |
| `git branch --show-current` / `git rev-parse HEAD` | `feat/promote-provisionals-run` / `29b5fbff…` |
| `python --version` | Python 3.14.2 |
| `python -c` eif module probe | no `eif*` module; no EIF env vars |
| `where.exe eif` | not found |
| Official installer `--help` via absolute EIF path | `FOREIGN_PATH` |
| MCP `move_agent_to_root` | `MCP_NOT_GRANTED` |
| `runtime_probe.py` / compile | **not run** (tools not in CIP; would be FOREIGN_PATH / control-plane) |

## Results

**Blocked before v0.5.0 install.** CIP remains on compiled EIF **0.4.0-draft**. Programme migration **not started**. Fresh v0.5 runtime certification **not started**.

## Decisions made / pending

Pending operator: run EIF v0.5.0 install/migrate from **host PowerShell** (not this CIP-hooked agent), preserving accepted L3 envelope and CIP identity; then return here for in-Cursor probes. Operator grades `runtime_probe.py report` outside Cursor if that remains the v0.5 contract (last 0.4 probe PLAN forbade the agent from running report).

## Risks

Installer may reset policy to L1. Do not treat CURRENT+old F27 as v0.5 capability evidence. Do not weaken CIP hooks to let this agent rewrite the control plane.

## Opportunities intentionally not implemented

CIP North Star programme charter. CIP product code. Hook weakening. Path-hiding / env-var tricks around `FOREIGN_PATH`. Fabricating ENFORCED.

## Exact next action

Warren: host PowerShell in `.eif/ESCALATION.md` (v0.5.0). Confirm the product tree is the **released v0.5.0**, run **that release’s** documented install + migrate + compile against this CIP path, restore L3 if the installer dropped authority, then resume this CIP chat for probe execution only.

## Read these first

1. `.eif/ESCALATION.md`
2. `.eif/AUTONOMY_POLICY.md` (accepted L3 envelope to preserve)
3. `.eif/PROJECT_MANIFEST.md` (identity to preserve)
4. `.eif/RUNTIME_CAPABILITIES.md` (stale 0.4 evidence; do not reuse)

## Verification status

v0.5.0 install: **not started** (environment/authority blocker).
v0.5.0 compile/install validation: **not started**.
Fresh runtime certification: **not started**.

## Remaining budget / stop state

Stopped. Correct stop: EIF product + installer are outside CIP `allowed_roots`; control-plane mutation is denied; MCP cannot retarget the agent onto the EIF repo.
