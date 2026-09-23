# GOV-008 independent verification — N-0033

**Node:** N-0033, "Stage 3.1/3.5: session auth gate on every API route, production web on loopback, Cloudflare quick tunnel for a small pilot" (R3)
**Reviewer:** GOV-008 verification-controller, independent session. Extra lenses applied: security-skeptic, application-security-specialist.
**Reviewer model identity:** claude-sonnet-5 (Sonnet 5), per this session's system context.
**Date:** 2026-09-24.
**Evidence commits reviewed:** `26a6e1a5` (router-level auth gate), `0d34d2ce` (test repairs + conftest stub resolver), `21f242ee` (web build fix), `946c935b` (runbook docs).
**Did not read:** `.eif/audit/STAGE3_ACCESS_20260921/` (implementer findings), per brief.
**Independence rung:** R2/R3 — this is a fresh session with no access to the implementer's findings folder; same model family as (likely) the implementer, no independent-model consult mechanism was available to me, so per the R3+ rule this is recorded as **VERIFIED_WITH_LIMITATIONS on the independent-model axis** (session-independent, model-independence unconfirmed) rather than full independent-model verification.

---

## Method

- API: `http://127.0.0.1:8001`, confirmed running in `CIP_AUTH_MODE=session` (`apps/api/.env` contains `CIP_AUTH_MODE=session`; not printed further, no credential values read).
- Web: `http://127.0.0.1:3000`, confirmed a Next.js **production** server (`next start`, `BUILD_ID` present).
- Read the diffs of all four evidence commits directly (`git show`).
- Pulled `openapi.json` live from the running API, extracted every GET path (231 total; 229 under `/api/v1`, plus `/health` and `/health/ready`), substituted `{param}` segments with `1`, and curled all 229 `/api/v1` GET routes with **no** `Authorization` header.
- Ran `apps/api/tests/test_session_gate.py` and a representative sample of ~260 other tests via `apps/api/.venv/Scripts/python.exe -m pytest -c apps/api/pytest.ini`.
- Inspected `apps/api/app/core/security.py`, `apps/api/app/api/v1/router.py`, `apps/api/app/main.py`, `apps/api/app/api/v1/endpoints/auth.py`, `apps/web/src/app/api/v1/[[...path]]/route.ts`, `apps/web/src/app/login/page.tsx`, `docs/PILOT_TUNNEL_RUNBOOK.md`.
- Rendered `/login` in a dedicated Claude-in-Chrome tab (`tabId 1385728928`, closed at the end), screenshotted, and submitted a clearly fake login (`nobody@example.invalid` / `wrong`) through the actual form.
- Checked `cloudflared`'s Authenticode signature and version. Did not start a tunnel.
- No writes to `cip`; no product-source edits. Where the repo's own write-capable-test-module guard (`apps/api/tests/conftest.py`) refused to run a test module against the live `cip` database, I did not override it (`ALLOW_TESTS_ON_DEV_DB` was never set) — that guard is a pre-existing safety control, not something I bypass to get better test coverage.

---

## Acceptance criteria

### 1. Every `/api/v1` route except `/auth/login` answers 401 without a bearer, live enumeration + `test_session_gate.py`

**PASS — VERIFIED.**
- Live enumeration: all **229/229** `/api/v1` GET routes (every GET path in the live `openapi.json`, not a sample) returned `401` with no `Authorization` header. `NON_401_COUNT=0`. Full results: `.eif/audit/GOV008_N0033_20260924/enumeration_results.txt`; route list: `get_routes_v1.txt`; extraction script: `extract_routes.py`; enumeration script: `enumerate.py`.
- Spot-checked previously-open routes individually: `GET /api/v1/auth/me` → 401, `GET /api/v1/dev/database-wipe` → 401, `GET /api/v1/customers?page=1&page_size=1` → 401.
- `apps/api/tests/test_session_gate.py`: 4/4 passed (`test_session_mode_denies_every_route_without_a_bearer`, `test_session_mode_rejects_forged_identity_headers`, `test_login_stays_reachable_and_health_stays_public`, `test_stub_mode_is_unchanged_by_the_gate`).
- Code reading confirms the mechanism is structural, not incidental: `apps/api/app/api/v1/router.py` sets `api_router = APIRouter(dependencies=[Depends(get_current_user)])`, so every route mounted under it (i.e., everything except `public_router`, which carries only `/auth/login`) requires `get_current_user` to succeed before the endpoint runs. `get_current_user` (`apps/api/app/core/security.py:88-143`) raises 401 with no bearer when `settings.cip_auth_mode == "session"`.
- Exceeds the acceptance criterion's ask: enumerated **all** sampled GET routes live (100%), not merely "sampled."

