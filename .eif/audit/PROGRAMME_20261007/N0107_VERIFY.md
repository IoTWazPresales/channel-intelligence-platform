# N-0107 GOV-008 verification

- Node: N-0107 "Supervisor recognises a network that blocks the tunnel port and stops churning the quick tunnel" (feature, R1, facet infra, stage validate rev 10 at start).
- Verification run: RUN-20261008-N0107-VER. Implementation run: RUN-20261008-N0107-IMPL (different run).
- Independence rung: **R2** — fresh-context subagent session, same model family (not a different model). Above the R1 requirement (same-session self-check allowed).
- Lens: GOV-008 verification-controller + reliability-sre-specialist.
- Verdict: **VERIFIED_WITH_LIMITATIONS** (all four acceptance criteria pass; limitations listed below).
- N0107_IMPL.md was used only as a pointer to the implementation test; every result below was re-executed or read live by this run.

## Scope note
`scripts/cip-supervisor.ps1` is uncommitted on 1714b78d (last commit touching it: ce13599b) and also carries N-0101 worker-env changes (WorkerListingEnv, ListingEnv, env block in status.json, header line about CIP_LISTING_*). Those are not part of this node and were not judged here. sha256 of the file under test: `81e1ae503cb58fd1a5e967d119bbe60621e399b55ddab9b149dd95f1b7180cca`; sha256 of `git diff -- scripts/cip-supervisor.ps1`: `de1f31010ae9b09377b3d0550303b1e17745253eb2fbef0ec12c81981a2fb8a9`.

## 1. Code review (git diff, N-0107 hunks)
OBSERVATION, from the diff and the full Invoke-Tunnel / New-LogPair / Test-MayStart / Write-Log source:

| Check | Result |
|---|---|
| Detector uses plain `Contains()` (no regex) | PASS. `Get-TunnelNetworkVerdict` uses only `$line.Contains('Registered tunnel connection')`, `Contains('dial tcp ')` and `Contains(':7844: i/o timeout')`. Ordinal, case-sensitive; matches cloudflared's real format (live registered line below). |
| Threshold | PASS. `$TunnelBlockedDialErrors = 6` (2 lines per failed attempt = 3 attempts); `if ($timeouts -ge $Threshold)`; passed from Invoke-Tunnel. |
| 'Registered tunnel connection' resets | PASS. Sets `$registered = $true; $timeouts = 0`, so only timeouts after the last registration count. |
| Blocked state holds without restart | PASS. On `port-blocked` with `$now -lt BlockedRetryAt`: `Set-State 'blocked'` then `return` before the stale-/ready and stale-public restart rules. Process kept, hostname kept. |
| One fresh attempt per 30 min | PASS. `$TunnelBlockedRetryMinutes = 30`; retry only when the clock passes `BlockedRetryAt`, through `Test-MayStart` (operator hold and back-off still respected); after every launch inside an episode `BlockedRetryAt = launch + 30 min` (also after a crash relaunch via the dead branch). `BlockedSince` is not reset by attempts. |
| /ready 200 ends the episode | PASS. `/ready 200` branch clears BlockedSince/RetryAt/Reason, logs "connection registered; port 7844 no longer blocked", and falls through to the unchanged healthy path. The log is not consulted when /ready is 200. |
| Log read is safe | PASS. `Read-LogTail`: last 64 KiB, `FileShare ReadWrite|Delete`, drops the partial first line, never throws. Each launch gets a fresh err log (`New-LogPair` rotates), so a new process starts with zero counted timeouts; adopted tunnels use the newest `tunnel*.err.log`. |
| No other behaviour changed | PASS. The old stale-/ready / stale-public restart block is textually the same, only re-indented under `if (-not $blockedRetry)`; it runs unchanged whenever the verdict is not `port-blocked` or /ready is 200. Other N-0107 additions are output-only: `blocked_reason` / `blocked_since` / `next_fresh_attempt` in status.json, the link.html note, `.blocked` CSS, `blocked` row styled `warn`. |

