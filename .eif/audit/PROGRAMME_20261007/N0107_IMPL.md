# N-0107 implementation: supervisor holds the tunnel on a network that blocks port 7844

Run: RUN-20261008-N0107-IMPL (gov-001 implementation run; lenses platform-devops-engineer, reliability-sre-specialist, test-engineering-specialist). Risk R1, facet infra. Working tree on 1714b78d, uncommitted.
Handback: **blocked**. Self-validated only; GOV-008 verification must run under a different `--run`. No commit made (not authorised in this run).

## What changed (scripts/cip-supervisor.ps1 only)

The file also carries earlier uncommitted N-0101 changes (worker-only listing env, `ListingEnv`, status.json `env` block) from another run. Those are not part of N-0107.

N-0107 additions:
- Settings: `$TunnelBlockedDialErrors = 6` (two dial lines per cloudflared attempt, so about three failed attempts), `$TunnelBlockedRetryMinutes = 30`, `$TunnelLogTailBytes = 65536`.
- `Read-LogTail`: reads the last 64 KB of a log file with ReadWrite+Delete sharing, so cloudflared keeps writing. Drops the partial first line when the read starts mid-file, strips CR, and never throws.
- `Get-TunnelNetworkVerdict`: uses plain `Contains()` and no regex. A `Registered tunnel connection` line resets the count. If at least 6 lines contain both `dial tcp ` and `:7844: i/o timeout` since the last registered line (or since launch), the verdict is `port-blocked`. A registered line with fewer timeouts after it gives `connected`. Anything else is `unknown`.
- `Get-TunnelErrLogPath`: a tunnel this supervisor launched uses its own err log (`Start-Component` now records `ErrLog`). An adopted tunnel uses the newest `tunnel*.err.log`; rotated `.err.log.N` files are ignored.
- `Invoke-Tunnel`, when cloudflared is running and auth is closed:
  - `/ready` 200 ends any blocked episode and logs `port 7844 no longer blocked`. The normal checks then apply.
  - Otherwise, a `port-blocked` verdict sets state `blocked` with detail `network blocks tunnel port 7844 (outbound TCP); not restarting. Blocked since ...; next fresh attempt ...`, and the tunnel is not restarted.
  - Once `next fresh attempt` has passed, the supervisor makes one fresh launch (still through `Test-MayStart`), logged as `port 7844 blocked for 30 min; one fresh attempt`. Every launch inside an episode resets the clock to 30 minutes.
  - When the verdict is not `port-blocked`, the old 10-minute `/ready` and public-check restart rules apply unchanged.
- status.json `link` gains `blocked_reason` (only while the state is `blocked`), `blocked_since` and `next_fresh_attempt`.
- link.html shows a note under the link when `blocked_reason` is set, and styles a `blocked` row as `warn`.
- Nothing changed for wsl, redis, worker, api or web. The header comment documents the rule.

## Tests (self-run)

- Parse check (`Parser.ParseFile`) found 0 errors.
- `.eif/audit/PROGRAMME_20261007/N0107_detector_test.ps1` loads the functions from the script by AST without running the main loop. Output is in `N0107_detector_test_out.txt`. Re-run 2026-10-08 ~13:55 local against the current file: **38 PASS, 0 FAIL**.
  - Verdict:
    - The recorded blocked lines from this PC (8 timeout lines) give `port-blocked`.
    - The registered sample gives `connected`. It was written in cloudflared's INF format, because no registered line existed on this PC.
    - Mixed orders: timeouts then registered gives `connected`. Registered then 8 timeouts gives `port-blocked`. Registered then 4 timeouts gives `connected`.
    - Threshold edges: 5 lines give `unknown` and 6 give `port-blocked`.
    - Empty input, timeouts on another port, and `connection refused` all give `unknown`.
  - Read-LogTail: reads the whole small file, keeps the bounded 4 KB tail, drops the partial line, strips CR, reads while a writer holds the file, and handles a missing or null path.
  - Err-log selection works for both an own tunnel and an adopted one.
  - Invoke-Tunnel with stubbed I/O:
    - A blocked log with `/ready` 503 gives `blocked`, no restart, and a retry at about 30 min.
    - Three more cycles still bring no restart.
    - At 30 min there is exactly one fresh attempt (one stop), and it reaches the launch gate.
    - `/ready` 200 gives `healthy`, clears BlockedSince and does not restart.
    - With no 7844 timeouts, the old `/ready failing for 10 min` restart still happens, and 2 min of failure is still `unhealthy` with no restart.
  - link.html: `Get-LinkHtml` was loaded by AST and given a fake status. It shows the note with reason and next attempt, the blocked row is styled `warn`, and there is no note when the tunnel is not blocked. The real link.html is outside the repo and was not read.

