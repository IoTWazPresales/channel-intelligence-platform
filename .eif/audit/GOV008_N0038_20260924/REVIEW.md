# GOV-008 independent review — N-0038 (Stage 3.2 CPOR role checks, BACKLOG-136/141)

Reviewer: verification-controller lens, plus identity-access-specialist, security-skeptic,
test-engineering-specialist. Model: claude-sonnet-5 (Sonnet 5). Independence rung: R2, another
session (fresh context, no access to `.eif/audit/PROGRAMME_20260924/n0038/`) — self-verification
was not needed as a fallback. Read-only: no product-source edits, no commits, no writes to `cip`
(all commands below ran against test/clone databases, mocks, or in-process route introspection).

Evidence base: `git show 209acf82`, `git show 66757fde` (full diffs read in full), current content
of `apps/api/app/api/v1/endpoints/{cpor_cases,cpor_exports,cpor_fx,cpor_historical_import,
cpor_payment_evidence,shipment_evidence}.py`, `apps/api/app/core/security.py`, `docs/BACKLOG.md`
BACKLOG-136 / BACKLOG-141, `apps/api/tests/test_rbac_n0038_cpor_roles.py`,
`apps/api/tests/conftest.py`, and a fresh in-process route-introspection script (written to and
deleted from this review folder — not the implementer's script).

## Criterion 1 — every CPOR write endpoint requires a role; viewer is read-only

**PASS — VERIFIED.**

Command (fresh script, this session, not the implementer's):
```
apps/api/.venv/Scripts/python.exe .eif/audit/GOV008_N0038_20260924/enum_routes.py
```
imports `app.main.app`, walks `app.routes` for `/cpor` and `shipment` paths, and prints each
route's dependant chain. Result: every `POST`/`PATCH` under `/api/v1/cpor/**` carries
`require_roles.<locals>._dep` in its dependency chain; every `GET` under `/api/v1/cpor/**` carries
only `get_current_user` (authentication only, no role gate) — e.g.:
```
WRITE POST   /api/v1/cpor/cases                                    deps=[..., 'require_roles.<locals>._dep']
read  GET    /api/v1/cpor/cases                                    deps=['get_current_user', 'get_current_user']
WRITE POST   /api/v1/cpor/historical-import/jobs/{job_id}/apply     deps=[..., 'require_roles.<locals>._dep']
WRITE POST   /api/v1/cpor/payment-evidence/jobs/{job_id}/apply      deps=[..., 'require_roles.<locals>._dep', '_sync_db']
```
Allowed sets read from the closures (and cross-checked against the diff and
`apps/api/tests/test_rbac_n0038_cpor_roles.py::_CPOR_WRITE_MATRIX`):
- Case lifecycle / settle / claim-evidence / promo-plan / export / FX writes → `{PLANNER, ADMIN}` (`cpor_cases.py`, `cpor_exports.py`, `cpor_fx.py`).
- Historical-import writes (`map-token`, `bulk-map-token`, `validate`, `apply`, `resolution-plan*`) → `{ADMIN}` only.
- Payment-evidence resolve/apply (`map-token`, `mark-shell-case`, `re-resolve`, `apply`) → `{STEWARD, PLANNER, ADMIN}`.
`require_roles` (`apps/api/app/core/security.py:177`) always admits `ADMIN` regardless of the
declared set, and 403s (`"Insufficient role"`) anyone else not in the set — `VIEWER` is in none of
the sets, so viewer is read-only everywhere. Confirmed live:
```
apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_rbac_n0038_cpor_roles.py -q
21 passed
```
including `test_no_cpor_write_admits_viewer`, `test_cpor_reads_stay_authentication_only`, and the
parametrized allowed/denied behavioural cases (real TestClient requests through the full
dependency chain — allowed role gets 422 past the gate, denied role gets a real 403).

Export generate, settle (`transition`/`settlement/rollup`), payment-evidence apply, historical
import and FX writes are each explicitly present in the matrix above — all covered.

## Criterion 2 — shipment steward panels accept STEWARD and ADMIN; no shipment-evidence write is ungated

**PASS — VERIFIED**, including the F1 fix in 66757fde.

Same route-introspection script, filtered to `/api/v1/shipment-evidence/**`: every non-GET route
carries `require_roles.<locals>._dep` with allowed set `{ADMIN, STEWARD}` — 28 gated routes total,
matching `test_shipment_evidence_gates_admit_steward_and_admin`'s `assert len(gated) == 28` and
`wrong == {}` exactly (re-run, passes).

Independently re-diffed 66757fde: before that commit, `shipment_steward_bulk_preview`,
`shipment_steward_bulk_apply`, and `shipment_steward_bulk_ignore_apply_async` had **no** user
dependency at all (fully open, any caller including unauthenticated could reach them once past
routing) — 66757fde adds `_user: dict = Depends(require_roles(Role.ADMIN, Role.STEWARD))` to all
three. This is a real fix, not cosmetic — verified against the pre-image in `git show 209acf82`
(the routes in that commit's post-image still lacked the dependency) and the post-image in
`git show 66757fde`.

## Criterion 3 — no new roles invented; matrix consistent with BACKLOG-136/141; nothing weaker than the trap

**PASS — VERIFIED.**

`grep` over the diff and the current files shows only `Role.ADMIN`, `Role.STEWARD`,
`Role.PLANNER`, `Role.VIEWER` used — the `Role` enum in `security.py` is untouched by either
commit (not in either diff's file list). Matches BACKLOG-136 (do not invent KAM/PM/Ken/Wayne
roles without a CONSULT) and BACKLOG-141 ("Do not invent new Role enum values here").

BACKLOG-136's specific regression trap is about **historical-import**: pre-R1 it was
`_require_admin(X-User-Role)` (forgeable header), R1/R1b regressed it to authentication-only, and
"R2 must restore an equivalent or stronger check on these routes specifically." N-0038 restores
`require_roles(Role.ADMIN)` — a real, session-derived admin check — which is at least as strong as
the pre-R1 gate (stronger, since the role now comes from the DB user or a real session, not a
client-forgeable header in session mode). Verified in `cpor_historical_import.py`'s
`_require_cpor_historical_writer = require_roles(Role.ADMIN)` and confirmed live via
`test_allowed_role_passes_gate_and_denied_role_gets_403[...historical-import.../apply...]` (ADMIN
passes, VIEWER/PLANNER/STEWARD all get 403).

Case-lifecycle/settle/export/FX/promo-plan → `{PLANNER, ADMIN}` and payment-evidence →
`{STEWARD, PLANNER, ADMIN}` are new decisions beyond what either BACKLOG entry mandates verbatim;
BACKLOG-136 says this mapping is CONSULT territory ("Map KAM/PM/Ken/Wayne onto IAM ... CONSULT, do
not invent"). The commit message and an in-code comment attribute this specific choice to Warren
directly ("Warren 2026-09-21"), which satisfies the "commercial/domain calls are the operator's"
rule — this reviewer treats that as ASSERTED (I did not independently verify the 2026-09-21
conversation with Warren; I can only observe that the code says a decision was made and by whom).
Before this node these routes were `get_current_user`-only (any authenticated role could write),
so `{PLANNER, ADMIN}` / `{STEWARD, PLANNER, ADMIN}` are strictly narrower, not weaker.

BACKLOG-141's own regression trap ("Preserve admin-only for import-job bulk delete and Product
Master commit unless explicitly reopened") is out of this node's file scope: bulk-delete routes
live in `catalog.py` / `customers.py` / `distributors.py`, none of which appear in either commit's
diff — confirmed by `grep -rn "bulk-delete" apps/api/app/api/v1/endpoints/*.py`, which shows those
routes only in the untouched files. Not reopened, not weakened.

## Criterion 4 — tests

**PASS — VERIFIED.**
```
apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_rbac_n0038_cpor_roles.py apps/api/tests/test_session_gate.py -q
21 passed in 8.90s
```
`test_rbac_n0038_cpor_roles.py` is not in `conftest.py`'s `_WRITE_CAPABLE_TEST_MODULES` (verified
by grep) — it uses `TestClient` + dependency overrides + mocked DB sessions only, and reaches at
most a 422 (validation) past the role gate, never a real handler — consistent with "nothing writes
to cip."

Sample of existing, non-write-capable `test_cpor*.py` (26 of 28 files; excluded
`test_cpor_cases_api.py` and `test_cpor_historical_unit_c.py`, the two listed in
`_WRITE_CAPABLE_TEST_MODULES`):
```
apps/api/.venv/Scripts/python.exe -m pytest <26 test_cpor*.py files> -q
168 passed, 1 error
```
The one error (`test_cpor_settle_confirm_clone.py::test_settle_confirm_path_blocked_and_allowed_on_clone`)
is an environment/path issue unrelated to RBAC: its fixture calls
`ScriptDirectory.from_config(Config("alembic.ini"))` with a relative path that only resolves when
pytest's cwd is `apps/api/`; run from the repo root (as this review and the brief's "never `cd`"
rule require) it raises `CommandError: No config file 'alembic.ini' found` before any RBAC-relevant
code executes. Recorded as a limitation, not a criterion-4 failure.

## Criterion 5 — stub mode unaffected; nothing writes to cip

**PASS — VERIFIED / ASSERTED (design, unchanged).**

`apps/api/app/core/security.py` is not in either commit's diff (confirmed via `git show --stat`
above). `get_current_user`'s stub-mode fallback path (no bearer, `mode != "session"`) is untouched:
`_resolve_stub_app_user` first tries to match a real `app_user` row by id/email; on no match it
falls back to `normalize_role(x_user_role or Role.ADMIN.value)`, i.e. admin by default when no
`X-User-Role` header is sent. Stub-mode default-admin behavior is therefore unaffected by N-0038.
No test run in this review, and neither commit's own new test, touches the `cip` database
(confirmed: all `test_cpor*` runs used `cip_ns4_settle_clone`/mocks/test DBs per each file's own
fixtures; `test_rbac_n0038_cpor_roles.py` mocks `get_db`/`_sync_db` entirely).

## Independent look: any CPOR/shipment-evidence write reachable by a viewer, or any read gated by accident?

**None found within this node's file scope**, per the same route-introspection pass covering
every `/api/v1/cpor/**` and `/api/v1/shipment-evidence/**` route (all methods). All CPOR GETs are
authentication-only (viewer-readable); all CPOR/shipment-evidence writes require a non-viewer role.

Two things noted as **out-of-scope, pre-existing, not introduced or worsened by N-0038** (not
criterion failures — BACKLOG-141's own "Out of scope" line names this class as "the ~213 still-
unauthenticated non-CPOR writes (R3)"):
- `PUT /api/v1/imports/jobs/{job_id}/shipment-field-mapping` and
  `POST /api/v1/imports/jobs/{job_id}/shipment-validate` (different router, `imports.py`-family) —
  writes, `get_current_user` only, no role gate.
- `POST /api/v1/inbound-shipments/clear-all`, `DELETE /api/v1/inbound-shipments/{shipment_id}`,
  `PATCH /api/v1/inbound-shipments/{shipment_id}` — same, different router/file, untouched by
  either N-0038 commit.

Neither is a `/cpor` route nor a `shipment_evidence.py` (`/api/v1/shipment-evidence`) route, so
they sit outside this node's declared scope (BACKLOG-136 = CPOR, BACKLOG-141 = the
`shipment_evidence.py` panel specifically); flagging for the record, not as a fail.

Stub-mode header trust (when `X-User-Id` does not resolve to a real `app_user`, `X-User-Role` is
trusted verbatim) is a pre-existing trust boundary, documented by BACKLOG-136 itself ("stub mode
forges admin") and by a `conftest.py` comment explaining tests rely on it. `security.py` is
untouched by N-0038 — this is not a new gap introduced here, but it is worth naming for the
security-skeptic lens: in session mode (the production-intended mode), the header is never
consulted when a bearer is present or absent — role always comes from the DB session/user row, so
the risk is confined to stub/dev mode by construction.

## Dim verdicts

- **quality.testing** — pass. New RBAC test module (21 tests: exhaustive matrix diff, viewer-
  exclusion, read-stays-open, and real-dependency-chain behavioural pass/deny) plus 168 passing
  pre-existing CPOR tests unaffected by the change; one pre-existing, unrelated environment error.
- **quality.security** — pass. Role enforcement is real (session/DB-derived, not header-forgeable
  in session mode), viewer is excluded from every CPOR/shipment-evidence write, admin is always
  admitted by design, and the historical-import regression trap is honored (equivalent-or-stronger
  than the pre-R1 gate).
- **quality.threat** — pass, with a named limitation. The one bypass surface (stub-mode header
  trust) is pre-existing, documented, confined to non-session/dev mode, and not touched by this
  node; the three genuinely-ungated shipment-steward-bulk routes (a real threat: any caller could
  preview/apply/ignore steward actions) were found and fixed within this same node's commits (F1).
- **quality.observability — na.** This node only adds authorization dependencies (`require_roles`)
  that raise a standard `HTTPException(403)`; it added no new state, side effect, or long-running
  path that would need new logs/metrics/traces, and touched no existing observability surface. No
  logging, alerting, or dashboard change was expected or found in either commit's diff.
- **verification.referent** — pass. Every material claim above was re-executed in this session
  from a fresh route-introspection script (not the implementer's), fresh `git show` reads of both
  commits, and fresh pytest runs — not taken from any implementer report (which was not read, per
  the brief).

## Overall verdict: VERIFIED

## Failed criteria
(none)

## Limitations
- `test_cpor_settle_confirm_clone.py::test_settle_confirm_path_blocked_and_allowed_on_clone` errors
  on `alembic.ini` relative-path resolution when run from the repo root; environment/path issue,
  unrelated to RBAC, not exercised to a pass/fail conclusion in this review.
- The specific `{PLANNER, ADMIN}` / `{STEWARD, PLANNER, ADMIN}` role choices for case-lifecycle,
  settle, export, FX, promo-plan and payment-evidence writes are ASSERTED as Warren's decision (per
  commit message and code comment) rather than independently confirmed with the operator directly.
- Browser/UI verification was not performed (not required by this brief; "No browser needed").
- Did not exhaustively test the stub-mode header-trust fallback behaviorally (asserted from reading
  unchanged code in `security.py`, cross-checked against BACKLOG-136's own description of it).
