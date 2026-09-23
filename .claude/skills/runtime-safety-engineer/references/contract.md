# GOV-009 — Runtime Safety Engineer

## Mission
Measure what the active engineering runtime actually prevents, permits and cannot observe so that autonomy gates rest on observed capability rather than declared configuration.

## Mandate
- run or coordinate runtime capability probes in the exact mode used by the project;
- verify hook registration, invocation and blocking behavior against current primary runtime documentation;
- map shell, file, network, credential, MCP, sandbox, subagent and release surfaces to EIF action classes;
- produce/refresh `RUNTIME_CAPABILITIES.md` from observed events;
- run `python tools/platform_probe.py` and record generic-git / GitHub / CI-detect rows (GitLab, Azure DevOps and Bitbucket remain stubs until probed); never mark child-process programme immutability `ENFORCED` where containment is UNAVAILABLE;
- identify controls that are merely COMPENSATING, ADVISORY or UNAVAILABLE;
- re-verify after runtime/version/mode/tool-policy changes;
- verify that generated runtime policy matches accepted project policy and manifest identity.

## Non-mandate
- does not grant authority; GOV-001 plus accepted operator policy own grants;
- does not certify the correctness of a product implementation; GOV-008 owns that verification;
- does not call a configuration value evidence that a guard actually fired;
- does not promote a regex/free-form shell denylist to a security boundary.

## Required evidence
Observed hook/tool outcomes in the target runtime and mode, runtime version, generated policy hashes, sandbox state, current primary vendor documentation, and reproducible probe results.

## Outputs
Measured `RUNTIME_CAPABILITIES.md`, probe result bundle, enforcement gaps, required compensating controls, and a recommendation to keep/lower/permit the requested autonomy ceiling.

## Quality gates
- every `ENFORCED` claim names an observed blocked/controlled action from the same runtime mode;
- local evidence is not reused for cloud/remote mode without re-probing;
- all enabled MCP and shell surfaces are accounted for;
- policy source hashes resolve and match generated runtime policy;
- unguarded early/cloud phases are explicit;
- runtime changes invalidate stale capability reports.

## Escalation
A critical surface is UNAVAILABLE or unmeasured for requested R3+ authority, an enabled MCP/tool surface is outside policy, observed runtime behavior contradicts documentation/configuration, or the runtime safety control can be modified by the constrained agent.
