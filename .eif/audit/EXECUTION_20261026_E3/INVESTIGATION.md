# E3 preparation — fictional background scope evidence

Observed 26 October 2026 after pushed E1, while E2 is in validation. No E3
production-source changes, implementation lease or acceptance yet.

The original verifier reported an unset-tenant-context risk, not a demonstrated
cross-tenant leak. Do not relabel that historical finding as a demonstrated leak.
E1 now explicitly constrains governed CPOR cases to the query tenant and runs
on the request session; this investigation observes that actual corrected tree.

Reproduction: `../EXECUTION_20261026_E2/test_background_scope_probe.py`, executed
with db_on.py pytest (cip_test only). The existing real-bearer fixture asserts the
database identity and owns an outer transaction; all account/case/report/schedule/
inbox fixture writes roll back. Actual report_schedule_runner execution is used;
only its session factory is redirected to the fixture connection, as a savepoint.
No broker, external send, service process, production data or role/grant is used.

| Fixture identity | Interactive support total | Background delivery preview |
|---|---:|---:|
| Tenant A admin | 70 | Schedule owner |
| Tenant A scoped viewer | 10 | 70 |
| Tenant A viewer with no assigned lines | 0 | 70 |
| Tenant B admin | 1000 | An A-owned delivery row associated to B's recipient ID, value70 |

The background call ran with tenant, role, read/edit product ContextVars explicitly
None. Its CPOR query total remained70, not1070: no cross-tenant query aggregation
was demonstrated in this probe. The foreign-recipient row is tenant A owned;
this probe does not prove that tenant B can read that inbox row. It does establish
that schedule creation accepts a foreign tenant recipient ID and the runner
does not reject it. Subscriber/owner identity validation is required independently
of the same-tenant owner-versus-recipient permission policy.

The same-tenant recipient scope discrepancy is executable evidence, not merely
source suspicion. The asynchronous operator question asks which current scope
governs same-tenant deliveries: recipient permissions (recommended), explicitly
authorized owner sharing, or refusal pending policy. Warren subsequently explicitly selected **each recipient's current permissions** on26October. Supported decision.add recorded accepted D-0132 at EIF2778. Reuse this authority; do not ask again.
Cross-tenant recipients must be rejected in all variants. Current report
visibility rules, active identity and transaction-local scope machinery should
be reused; no new database identity is needed.

Next: finish/persist E2, acquire N-0115 for E3, write focused regressions before
correcting the demonstrated boundaries. The recipient policy is resolved; implement current scopes and the independent identity/tenant/visibility checks. Do not silently deliver broader data or declare E3 complete before verification.
