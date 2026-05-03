# Cursor Prompt Templates

These templates are reusable task starters for Cursor.

Use them to prevent:
- broad uncontrolled edits
- repeated refix loops
- unnecessary full-codebase scanning
- unnecessary rebuilds/restarts
- expensive model usage on vague tasks
- commits without validation

General rule:
- Use PLAN ONLY for risky, unclear, cross-file, database, import, auth, policy, background-job, or architecture-sensitive work.
- Use IMPLEMENT APPROVED PLAN only after the plan is good.
- Use AUDIT DIFF ONLY after implementation, especially before committing or merging.
- Use FIX SPECIFIC ERROR ONLY when something breaks.
- Use VALIDATE AND COMMIT LOCAL when changes already exist and need safe closure.

---

## 1. PLAN ONLY

Use when the task is unclear, risky, cross-cutting, or has caused repeated bugs before.

```text
PLAN ONLY. Do not edit files.

Goal:
[describe the task]

Context:
[paste relevant error, screenshot description, current behavior, expected behavior, previous Cursor result, or known files]

Find:
- relevant files
- likely root cause
- smallest safe implementation path
- affected services
- focused validation commands
- risks/regressions

Return:
- root cause summary
- proposed files to change
- patch plan
- validation plan
- risks or unknowns

Wait for approval before editing.
```

---

## 2. IMPLEMENT APPROVED PLAN

Use only after a plan has been reviewed and accepted.

```text
Implement the approved plan.

Scope:
Only touch:
- [file 1]
- [file 2]
- [file 3]

Rules:
- No unrelated refactors.
- No architecture changes.
- Preserve existing behavior outside this task.
- Do not install, remove, or upgrade dependencies.
- Do not create or modify database migrations unless explicitly included in the approved plan.
- If the approved plan appears wrong, stop and explain before editing more.

Validation:
Run the smallest relevant validation first:
- [focused validation command]

Then, only if passing, run:
- [broader validation command, if needed]

Finish:
- Restart only affected services if needed.
- Commit locally if validation passes.
- Do not push.
- Report changed files, validation results, services restarted, and commit hash.
```

---

## 3. AUDIT DIFF ONLY

Use after Cursor has implemented something. This is for review, not editing.

```text
AUDIT ONLY. Do not edit files.

Review the latest diff for:
- regression risk
- missed edge cases
- API/UI/DB/worker contract mismatch
- unnecessary changes
- unrelated refactors
- test coverage gaps
- security/secrets risk
- migration/dependency/config risk
- validation gaps

Return:
- PASS or FAIL
- must-fix issues only
- optional improvements separately
- recommended validation commands, if missing

Do not edit files.
```

---

## 4. FIX SPECIFIC ERROR ONLY

Use when a specific error appears after implementation.

```text
Fix this specific error only.

Error:
[paste exact error/log]

Context:
- occurred after: [commit/task/change]
- expected behavior:
- actual behavior:
- affected screen/endpoint/job/service:
- known relevant files, if any:

Instructions:
- Diagnose root cause before editing.
- Do not fix unrelated issues.
- Do not perform broad refactors.
- Do not change architecture.
- Do not install/remove/upgrade dependencies.
- If the root cause is outside the expected scope, stop and explain before editing.

Validation:
Run the smallest relevant validation.

Finish:
- Restart only affected services if needed.
- Commit locally only if validation passes.
- Do not push.
- Report changed files, validation result, services restarted, and commit hash.
```

---

## 5. VALIDATE AND COMMIT LOCAL

Use when changes already exist and you want Cursor to safely close the task.

```text
Validate the current changes and commit locally if safe.

Steps:
1. Inspect the current diff.
2. Confirm no unrelated files are included.
3. Confirm no secrets, credentials, tokens, or private environment values are included.
4. Run the smallest relevant validation first.
5. Run broader validation only if appropriate.
6. If validation passes, commit locally with a clear conventional commit message.
7. Do not push.

Return:
- changed files
- validation commands run
- validation result
- services restarted, if any
- commit message
- commit hash
- any risks or follow-ups
```

---

## 6. SUPPLY-CHAIN IMPORT / JOB FLOW PLAN

Use for import parsing, mapping, validation, commit/apply, async job, retry, refresh recovery, or audit-history work.

```text
PLAN ONLY. Do not edit files.

Goal:
[describe the import/job/mapping issue]

Context:
[paste error, validation output, screenshot description, current behavior, expected behavior]

Investigate:
- parser output
- UI mapping state
- API contract
- validation result shape
- job lifecycle/state transitions
- worker behavior
- database persistence/audit records
- refresh/reload recovery behavior
- duplicate/retry/double-click protection

Find:
- relevant frontend files
- relevant API files
- relevant worker/job files
- relevant database models/tables
- root cause
- smallest safe implementation path
- validation plan

Rules:
- Do not bypass validation.
- Do not silently coerce ambiguous SKU/customer/distributor/product mappings.
- Do not change import semantics without explaining the business impact.
- Do not create migrations unless absolutely required and explicitly approved.

Return:
- root cause
- proposed files to change
- patch plan
- validation plan
- risks/unknowns

Wait for approval before editing.
```

