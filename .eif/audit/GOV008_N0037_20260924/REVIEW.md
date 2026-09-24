# GOV-008 independent review — N-0037: Stage 3.4 login rate limit and lockout

Reviewer model: Claude Sonnet 5 (`claude-sonnet-5`), independent session, fresh context (no read of
`.eif/audit/PROGRAMME_20260924/n0037/IMPL.md` or implementer stage notes). R2 node; another-session
independence applies (self-model, not another model — see verification.referent below).

Evidence base: `git show 76316728` (full diff read: `apps/api/app/core/login_throttle.py` new file,
`apps/api/app/api/v1/endpoints/auth.py`, `apps/api/app/core/config.py`, `apps/api/app/core/password.py`,
`apps/api/tests/conftest.py`, `apps/api/tests/test_auth_login_throttle.py`), running API on
`http://127.0.0.1:8001` (live POSTs), `apps/web/src/app/api/v1/[[...path]]/route.ts` (full read),
`apps/api/.venv/Scripts/python.exe -m pytest ...` run.

## AC1 — Throttled per account and per client address; limit/window are config, not literals

**PASS — VERIFIED.**
- `apps/api/app/core/config.py`: `cip_login_throttle_enabled` (default `True`),
  `cip_login_max_failures_per_account` (default `5`), `cip_login_max_failures_per_address`
  (default `20`), `cip_login_throttle_window_seconds` (default `900`) — all `Settings` fields
  read from env (`CIP_LOGIN_*`), not literals in the throttle code. `LoginThrottle._window_and_limits`
  reads `get_settings()` on every call, so live config changes apply without redeploying the throttle.
- `login_throttle.check(account, address)` checks the account key (`acct:<email>`) before the
  address key (`addr:<address>`), sliding-window via a `deque[float]` of failure timestamps pruned
  against `now - window` (`apps/api/app/core/login_throttle.py:97-118`).
- Live: 5 wrong-password POSTs to `wronguser1@example.invalid` returned `401` each; the 6th
  returned `429` with `Retry-After: 882` (window 900s, ~18s elapsed) — account throttle fires at
  the configured limit, not before.
- Unit test `test_defaults_are_settings_not_literals` asserts the four settings values; passed in
  the run below. `test_per_address_throttle_across_accounts` sets
  `CIP_LOGIN_MAX_FAILURES_PER_ADDRESS=3` via env and shows the address key locks after 3 distinct
  emails' failures and then blocks a fresh, unlocked account too — confirms the address key is
  independent of the account key and config-driven.

## AC2 — 429 + Retry-After; correct password refused during lockout; success resets the counter

**PASS — VERIFIED (429/Retry-After/refusal live + by test; reset by test only).**
- Live: 6th attempt on the locked account returned `HTTP/1.1 429`, header `retry-after: 882`,
  body `{"detail":"Too many login attempts. Try again later."}`.
- `login()` calls `login_throttle.check()` **before** loading the user or calling
  `verify_password` (`auth.py:99-105`), so a blocked key is refused pre-verification regardless of
  password correctness. Unit test `test_lockout_refuses_correct_password_until_window_passes`
  confirms a correct-password attempt against a locked account still gets `429`, then succeeds
  (`200`) once the clock is advanced past the window.
- Reset-on-success: `auth.py:120-121` calls `login_throttle.reset_account(email)` only in the
  success branch; `reset_account` pops only the `acct:` key, not `addr:` (documented rationale:
  a valid login on one account must not clear an address that is spraying other accounts).
  Unit test `test_successful_login_resets_account_counter` confirms 4 failures + 1 success + 4 more
  failures all stay under the 5-limit (i.e., the account counter truly zeroes). I could not test
  this live without a real password (task rule: never use a real password), so this criterion is
  VERIFIED via the automated test only, not live.

## AC3 — No enumeration: unknown-user and wrong-password responses indistinguishable in status and body