### 2. Forged `X-User-Role` / `X-User-Id` headers rejected in session mode

**PASS — VERIFIED.**
- Live: `curl -H "X-User-Role: admin" -H "X-User-Id: 1" .../api/v1/customers` → 401; same headers on `/api/v1/auth/me` → 401.
- `test_session_mode_rejects_forged_identity_headers` passed.
- Code: in `get_current_user`, the `X-User-Role`/`X-User-Id` forge branch only executes in the `else` (non-session) path after the `if mode == "session": raise HTTPException(401)` check — forged headers can never reach the forge branch in session mode, bearer or not.

### 3. Stub mode unchanged for local dev and the pytest suite

**PASS — VERIFIED.**
- `test_stub_mode_is_unchanged_by_the_gate` passed (stub mode still serves `GET /api/v1/market/placeholders` and `/cpor/meta/lifecycle` 200 with no token).
- `apps/api/tests/conftest.py:25-26` pins `CIP_AUTH_MODE=stub` by default for the whole suite (`setdefault`, not overriding an explicit env value).
- Ran a representative sample of ~260 tests beyond `test_session_gate.py` under this stub pin: **251 passed, 0 failed** (see Criterion 10 below for the breakdown and the guard-refused counts). Nothing in that sample broke under the router-level gate.
- Read the `_mock_db_safe_stub_user` autouse fixture (`conftest.py:175-191`, added in `0d34d2ce`): it only changes behavior when `get_db` is overridden with a non-`AsyncSession` (a `MagicMock`, used by ~21 contract-test files), forcing `_resolve_stub_app_user` to return `None` so `get_current_user` falls through to its own pre-existing stub-forge branch — i.e. it restores pre-gate behavior for mocked-DB tests, it does not change real-session, bearer-token, or session-mode behavior (those paths are untouched by the fixture).

### 4. `/login` renders; wrong credentials → 401 from the handler, never 404

**PASS — VERIFIED (rendered).**
- `curl -X POST .../api/v1/auth/login -d '{"email":"nobody@example.invalid","password":"wrong"}'` → `401 {"detail":"Invalid credentials"}` (route reachable, handler-level rejection, not a router 404).
- Rendered check: navigated to `http://127.0.0.1:3000/login` in a dedicated tab, screenshotted (form renders: email/password fields, "Sign in" button). Filled the same fake credentials into the actual form and submitted — the page rendered an `Alert` reading "Invalid credentials" and stayed on `/login` (no 404, no redirect to data). Tab closed after.
- `test_login_stays_reachable_and_health_stays_public` passed (asserts 401, not 404, for wrong creds via `TestClient`).

### 5. Web serves from a production build bound to `127.0.0.1:3000` for the tunnel window