## Live measurement (this PC, network that drops outbound TCP 7844)

The supervisor was restarted with the new code by the earlier session of this run, using `cip-supervisor-stop.ps1 -Restart`. The script was last modified at 09:51:29 local and the supervisor (pid 39976) started at 09:55:22 local. As of 13:53 local the API, web and worker show `adopted=False launches=1`. This continuation did not restart anything.

Supervisor log (local time):
- **Before** (old code), the same network: launches at 09:07, 09:17, 09:27, 09:38 and 09:48, each one `restarting (/ready failing for 10 min)`. That is six launches an hour, and every one changed the public link.
- **After**:
  - 09:56:18: launch 1.
  - 09:57:32: `cloudflared log shows 6+ dial timeouts to port 7844 and no registered connection; holding the tunnel`, followed by `starting -> blocked`. Detection took about 74 s after launch.
  - Fresh attempts followed at 10:27:44, 10:57:47, 11:27:58, 11:58:08, 12:28:11, 12:58:39 and 13:28:53, each about 30 min apart. Each went `starting -> blocked` within about 75 s.
  - Between attempts there was no restart, only public checks every 5 min (`/login 530` or `0`).
  - At 13:53 there had been 8 launches in about 4 h, against 6 an hour before. The tunnel showed state `blocked`, detail `network blocks tunnel port 7844 (outbound TCP); not restarting. Blocked since 2026-10-08T09:57:30; next fresh attempt 2026-10-08T13:58:55; /ready 503`.
- status.json `link` (read with `cip-supervisor-status.ps1 -Raw`): `blocked_reason` = `network blocks tunnel port 7844 (outbound TCP)`, `blocked_since` = `2026-10-08T09:57:30`, `next_fresh_attempt` = `2026-10-08T13:58:55`.
- **Normal path, measured live.** The network began allowing 7844 at some point between 13:30 and 13:59.
  - 13:59:02: `restarting (port 7844 blocked for 30 min; one fresh attempt)`, then launch 9 (pid 50724) and a new link at 13:59:11.
  - 13:59:43: `connection registered; port 7844 no longer blocked (blocked since 2026-10-08T09:57:30)`, then `starting -> healthy /ready 200`.
  - 14:00:17: public check `/login 200, /api/v1/auth/me 401`.
  - At 14:02:09 the status script showed the tunnel `healthy`, launches 9, public `/login=200 /api/v1/auth/me=401`, and local api/web all as before. status.json `link` showed `blocked_reason`, `blocked_since` and `next_fresh_attempt` all null.
  - The live data cannot tell whether the held process would have registered by itself, because the fresh attempt came first.
- Watch summary (status script `-Ports -Local -Public -Log 20`, at 13:53, 13:57, 13:58, 13:59 and 14:02): no restart while blocked, one fresh attempt at the scheduled time, and a return to normal as soon as `/ready` was 200.

## Ledger (run RUN-20261008-N0107-IMPL)

- The lease expired after the cut-off and was re-acquired (rev 1757).
- Recorded `evidence.add` for the supervisor script, the detector test and this file.
- Recorded `node.quality` reliability pass (first entry superseded after the live recovery) and observability pass.
- Moved `node.stage` to validate, then ran `node.lease.release`. The node ended at revision 10, stage validate, programme rev 1765.
- No `node.verification` or completion was recorded.

## Findings and limitations

1. OBSERVATION: each fresh attempt still changes the public link, now twice an hour instead of six times. This meets the criterion ("long back-off, e.g. 30 minutes"). A longer or growing back-off, or keeping the old process across the attempt, is a possible follow-up for Warren and is not in scope here.
2. LIMITATION: the registered-line sample in the unit test is constructed. The recovery path itself was observed live at 13:59:43, but through `/ready` 200 rather than the log verdict.
3. LIMITATION: link.html was checked through the generator function with a fake status, not by reading the rendered file outside the repo.
4. OBSERVATION: the tunnel start log line reports `CIP_LISTING_* present=False`, which is correct (N-0101 sends listing env to the worker only). It is not part of N-0107.
5. The verification rung is self-verification (R1 allows it). GOV-008 under a different run is still required before completion.
