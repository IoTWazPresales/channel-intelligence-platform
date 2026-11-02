---
eif: decision-register
version: 0.3
review_after: event-driven
status: active
last_updated:
owner:
---

> **Artifact safety:** Reference sensitive data; never reproduce secret values, credentials, tokens, private keys or customer PII here. Use `[SECRET]`, `[CREDENTIAL]`, `[PII]`, or `[CUSTOMER-DATA]` markers with locations instead.

# Decision Register

| ID | Date | Status | Decision | Owner | Review trigger |
|---|---|---|---|---|---|
| D-0132 | 2026-10-26 | PROPOSED | Scheduled report delivery runs under each recipient's current permissions (active identity, same tenant, existing report visibility), not the schedule owner's | Warren | A change to who may receive a scheduled report, or a role or product-line scope change |

## ADR template

### ADR-XXXX — <title>
- Status: PROPOSED | ACCEPTED | EXPERIMENTAL | SUPERSEDED | REJECTED | DEFERRED
- Date:
- Owner:
- Risk:
- Reversibility:

#### Context

#### Evidence

#### Decision

#### Alternatives

#### Consequences

#### Verification

#### Review / invalidation trigger

#### Affected artifacts

### D-0132 — Scheduled delivery uses each recipient's current permissions
- Status: PROPOSED (recorded here on 2 November 2026 at the operator's instruction; see the note under Evidence)
- Date: 2026-10-26
- Owner: Warren
- Risk: R3 (who may read governed figures in a background job)
- Reversibility: reversible in code; a delivery already sent cannot be recalled

#### Context
A scheduled report runs in the background with no request context. Before this decision it ran with the schedule owner's authority, so a recipient with narrower product-line access could receive figures they cannot open themselves, and a schedule could name a recipient of another tenant. The question put to Warren on 26 October 2026: which current scope governs a same-tenant delivery: the recipient's permissions (recommended), explicitly authorised owner sharing, or refuse until a policy exists.

#### Evidence
- `.eif/audit/EXECUTION_20261026_E3/INVESTIGATION.md`: the executable probe (tenant A owner total 70, scoped viewer 10, viewer with no assigned lines 0; a schedule accepted a foreign-tenant recipient id).
- Note: the programme ledger records D-0132 as accepted by Warren on 26 October (`decision.add` at EIF 2778) and `E3_IMPLEMENTATION.md` / `VERIFY_ASTRA.md` call it "accepted". It was never written into this register. This entry is `PROPOSED` because the operator asked for it to be recorded as proposed; Warren confirms or changes the status.
- GOV-008 review of 2 November 2026 (`.eif/audit/REVIEW_20261102/FINDINGS.md`): the tenant, inactive, revoked and other-tenant recipient refusals hold; finding M4 (one failing recipient stopped the rest) is fixed in batch 2.

#### Decision
Each recipient's own current permissions govern a scheduled delivery: the recipient must be an active user of the report's tenant who can view the report, and the query runs with that recipient's product-line scope. A recipient who fails any check is refused and not notified. A cross-tenant recipient is refused in every variant.

#### Alternatives
- Owner's authority: rejected, it can show a recipient more than they may see.
- Explicit owner sharing: not built; it needs a sharing model nobody has asked for.
- Refuse until a policy exists: rejected, scheduled reports would stop.

#### Consequences
A schedule's recipients may see different figures from each other and from the owner. One recipient's refusal must not stop the others (batch 2, M4). A deactivated recipient receives nothing, not even a failure notice.

#### Verification
`tests/test_report_schedule_recipient_scope.py`, `tests/test_batch2_m4_schedule_recipients.py`; GOV-008 probe `reports/gov008_probe_e3_schedule.py`.

#### Review / invalidation trigger
A change to roles, product-line scope or report visibility rules; any request to deliver to people outside the tenant.

#### Affected artifacts
`apps/api/app/services/report_delivery.py`, `apps/api/app/services/report_schedule_runner.py`, N-0115 / N-0116 evidence.