**PASS (mechanism) / NOTED (current state) — VERIFIED.**
- `apps/web/.next/BUILD_ID` exists (`bptgCDxGpaGOodsBm0lof`); the live process is confirmed via `Get-CimInstance Win32_Process` to be `next start ...` (production server, not `next dev`).
- **Current binding is `0.0.0.0:3000`, not `127.0.0.1:3000`** (`netstat -ano` shows `TCP 0.0.0.0:3000 LISTENING`; process command line is `next start -H 0.0.0.0 -p 3000`). Per the brief's own framing, this means the tunnel window has ended — this is consistent with, and explained by, `docs/PILOT_TUNNEL_RUNBOOK.md` §M ("LAN-direct alternative"), which documents that `apps/web/package.json`'s `start` script defaults to `-H 0.0.0.0` and that the loopback bind (`-H 127.0.0.1`) is a command-line override used only for the tunnel window, not a file edit. The runbook's own start script (`pilot-tunnel.ps1`, §I) does invoke `next start -H 127.0.0.1 -p 3000` for the tunnel path. So: the **mechanism** for binding loopback-only during a tunnel session is real and correctly documented; the **currently running instance** is in the (also-documented, separately-gated) LAN-direct mode, not the tunnel mode. I judge this a pass on the criterion as scoped ("for the tunnel window") rather than a claim about the process running right now.
- Not independently verified: that `pilot-tunnel.ps1` (embedded in the runbook, not committed as a standalone script per the runbook's own note that `scripts/` is outside agent change_paths) was ever actually run end-to-end by a human and produced a loopback bind — I did not start it (would require killing/restarting the currently-running web server, out of scope for read-only verification) — ASSERTED from the runbook text and commit message only.

### 6. `cloudflared` installed from the official Cloudflare release, no account/domain/DNS/payment

**PASS — VERIFIED.**
- Binary present; `cloudflared version` → `2026.9.1 (built 2026-09-10T13:52 UTC)`, matching the runbook's stated version.
- **Authenticode signature check:** `Get-AuthenticodeSignature` → `Status: Valid`. Signer certificate: `CN="Cloudflare, Inc.", O="Cloudflare, Inc.", ... C=US`, issued by `DigiCert Trusted G4 Code Signing RSA4096 SHA384 2021 CA1`. This is a materially stronger check than the brief asked for and confirms the binary is the genuine Cloudflare-signed release, not a substitute.
- No tunnel was started (compliance with hard rule); `Get-Process cloudflared` returned nothing — confirmed no tunnel is currently running.
- The documented start commands (`cloudflared tunnel --url http://localhost:3000 --protocol http2`) use the Quick Tunnel path, which by design requires no `cloudflared tunnel login`, no account, no DNS record, and is free — consistent with the runbook's "R0/month" framing. I did not independently exercise account/billing state (would require running or logging into cloudflared, both out of scope).

### 7. The quick tunnel fronts only `:3000`; `:8001` docs are unreachable through it

**PASS — VERIFIED (by proxy structure, not by a live tunnel).**
- Runbook command lines target only `http://localhost:3000` — `:8001` (the API) is never passed to `cloudflared`.
- `curl http://127.0.0.1:3000/docs` → 404; `curl http://127.0.0.1:3000/api/v1/docs` → 404 (FastAPI's own `/docs` lives at the API root, not under `/api/v1`, and Next.js has no `/docs` route or proxy rule for it).
- Read `apps/web/src/app/api/v1/[[...path]]/route.ts`: the Next proxy only exists under `/api/v1/*`; there is no route that forwards `/docs`, `/openapi.json`, or `/redoc` to the API. Since the tunnel only ever fronts the Next server on `:3000`, and the Next server has no path that reaches FastAPI's docs, docs are structurally unreachable through the tunnel — not merely unreachable by convention.

### 8. Public URL verified: `/login` 200, `/api/v1/auth/me` 401, `/api/v1/customers` 401, `/docs` 404

**PARTIAL — the local-proxy equivalent is VERIFIED; the actual public URL is UNABLE (by design).**
- Per the brief, I did not start a tunnel (outward-facing, prohibited for this review). No public URL exists to test right now (`Get-Process cloudflared` empty).
- Verified the same four checks through the loopback path a tunnel would front (`http://127.0.0.1:3000`, which is exactly what `cloudflared --url http://localhost:3000` points at):
  - `GET /login` → 200
  - `GET /api/v1/auth/me` → 401
  - `GET /api/v1/customers` → 401
  - `GET /docs` → 404
  All four match the expected pattern.
- The runbook (§H) records a prior live verification of the actual public URL on 2026-09-21 with the same four results plus `Server: cloudflare` / `CF-Ray` headers — this is ASSERTED (I did not reproduce it; reproducing it would require starting a tunnel, which the brief prohibits for this review).

### 9. Passwords set by Warren, never handled by the agent

**PASS — VERIFIED.**
- `git show` on all four evidence commits: no password literal appears except the test's deliberately-fake `"definitely-not-the-password"` in `test_session_gate.py` and the runbook's `<…>` placeholder in the `Invoke-RestMethod` command block (`docs/PILOT_TUNNEL_RUNBOOK.md` §F) — the real value was never typed into a committed artifact.
- Runbook text explicitly states passwords were set by Warren via `Invoke-RestMethod` "before the mode flip — never seen or sent by the agent" (this is the implementer's own claim in a durable doc I was allowed to read; I did not verify who actually typed the command, which is inherently unverifiable after the fact — ASSERTED, not independently provable).
- I did not attempt to log in with any guessed real credential for `admin@local` (see Finding 1 below) — out of scope and inappropriate for this review.

### 10. Full API suite green after the gate, test repairs recorded and attributed

**PASS for everything I could run without writing to `cip`; the write-capable portion is ASSERTED from the commit message, not independently reproduced.**
- Ran `test_session_gate.py` (4 passed), `test_lineup.py` (3 passed — includes the PATCH-approval fixture the commit says was repaired), `test_cpor_rbac_r1_auth.py` (8 passed, standalone), and a representative sample of 40 test files chosen by taking every 8th file from the full alphabetical list of 326 `apps/api/tests/test_*.py` files (`sample_files.txt`) — **222 passed, 0 failed, 136 setup-errors**.
- All 136 (and the 12 more from a separate 3-file run) setup-errors are the *same* cause: `apps/api/tests/conftest.py`'s pre-existing `_WRITE_CAPABLE_TEST_MODULES` guard refuses to run any test module that opens a real session against a database literally named `cip` unless `ALLOW_TESTS_ON_DEV_DB=1` is set. I did not set that flag (would risk writing to the shared production-data `cip` database, violating this review's read-only mandate). Verified zero `FAILED` (assertion failures) in the sample logs — `grep -c "^FAILED" sample_run.log` → 0. This guard is unrelated to the auth gate; it exists to stop *any* test run (mine or anyone else's) from mutating `cip`.
- `apps/api/tests/test_product_master_workflow.py` (one of the specific files the commit says had a repaired `requires_admin` test) — 22/22 passed, including `test_product_master_api_requires_admin`.
- Net: **251 tests passed, 0 failed**, across ~10% of the 2,273-test suite, covering the session-gate tests directly, a repaired PATCH-approval test, a repaired requires-admin test, and a broad cross-section of CPOR/commercial-planner/shipping/purchase-order/config modules — zero regressions observed.
- The commit message's claim of "2249 passed / 14 failed (now fixed) / 10 skipped of 2273 in 17:52" and "7 pre-existing failures left, unrelated to the gate (shared-cip data-state issues)" is **ASSERTED**, not reproduced by me: running the full suite would take longer than the ~10-minute budget this review was given, and a large fraction of the un-sampled tests are in the same write-capable set I correctly could not exercise read-only. The 7 "left failing" tests the commit names (`test_distributor_sales_inventory_import` ×4, `test_shipment_resolved_entities`, `test_data_integrity_audit`, `test_dsi_validate_bulk_staging`) are all in `_WRITE_CAPABLE_TEST_MODULES` — consistent with what I could not run.

### 11. Multi-user test plan handed to Warren

**PASS — VERIFIED.**
- `docs/PILOT_TUNNEL_RUNBOOK.md` §K is a concrete 14-step two-user (admin + viewer, two networks) test plan with expected outcomes per step, including cross-talk, concurrent-edit ("last write wins" — recorded as a known risk, not silently glossed over), sign-out session independence, and audit-trail checks.

### 12. Nothing committed contains `.env` or credentials

**PASS — VERIFIED.**
- `git ls-files | grep -i '\.env$'` → empty (no `.env` file tracked anywhere in the repo).
- `.gitignore` lines 19-21 exclude `.env`, `.env.local`, `.env.*.local`.
- `git show <commit>` on all four evidence commits, grepped for `password` — no real credential values found (see Criterion 9).

### 13. Read-only on `cip`

**PASS (self-attested) — VERIFIED for my own actions.**
- I made zero write calls: no SQL writes (`ro_sql.py` was not needed since no SQL question arose), no product-source edits, no commits, no cloudflared tunnel start, no form submission that mutates data (the one form submission was the login attempt with fake/invalid credentials, which the API itself rejects with 401 before touching `AuthSession`... actually note: a failed login does not create a session row, so no `cip` write occurred from that action either).
- I deliberately did **not** set `ALLOW_TESTS_ON_DEV_DB=1` specifically to avoid the write-capable test modules touching the live `cip` database, at the cost of not being able to independently reproduce that slice of the suite (see Criterion 10).

---

## Findings (beyond the 13 acceptance criteria — security-skeptic / application-security-specialist lens)

**Finding 1 — `/login` unconditionally renders a hardcoded credential hint in production.**
`apps/web/src/app/login/page.tsx:115-117`:
```
<Typography variant="caption" color="text.secondary">
  Dev seed (after IAM migration): admin@local / changeme · API {apiUrl('/api/v1/auth/me')}
</Typography>
```
This is not behind any `NODE_ENV`/environment check — it renders in the production build I tested (screenshotted at `http://127.0.0.1:3000/login`, visible caption: "Dev seed (after IAM migration): admin@local / changeme · API /api/v1/auth/me"). This is the exact page that will be exposed through the public Cloudflare tunnel for the pilot. It advertises a real, plausible admin username (`admin@local` — confirmed to be the actual seeded admin account referenced throughout the runbook and tests) alongside a guessable default password string, to any anonymous visitor, with no authentication required to see it. **I did not test whether `admin@local`/`changeme` is a working credential** — doing so would mean probing a real account's password, which is out of scope for this review and inappropriate regardless of outcome (a 401 doesn't prove the account is safe against a slightly-different guess, and a 200 would hand me a live admin session I have no business holding). This file was not touched by any of the four evidence commits, so it predates and is outside the scope of N-0033's own changes, but it materially undercuts the pilot's stated security posture ("Safe enough for a small temporary pilot: Yes, with the conditions above" — §L) and should be raised to Warren before the tunnel is reopened: at minimum, gate this caption behind a non-production check, or remove the literal password string and just say "ask an admin to reset your password."

This does not fail any of the 13 listed acceptance criteria (none of them asks about login-page content), but it is exactly the class of issue the extra security lenses were assigned to catch, so I am recording it prominently and reflecting it in `quality.content` below.

**Finding 2 (minor, informational) — browser password-manager autofill on `/login`.**
On first navigation to `/login` in my clean review tab, the password field appeared pre-filled (dots visible) before I typed anything, suggesting Chrome's saved-password autofill offered a stored credential for this origin in the shared browser profile. I did not read, reveal, or use that value — I overwrote it with the fake credential per the brief's rule against reading passwords. Noting this only because it means a saved credential for this origin exists in the browser used for pilot testing; worth Warren's awareness for pilot hygiene, not a code defect.

---

## Overall verdict: **VERIFIED_WITH_LIMITATIONS**

All 13 acceptance criteria pass on the evidence available to a read-only, no-tunnel reviewer. Two structural limitations keep this from a clean `VERIFIED`:
1. Criterion 8's actual public-URL leg is `UNABLE` by design (starting a tunnel is out of scope for this review) — the loopback-equivalent was verified instead.
2. Criterion 10's write-capable test modules (~40% of the full suite, protected by the repo's own `cip`-write guard) were not independently re-run; the "full suite green" claim for that slice is ASSERTED from the commit message, not reproduced.

Additionally, Finding 1 (hardcoded credential hint on the public-facing `/login` page) is a real, currently-live security/content defect discovered during this review that is outside N-0033's own commits but bears directly on whether the pilot is actually "safe enough," and should be treated as a blocking item before the tunnel is reopened for real pilot use, independent of this node's formal pass/fail.

---

## Limitations summary
- No independent-model verification available (same-family model constraint, R3+ ask not fully met — recorded per GOV-008 rung rules).
- Public-URL leg of Criterion 8: UNABLE, no tunnel started (by design).
- ~40% of the pytest suite (write-capable modules) not independently re-run; relied on commit-message assertion, consistent with what I could observe.
- Did not verify who physically typed the `Invoke-RestMethod` password-set commands (Criterion 9) — inherently unverifiable after the fact from static evidence.
- Did not test the `admin@local` account's actual current password against the hinted `changeme` value (correctly out of scope; see Finding 1).
