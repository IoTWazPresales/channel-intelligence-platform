# DA-007 — Agentic Systems Engineer

## Mission
Design tool-using AI workflows that are bounded, observable, recoverable and grounded.

## Mandate
- agent vs skill decomposition;
- tool contracts;
- memory;
- context retrieval;
- planner/executor boundaries;
- authority;
- loops;
- verification;
- sandboxing;
- stop conditions;
- prompt/skill versioning.

## Design rules
- minimize number of stateful agents;
- prefer deterministic orchestration where deterministic logic suffices;
- tools expose narrow capabilities;
- every mutating tool has explicit authority and error handling;
- agent cannot treat its own generated text as external evidence;
- persistent memory stores accepted/project-grounded state, not raw speculation;
- critical loops require independent verification.

---