---

## 7. SUPPLY-CHAIN IMPLEMENT APPROVED PLAN

Use after approving a supply-chain import/job/mapping plan.

```text
Implement the approved supply-chain plan.

Scope:
Only touch the files identified in the approved plan unless unavoidable.
If additional files are needed, stop and explain before editing them.

Rules:
- Preserve auditability and traceability.
- Keep frontend/API/worker/database contracts synchronized.
- Keep commit/apply flows safe against refresh, retry, double-click, duplicate submission, stale jobs, and partial completion.
- Do not weaken validation.
- Do not hide ambiguous mappings.
- Do not introduce hidden matching behavior without user confirmation.
- No unrelated refactors.
- No dependency changes.
- No migrations unless explicitly approved.

Validation:
Run focused validation for the changed area.

For import/job changes, validate where relevant:
- successful validation
- failed validation
- ambiguous mapping
- refresh/reload recovery
- duplicate/retry protection
- queued/running/completed/failed state handling

Finish:
- Restart only affected services.
- Commit locally if validation passes.
- Do not push.
- Report changed files, validation results, services restarted, and commit hash.
```

---

## 8. RECLAIM PLAN

Use for Reclaim tasks involving Health Connect, permissions, onboarding, auth, notifications, Home UI, insights, Play Store policy, or release readiness.

```text
PLAN ONLY. Do not edit files.

Goal:
[describe the Reclaim task]

Context:
[paste error, screen behavior, policy issue, current behavior, expected behavior]

Investigate:
- relevant screens/components
- relevant hooks/services
- Health Connect/permission impact
- Supabase/auth/session impact, if any
- Play Console/Data Safety impact, if any
- user-facing copy/claims impact
- release risk
- smallest safe implementation path
- validation commands

Rules:
- Do not add new health permissions or data types without explicit approval.
- Do not create unsupported wellness/medical claims.
- Preserve STATE → MEANING → ACTION.
- Avoid guilt, streak-pressure, or alarmist wellness language.
- Preserve the warm, premium, rounded design language.
- Do not alter auth/deep-link/session handling unless this task is specifically about auth.
- No broad redesigns unless explicitly requested.

Return:
- root cause or design gap
- proposed files to change
- patch plan
- validation plan
- Play/policy risk, if any
- risks/unknowns

Wait for approval before editing.
```

---

## 9. NEUROGROW PLAN

Use for schematic, firmware, component, rail, connector, sensor, power, or enclosure-related work.

```text
PLAN ONLY. Do not edit files.

Goal:
[describe the NeuroGrow task]

Context:
[paste schematic finding, component issue, firmware issue, or design question]

Investigate:
- relevant schematic/firmware/design files
- affected power rails
- affected connectors
- affected components
- affected firmware pins/interfaces
- safety/electrical implications
- uncertainty or assumptions
- smallest safe change path
- validation/checklist

Rules:
- Treat hardware/schematic changes as safety-critical.
- Separate confirmed facts from assumptions.
- Do not invent component values or wiring assumptions without flagging uncertainty.
- Preserve 24V_IN → 12V_AUX → 5V_SYS → 3V3_LOGIC rail logic unless explicitly changed.
- Always consider power, grounding, protection, connector, and sensor-voltage implications.
- Do not optimize aesthetics over electrical correctness.

Return:
- confirmed issue
- assumptions/uncertainties
- proposed fix
- affected components/nets/files
- validation/checklist
- risks

Wait for approval before editing.
```

---

## Model Routing Notes

Default model routing:

- Composer 2 / Auto:
  - simple edits
  - UI tweaks
  - known file changes
  - mechanical implementation

- Claude Sonnet medium-thinking:
  - cross-file implementation
  - moderate debugging
  - import/job flow fixes
  - API/frontend contract work

- Claude Opus high-thinking:
  - diagnosis only
  - architecture review
  - final audit
  - repeated bug that survived cheaper models

Rule:
Do not use Opus as the default implementer.
Use Opus for diagnosis/audit, then use Composer or Sonnet to implement the bounded fix.

---

## Standard Closing Instruction

Add this to implementation prompts when needed:

```text
Finish by:
1. Running focused validation.
2. Restarting only affected services if needed.
3. Committing locally only if validation passes.
4. Not pushing.
5. Reporting changed files, validation result, services restarted, and commit hash.
```