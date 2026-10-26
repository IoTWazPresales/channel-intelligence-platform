# E3 current-recipient scheduled delivery scope

Implementation run RUN-20261026-N0115-E3-CODEX; base commit
03ec2221251bfba489b73f2d2a00742399b961d9. Accepted D-0132 (Warren,
26 October) requires each recipient's current permissions. No owner sharing
authority or commercial definition changes are implied.

## Canonical paths and reproduction

| Trigger | API route | Background task | Writer | Commit model |
| --- | --- | --- | --- | --- |
| Create schedule / Run now | reports/schedules, schedules/{id}/run-now | none for Run now | report_delivery.deliver_saved_report | per delivery; schedule metadata afterward |
| Calendar / import completion | existing scheduler/fanout entry points | report_schedule_runner | same delivery service and query engine | per delivery; existing scheduling cadence retained |
| Execution failure | existing runner exception path | same runner | _write_failed_delivery | failure inbox batch |

No importer action/fact writer is involved. Existing buttons continue to use
these paths. Extend the canonical delivery boundary, rather than adding a
second query or notification writer. Query execution is read-only; the inbox
and schedule records are the existing writes.

The actual runner initially delivered fictional CPOR total70 to same-tenant
viewers whose interactive totals were10/0 and accepted a foreign subscriber ID.
The query total stayed70, not1070. This does not demonstrate a production
cross-tenant leak or prove the foreign user could read the A-owned inbox row.
The initial clean regression run failed8 cases before production correction.
The earlier harness teardown failures remain separate evidence.

## Change

- Resolve active, same-tenant identities and existing report visibility on
  creation, Run now and each background delivery, using server-side roles and
  current product assignments. Bind report tenant and the canonical read/edit/
  role context; apply its transaction-local gate to the already-open transaction.
- Restore caller ContextVars and the live transaction gate after delivery
  commit/refresh. Roll back failed recipient transactions, including aborted SQL,
  before restoring caller context. Unscoped workers resume the canonical open gate.
- Refuse mismatched schedule/report tenants. Do not send failure report details
  to missing, inactive, foreign or otherwise unauthorized recipients.
- Run now returns only inbox-visible delivery contents to its caller. Running a
  report for a broader recipient does not grant that recipient's data to the caller.

Independent review found the response and live-transaction gaps in the initial
implementation. Root reproduced all3 failures before correcting them. Final
tests cover successful, rejected and aborted-SQL cleanup. The pool test originally
over-required '*'; blank/NULL are also canonical open values, so that assertion
was corrected without claiming its initial failure demonstrated leakage.

## Verification and limits

Fresh focused root:40 passed/1 opt-in browser skip. Separate Astra:29 passed,
VERIFIED_WITH_LIMITATIONS, with final eight-path hashes. Full required gate
results are recorded in final-summary.json when complete. Earlier runs remain
historical, not substituted for fresh evidence. Lint's initial attempt omitted
the documented ESLINT_USE_FLAT_CONFIG=false shell setting; its corrected run
is separate. No product frontend change is needed for that setup error.

Fictional fixture writes use an outer rollback on cip_test; the pool check changes
only transaction-local settings. No production connection, migration, service
restart, external send, database identity/grant, deployment or main action.
This is real query/runner/authenticated API integration, not browser or broker smoke.
Non-owner database proof, exhaustive concurrency/revocation races, remaining
original model/calendar/security/performance scope and operator acceptance remain
outstanding. No complete R3/runtime attestation is claimed.

Resume status revealed that the prior four-hour lease elapsed during the
interruption. Review regression edits/corrections made during that resume
preceded detection; supported reacquisition at revision2783 restores ownership,
but does not retrospectively establish uninterrupted lease enforcement. The
runtime did not prevent filesystem edits. This procedural/runtime limitation
is preserved, not converted into a guard pass. Ledger integrity is true and
historical gate debt remains acknowledged.

Next executable unit: E4 saved-query equivalence/sort/limit/period grain,
promotion context and saved-v2 export routing. E6 retains legacy tenant semantic
restrictions/model overlays; no original requirement has been silently deferred.