Minor observations (no criterion impact):
- O1. status.json `blocked_since` / `next_fresh_attempt` are written whenever an episode is open (also during the ~70 s 'starting' window of a fresh attempt), while `blocked_reason` is written only when the state is 'blocked'. Slightly inconsistent; link.html keys on the reason, so the page is correct.
- O2. The hold also applies when an already-connected tunnel loses 7844 (seen live at 14:30:51). If cloudflared were wedged rather than blocked, recovery would wait up to 30 min instead of 10. Accepted trade-off of the design; the back-off length is already Warren's open question.

## 2. Tests and mutation (re-executed by this run)
- Parse check: `[Parser]::ParseFile` on scripts/cip-supervisor.ps1 → **0 errors** (both harnesses).
- Implementation test `.eif/audit/PROGRAMME_20261007/N0107_detector_test.ps1` re-run: **38 PASS / 0 FAIL** (recorded blocked lines from this PC; registered lines synthetic).
- Own test `.eif/audit/PROGRAMME_20261007/N0107_verify_test.ps1` (new, independent): loads the product functions and the product's constants by AST, stubs `Get-Date` with a simulated clock and stubs I/O and launches, then drives `Invoke-Tunnel` for hours of 30 s cycles. **27 PASS / 0 FAIL**:
  - detector edges: threshold-1 → unknown; threshold → port-blocked; registered after 10 failed attempts → connected; `:17844:` and `.7844 ` not counted; upper-case REGISTERED not matched (ordinal).
  - A: 4 h on a blocked log → **7 launches** (09:30 … 12:30), minimum gap ≥ 30 min, only fresh-attempt restart reasons, hold logged once.
  - B: same 4 h, log without the 7844 pattern → **24 launches** (old 10-min rule unchanged), never 'blocked'.
  - C/D: re-arm to launch + 30 min after a fresh attempt and after a crash relaunch; BlockedSince unchanged.
  - E: /ready 200 with a stale blocked log → healthy, fields cleared, recovery logged once, 60 min with no launch.
  - F: registered then below-threshold timeouts → not blocked; then above threshold → new episode, no restart in the hold.
- Mutation (own), each applied with Edit, run against both harnesses, then reverted:
  - M1 threshold ignored (`-ge $Threshold` → `-ge 1`): implementation test **2 FAIL**, own test **3 FAIL**. Killed.
  - M2 restart while blocked (hold condition → `$false`): implementation test **6 FAIL**, own test **8 FAIL** (A: a launch every 30 s). Killed.
  - Revert: file sha256 and `git diff` sha256 identical to the baseline above; both harnesses green again (parse 0, failures 0). The running supervisor (pid 39976, started 09:55:22) parsed the file at start and was not restarted, so the short mutation window did not reach it.

