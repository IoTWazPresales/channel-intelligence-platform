# N-0086 implementation — security hardening before 24/7 exposure

Run: `RUN-20261009-N0086-IMPL` (implementation; self-verification only — GOV-008 must run under a different run).
Lenses: backend-engineer (owner), application-security-specialist, test-engineering-specialist, threat-modeling-specialist.
Base tree: HEAD `1714b78d` plus a shared dirty tree (other nodes N-0065, N-0068, N-0109 have uncommitted work in the same files list; only the N-0086 hunks below belong to this node).

Status: criteria 1 and 2 tested. Criterion 3 (pilot passwords via N-0075) is not built. Operator acceptance is still pending. Not closed.

The previous session of this run was cut off by a usage limit; this session continued from its on-disk state without redoing finished work:
proxy header module + vitest, API throttle key change + pytest, steward gates on imports / cst_steward / mappings / product_master_gaps / exceptions, before/after route tables.

## Tests run 2026-10-10

- `pytest tests/test_login_throttle_n0086.py tests/test_rbac_n0086_steward_writes.py` from `apps/api`: 153 passed.
- Vitest: `proxyForwardedHeaders.test.ts` 15, `stewardAccess.test.ts` 14, `StewardWriteGate.test.tsx` 5. 34 passed.

Criterion 1: the web proxy drops visitor-supplied forwarding headers and sends one trusted address. A loopback peer uses the right-most X-Forwarded-For entry; any other peer is used as itself. Criterion 2: steward writes on the named routes require steward or admin, and the web gate hides those controls from other roles. Criterion 3 is the N-0075 invite flow, which is not built. No browser pass in this run. No product commit.