**PASS — VERIFIED (live + test).**
- Code: `login()` always calls `verify_password(body.password, user.password_hash if user else
  DUMMY_PASSWORD_HASH)` before branching on `user is None or not user.is_active or not
  password_ok`, so unknown-user, inactive-user and wrong-password all take the identical
  `401 {"detail": "Invalid credentials"}` path with no distinguishing branch
  (`auth.py:113-119`). `DUMMY_PASSWORD_HASH` (`password.py:33-35`) is a well-formed
  `pbkdf2_sha256$260000$<salt>$<64 zero hex chars>` string generated once at import, so the
  unknown-user path pays the same PBKDF2 (260,000 iterations) cost as a real wrong-password check
  — this also closes the timing side channel, not just the status/body one.
- Live: `unknownA@example.invalid` and `unknownB@example.invalid` (two never-used fake emails)
  each returned `HTTP/1.1 401`, identical `content-length: 32`, identical body
  `{"detail":"Invalid credentials"}`, identical headers aside from `date`. Also verified structurally
  from the lockout path: the 429 response for the locked known-email account and the 429 body shape
  is the same "Too many login attempts..." text regardless of account vs. address reason
  (`_too_many_attempts`, `auth.py:91-97` — single helper, one body for both throttle reasons and
  both known/unknown accounts).
- Unit test `test_unknown_user_and_wrong_password_are_indistinguishable` additionally verifies via
  a spy that `verify_password` is called with `DUMMY_PASSWORD_HASH` for the unknown case (so the
  PBKDF2 work truly happens) and that a locked unknown email and a locked real account produce the
  same status, body and Retry-After.

## AC4 — Tests cover throttle, reset and non-enumeration; stub mode unaffected

**PASS — VERIFIED.**
```
apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_auth_login_throttle.py \
  apps/api/tests/test_session_gate.py apps/api/tests/test_auth_password_roles.py -q
......................                                                   [100%]
22 passed in 28.14s
```
`test_auth_login_throttle.py` (11 tests) covers: settings-not-literals, account throttle +
Retry-After decay, lockout refusing a correct password + reset after window, success resets
counter, per-address throttle across accounts (config override), non-enumeration (status/body/
timing), structured logging without raw email, throttle-disable flag, stub-mode routes unaffected
by a locked auth-mode account (`test_stub_mode_gated_routes_unaffected_by_lockout` — 6 failed
`/auth/login` attempts, then confirms `GET /api/v1/market/placeholders` still `200`s), and 7
parametrized cases for `client_address` XFF trust. `test_session_gate.py` and
`test_auth_password_roles.py` (existing suites) still pass, i.e. no regression from the new
pre-check / dummy-hash path. Tests use an in-memory fake `AsyncSession` (`_FakeSession`), no real
DB — consistent with AC5.

## AC5 — Nothing writes to cip