## 3. Live, read-only (no restarts)
`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/cip-supervisor-status.ps1 -Ports -Local -Public -Log 80` at 14:37:01, plus `-Log 400` filtered to the morning, plus the read-only helper `.eif/audit/PROGRAMME_20261007/N0107_verify_live_read.ps1` (reads status.json, link.html and the newest tunnel err log in the supervisor's own folder; writes nothing).

Supervisor log, FACT (lines read this run):
- Old code: tunnel restarts "(/ready failing for 10 min)" at 09:17:24, 09:27:41, 09:38:01, 09:48:28 (launches 5–8 of the old supervisor) — confirms the ~10-min churn of criterion 1.
- 09:55:22 supervisor restarted with the new code (pid 39976). Launch 1 at 09:56:18; **09:57:32 "cloudflared log shows 6+ dial timeouts to port 7844 … holding the tunnel, next fresh attempt 10:27:30"**, state starting → blocked (74 s after launch).
- Fresh attempts, reason "port 7844 blocked for 30 min; one fresh attempt": 10:27:45 (launch 2), 10:57:50 (3), 11:27:59 (4), 11:58:08 (5), 12:28:12 (6), 12:58:40 (7, pid 35424), 13:28:55 (8), 13:59:03 (9, pid 50724). Between attempts only "public check" lines; no other restart. Each attempt returns to 'blocked' with `Blocked since 09:57:30` unchanged and next attempt = launch + 30 min.
- **13:59:43 "connection registered; port 7844 no longer blocked (blocked since 09:57:30)"**, starting → healthy /ready 200. Public checks 14:00:17 … 14:27:03: **/login 200, /api/v1/auth/me 401** (6 checks).
- **Launches count: tunnel launches=9** (1 initial + 8 fresh attempts in 4 h 3 min; old code would have made ~24).
- After the implementation report: 14:29:44 healthy → unhealthy /ready 503; **14:30:51 a new episode on the same pid 50724, no restart** (blocked since 14:30:51, next fresh attempt 15:00:51); 14:32:30 public 530/530.

Current state, FACT at 14:37–14:39:
- Public link `seeds-streaming-survivor-grades` **/login 530, /api/v1/auth/me 530** — NOT 200/401. The network is blocking 7844 again; this is the condition the node handles, not a defect. 200/401 was observed in the log from 14:00:17 to 14:27:03 only.
- Local: api /health 200, api /auth/me 401, web /login 200, web proxy /auth/me 401; wsl, redis, worker, api, web healthy throughout.
- status.json: `blocked_reason` "network blocks tunnel port 7844 (outbound TCP)", `blocked_since` 14:30:51, `next_fresh_attempt` 15:00:51, tunnel state blocked, launches 9.
- Rendered link.html (closes the implementation's limitation): blocked note div present, names the reason and the times, tunnel row `<td class='warn'>blocked</td>`.
- Live err log (tunnel.err.log, 75 lines): 1 real "Registered tunnel connection" line (11:59:11Z = 13:59:11 local, connIndex=0, protocol=http2) followed by 15 "dial tcp …:7844: i/o timeout" lines; the product detector on that tail returns **port-blocked** — the same decision the supervisor took at 14:30:51, now on a real registered line rather than a synthetic one.

## Verdict per acceptance criterion
| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | Observed old churn (6 launches, 10-min restarts) | PASS (corroborated) | Supervisor log 09:17–09:48 restarts every ~10 min with new links. |
| 2 | Detector, marks status.json and link.html, stops restarting, 30-min back-off, resumes when a connection registers | PASS | Code review; tests 38/0 and 27/0; mutations killed; live hold 09:57–13:59, fresh attempts every ~30 min, recovery 13:59:43, live status.json and rendered link.html carry the reason. |
| 3 | No other behaviour change; parse 0; unit test on recorded log lines | PASS | Old restart rule textually unchanged and still fires (B: 24 launches/4 h; implementation test old-rule cases); parse 0; detector on recorded blocked lines and on the live err log. |
| 4 | Measured live: no restarts while blocked; status shows the reason | PASS | 9 launches 09:56–13:59 all initial/fresh-attempt; second episode 14:30:51 held on the same pid; status.json/link.html/status script show the reason. |

## Limitations
- L1. R2 same model, not a different model.
- L2. Not observed: a held process recovering by itself without a fresh attempt (13:59 recovery came through the fresh attempt). Code path covered by tests (E). The episode open since 14:30:51 may show it before 15:00:51; not waited for.
- L3. Public link currently 530/530 (network blocks 7844 again); the operator-expected 200/401 is historical (14:00–14:27).
- L4. Link still changes about twice an hour while blocked (one per fresh attempt); a longer back-off is Warren's call (already open).

## Deferred finding (not N-0107)
- D1. `Write-Log` swallows every exception (`catch { }`, pre-existing). Launch 7 at 12:58:40 (pid 35424) has its "started", "blocked -> starting" and "public link is now" lines missing from supervisor.log, though the launch counter (9) and the 12:59:54 line for pid 35424 show it happened. Supervisor log can drop lines silently; observability gap outside this node.

## Files
- Written by this run: this report; `.eif/audit/PROGRAMME_20261007/N0107_verify_test.ps1`; `.eif/audit/PROGRAMME_20261007/N0107_verify_live_read.ps1`; ledger payloads `N0107_ver_*.json`.
- Product: no change (temporary mutations reverted; hashes identical). No restart, no commit.