**PASS — VERIFIED.**
`git show 76316728 --stat` touches only `auth.py`, `config.py`, `login_throttle.py`, `password.py`,
`conftest.py`, `test_auth_login_throttle.py` — no migration, no model, no new table. `LoginThrottle`
holds state in an in-process `dict[str, deque[float]]` (`login_throttle.py:76-79`) behind a
`threading.Lock`, explicitly documented as in-memory/per-process ("must not depend on Redis being
up"). The only DB touch in the modified `login()` path is the pre-existing `select(AppUser)` read
and, on success, the pre-existing session-row insert — both unchanged by this diff. Test suite uses
a fake session (no real DB connection). No SQL was needed for this review.

## Web proxy / client-address derivation — security finding (bears on AC1's "per client address")

`apps/web/src/app/api/v1/[[...path]]/route.ts:102-107` builds the upstream request by copying
**every** inbound header except a small hop-by-hop set (`connection`, `keep-alive`,
`proxy-authenticate`, `proxy-authorization`, `te`, `trailers`, `transfer-encoding`, `upgrade`,
`host`) — `x-forwarded-for` is not in that set, and the route never sets or appends its own XFF
value. Read in full; confirmed no other file in `apps/web` touches `x-forwarded-for`
(`grep -ri x-forwarded-for apps/web` → no matches outside intent I already reviewed).

`client_address()` (`login_throttle.py:47-63`) trusts XFF whenever `request.client.host` (the TCP
peer) is loopback, and takes the right-most hop. In the deployed topology described in the code
comment (Next same-origin proxy on loopback + API on :8001), the API's peer for every proxied
request **is** the Next process, i.e. always loopback — so XFF is always trusted from the browser's
perspective, and the browser (or any HTTP client that talks to the Next origin, e.g. a script,
before any auth) fully controls the value the API uses as the address-throttle key, because Next
forwards it verbatim.

Consequence: the per-address limit (AC1's "per client address") is trivially bypassable by an
attacker rotating a fake `X-Forwarded-For` per batch of guesses — defeating credential-stuffing
protection at the address layer (the per-account 5-limit still holds per target account regardless,
since it does not depend on address). It is also spoofable in the other direction: an attacker can
set `X-Forwarded-For: <victim-NAT-IP>` and spray wrong passwords against arbitrary (including
unknown) accounts to drive that address's failure count to the configured limit, locking out real
users who share that IP (e.g., a corporate NAT) from all logins for the window (default 15 min) —
a denial-of-service against innocent users that does not require any correct guesses.

This is not a silent gap: the code comment in `login_throttle.py:53-56` documents it explicitly
("Next 15 only fills X-Forwarded-For when the client did not send one, so a client can choose this
value; per-account limits do not depend on it") and the account-level limit is unaffected. I treat
this as a **residual risk to record, not a criterion failure** — AC1 says "per client address" is
throttled, which it literally is (the code path exists and fires, as shown live for the
default-simulated case), and the implementer's own note already scopes the limitation. But it means
the per-address control provides real protection only when the Next proxy itself is behind an
infra layer that strips/overwrites client-supplied XFF (e.g., a load balancer or CDN doing this
before Next) — there is no evidence in this diff or `route.ts` that such a layer exists or is
required by config/docs. I could not verify the production topology (out of scope of this repo) so
I record it as a limitation rather than a fail.

I did not use additional live-request budget to demonstrate the XFF-spoofing bypass empirically
(would require attempts against the login endpoint through the web proxy on :3000, consuming
failed-attempt budget under the 8-attempt cap and risking address lockout); the finding is based on
full reads of both files plus the seven parametrized `test_client_address_trusts_xff_only_from_loopback`
cases, which confirm the trust/no-trust boundary exactly as described (loopback peer + XFF present →
trusted; non-loopback peer → XFF ignored). Labelled ASSERTED for the live browser-exploit path,
VERIFIED for the code behavior itself (source read + passing unit tests).

## quality.observability — are lockouts logged, without raw email/password?

**PASS.** `log_throttle_event()` (`login_throttle.py:172-183`) logs a structured warning with
`event` (`"lockout"` | `"throttled"`), `reason` (`"account"` | `"address"`), `account_key` /
`address_key` (HMAC-SHA256 truncated to 16 hex chars, keyed by a per-process random pepper
generated with `secrets.token_bytes(32)` — not reversible, and not stable across process restarts,
so it cannot be correlated to a real email/IP outside the log stream, and cannot be used to
brute-force the pepper offline either), and `retry_after_s`. Never logs `body.password` or the raw
email/address. Verified by `test_lockout_and_throttle_logged_without_raw_email`: asserts the two
expected event names, that `reason == "account"`, that `account_key` matches the same
`log_key(EMAIL)` helper, and that neither the raw email nor the raw password substring appears in
`record.getMessage()`.

Gap: only the failure that *crosses* a threshold is logged (`record_failure` only appends to
`locked` when a key transitions from under-limit to at-limit); the 1st–4th failed attempts on an
account are not logged at all, and non-throttled 401s (wrong password, unknown user) produce no
log line anywhere in the reviewed diff. That means there is no log-based way to see "someone is at
attempt 3 of 5" or to alert on distributed low-and-slow guessing that never crosses a single
account's threshold (e.g., 1 guess per account across thousands of accounts from one spoofed
address, given the AC1 finding above). This is a reasonable, deliberate scope boundary for this
node (log volume on every failed login could itself be a concern) but is a real gap for detecting
credential-stuffing campaigns that stay under threshold — recorded as a limitation, not a failure,
since no acceptance criterion requires per-attempt audit logging.

## quality.security / quality.threat — is the threat model sound; residual risks

Sound for its stated scope (per-account credential stuffing/guessing against a single account from
a single or few addresses): pre-check-before-verify ordering, constant-shape dummy-hash timing
defence, HMAC-not-reversible log keys, in-memory-only state (no PII persisted to `cip` or disk),
config-driven limits, bounded memory (`_MAX_TRACKED_KEYS = 10_000` with an LRU-ish sweep) against an
attacker spraying keys to exhaust memory.

Residual risks (beyond the XFF spoofing/framing risk above, already covered):
1. **Single-process, in-memory counters.** Documented in the module docstring as intentional
   ("API runs as a single process today"). If the API is ever run with multiple worker processes
   (e.g. `uvicorn --workers N` or multiple pods behind a load balancer) without a shared store,
   each worker has its own counter, so the effective per-account limit becomes
   `limit × worker_count` and an attacker distributed across workers evades the throttle. I did not
   check the actual deployment/process-manager config for this node (out of scope for a code+API
   review); recorded as a limitation to verify against `ENVIRONMENT_POLICY.md` / deployment config
   before relying on this for a multi-worker or multi-instance deployment.
2. **Process restart clears all counters** (also documented) — an attacker who can trigger or wait
   out a restart gets a fresh window. Acceptable for the stated scope (this is a defense against
   sustained brute force, not a hard security boundary) but worth naming as residual risk.
3. **Address-block collateral damage even without spoofing:** a shared NAT/VPN egress IP with ≥20
   failed logins across any accounts within 15 minutes locks out every user behind that IP,
   including ones not involved in the failures — an inherent trade-off of IP-based throttling, not
   a defect, but real for an enterprise-B2B product where many users may share an office egress IP.
4. **No CAPTCHA / no account notification on lockout** — out of scope for this node's acceptance
   criteria, noted only as a possible follow-on hardening, not a gap in this node.

None of these are criterion failures; AC1–AC5 as written are met. They are recorded as residual
risk for the risk register / next-node consideration, consistent with "no self-authorized scope
expansion."

## Live-check budget note

Per the task's 8-failed-attempt cap: I used 7 failed `/api/v1/auth/login` POSTs total from
127.0.0.1 (5 to trip `wronguser1@example.invalid`'s account lockout, 1 more on the same account to
observe the 429/Retry-After, 1 each for `unknownA@example.invalid` and `unknownB@example.invalid`
to compare bodies) — leaving 127.0.0.1's address counter at ~7/20, well clear of that address's own
lockout. I did **not** live-test: (a) success-resets-counter (would require a real password, which
the task rules disallow), (b) the XFF-spoofing bypass end-to-end through the :3000 web proxy (would
consume more of the failed-attempt budget and could push the shared 127.0.0.1 address counter
toward its own limit, especially stacked on top of any other concurrent review activity against the
same API instance), (c) Retry-After decreasing over real wall-clock time (would need to wait out
part of the 15-minute window). All three are covered by passing automated tests instead, and are
labelled accordingly above.

## Overall verdict: VERIFIED_WITH_LIMITATIONS

All five acceptance criteria PASS with direct evidence (live requests for 1–3, the required pytest
run for 4, static/diff inspection for 5). The verdict is "with limitations" rather than plain
VERIFIED because of: the XFF-trust/spoofing residual risk on the per-address leg of AC1 (real, not
a criterion failure, already partly self-documented by the implementer), the single-process/
in-memory counter scaling caveat, and the untested (live) success-reset path due to the
no-real-password rule. None of these are FAILs; they are limitations an operator/architect should
see before relying on the per-address leg specifically as an anti-abuse control in a multi-instance
or non-loopback-proxy deployment.
