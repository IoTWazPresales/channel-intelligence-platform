# N-0101 GOV-008 verification

- Node: N-0101 (N-0085 U1: listing polling under the supervisor, restock, dead-link back-off, per-site 403/429 pause, run time limit). Stage `validate`, rev 11, R2, facets api/infra.
- Verification run: `RUN-20261008-N0101-VER`. Implementation run: `RUN-20261007-N0101-IMPL`.
- Independence rung: **R2, fresh context** (separate subagent session, same model family). Not a different model. Every result below was re-executed in this run; `N0101_IMPL.md` was used only to know which claims to test.
- Date: 2026-10-08, about 09:00 to 09:25 local (SAST).
- Lenses: GOV-008 verification-controller, reliability-sre-specialist, test-engineering-specialist.

## Verdict

**FAILED (narrow, one defect).** All eight acceptance criteria hold in the running worker. One implementation claim is false (D1): the per-site pause never uses Redis. `default_site_pause_store()` always returns the process-local store because of an import error that is caught and hidden. The fix is one line plus one test. Overnight polling did not run because the laptop was asleep (F1). That is about the host, not a code defect, but it limits what "Checked on a schedule" means.

| # | Criterion | Verdict |
|---|---|---|
| C1 | Supervisor's worker env sets CIP_LISTING_CAPTURE_SCHEDULE and CIP_LISTING_LIVE_FETCH; status shows both | VERIFIED |
| C2 | A beat run records new Takealot and Evetech observations on cip | VERIFIED_WITH_LIMITATIONS (F1: no runs 18:18 to 08:54, host asleep) |
| C3 | out_of_stock seen in stock returns to active (restocked); out_of_stock keeps being polled | VERIFIED_WITH_LIMITATIONS (restock not seen live) |
| C4 | consecutive failures drive dead-link back-off; 403/429 pauses only that site (1 h doubling to 24 h) and is recorded | VERIFIED_WITH_LIMITATIONS (back-off live; pause unit-level only; **D1**) |
| C5 | Oldest-due first, mixes retailers, stops at 10 min | VERIFIED |
| C6 | "Checked on a schedule" copy is true | VERIFIED_WITH_LIMITATIONS (true only while the host is awake, F1) |
| C7 | Conforms to N0085_DESIGN.md, D-0061 and D-0063 (browser UA, spacing, pause, time limit, no evasion) | VERIFIED (D1 weakens the pause across processes; F3 Amazon CAPTCHA-at-200 already deferred) |
| C8 | Tests green on touched areas; tsc 0 and eslint clean on changed files | VERIFIED for Python; tsc and eslint not applicable (N-0101 changed no web file); eslint run attempt UNVERIFIED (see below) |

Ledger kinds: **behavioral = pass** (criteria behaviours reproduced; limitations recorded). **referent = fail** (the IMPL claim "the site pause is in Redis" / "Falls back to a process-local store when Redis is unreachable" is false as built).

## D1 (defect, must fix before complete): the site pause never reaches Redis

- `apps/api/app/services/listing_capture/site_pause.py`, `default_site_pause_store()` runs `from app.core.config import settings`. `app.core.config` has no `settings`; it exports `get_settings()` (line 194, `@lru_cache`). The `ImportError` is caught by `except Exception` and logged as "Redis unavailable".
- Reproduced (venv python, read-only): `from app.core.config import settings` raises `ImportError: cannot import name 'settings'`. With `get_settings().redis_url` (host localhost, port 6379, db `/0`), `redis.Redis(..., socket_connect_timeout=0.5).ping()` returns True in 0.04 s, but `default_site_pause_store()` returns `MemorySitePauseStore` and logs "Redis unavailable".
- Live: the worker log shows `listing capture: Redis unavailable; site pauses kept in this process only` on **every** run (17:00, 17:30, 18:00, 21:02, 08:55, 09:02). Redis component healthy (`PING -> +PONG`) throughout.
- Effects:
  - A pause set by the worker is invisible to `POST .../listing-capture/poll`, which runs in the API process. A manual poll can fetch a site the worker has paused, which goes against D-0063.
  - A worker restart (which the supervisor does on a crash) loses the pause and its doubling memory. The site is contacted again at once, and the next pause starts at 1 h again.
  - The Redis keys `cip:listing_capture:site_pause:*` can never exist, so the planned way to see pauses from outside does not work.
- Why tests missed it: every test injects `MemorySitePauseStore` or monkeypatches `default_site_pause_store` (`test_listing_capture_p5_live_fetch.py`). No test covers store selection.
- Fix: use `from app.core.config import get_settings` and `get_settings().redis_url`. Add a unit test that monkeypatches `redis.Redis.from_url` to a fake whose `ping()` returns True and asserts `RedisSitePauseStore` is returned, and that a ping failure returns the memory store. Narrow the `except` around the import, or log the exception type, so a code error no longer reads as an outage.

## Findings (not defects in N-0101 code)

- **F1. Overnight polling did not run because the host slept.** Windows System log (read-only `Get-WinEvent`): 18:18:31 entering Modern Standby (Reason: Lid). 18:44 battery-budget re-entry. 21:01:57 exit, then 21:02:03 "entering sleep: Hibernate from Sleep". 08:54:59 resume (system time jump 42,766,664 ms). Beat slots 18:30 to 20:30 and 21:30 to 08:30 never ran. Beat caught up at 08:55:45 (one catch-up run) and ran the 09:00 slot right after it. The supervisor cannot keep polling with the lid closed. "Always on" needs the machine awake (power plan or lid action), which is Warren's call and a machine setting outside the supervisor's rules. Owner: N-0073 follow-up or Warren.
- **F2. The 42,777 s "run" is hibernation, not a hang.** The 21:02 run polled 15 listings in about 10 s awake, the host hibernated mid-run, and on resume the loop's first check hit the 600 s limit (`stopped_reason: time_limit`, logged 08:54:59.509, the same second as the resume). Celery reports `succeeded in 42779.656s`. That reads like a stuck task in dashboards. Suggestion: log wall-clock start and end, or note when `duration_seconds` far exceeds the limit. 15 rows with `http_status 0`, `parse_failed` (6 amazon, 6 evetech, 3 takealot) came from the network dropping at sleep. They were correctly not counted as dead links.
- **F3. Amazon CAPTCHA pages at HTTP 200 are still fetched every run.** Since 2026-10-07 12:00 there are 140 Amazon `parse_failed` rows at 200 and 115 `ok` rows (all availability `unknown` today). Already a deferred DOES_NOT_FIT item (ESCALATION seq 1682) awaiting Warren. Re-confirmed, not re-raised.
- **F4. Tunnel unhealthy after wake (N-0073 scope).** Status at 09:09:44: tunnel `/ready 503`, public `/login 530`, launches=4, two new hostnames this morning (`coating-synthesis-...` at 08:56, `heaven-bedding-...` at 09:07). All other components were healthy. Not caused by N-0101: the tunnel's launch lines show both listing flags `present=False`, as designed.
- **F5. Storage (finops FAIL, already recorded).** Snapshot bytes per half-hour slot: 19.7, 18.8, 29.6, 22.2 and 36.9 MB (the last slot holds 2 runs). Consistent with the implementation's measure of about 20 MB per run.
- **F6.** 10 Evetech observations have HTTP 404 but `parse_status ok` (an existing rule: dead only when the parse also fails). Worth a look in U2, not N-0101.

## Evidence

### (1) Code review

Changed files reviewed: `apps/api/app/services/listing_capture/observation.py`, `registry.py`, new `site_pause.py`, `apps/api/app/worker/tasks.py` (unchanged; it calls `poll_active_listings(session, http_get=default_http_get)` behind both gates), `celery_app.py` (beat `crontab(minute="*/30")`, unchanged), `scripts/cip-supervisor.ps1` (diff), and `tests/test_listing_capture_p5_live_fetch.py` (diff).

- **User-Agent (D-0063):** `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36`, plus an ordinary `Accept` and `Accept-Language: en-ZA,en;q=0.9`. This is an ordinary desktop Chrome string. The Takealot API `Accept: application/json` and `Referer` headers predate this change (not in the diff).
- **No evasion:** grep of `listing_capture/` for captcha, proxy, rotate, stealth, cloudscraper, undetected, selenium, playwright, 2captcha, x-forwarded and cookie finds only the D-0063 comment. Transport is stdlib `urllib` with a 20 s timeout. There are no retries and no cookie jar. After a 403/429, `guarded_get` sends nothing more to that site in the run (Takealot's EAN follow-up is suppressed) and returns an empty body, so no price is parsed from a refusal page.
- **Restock:** `prev_status == out_of_stock`, `parse ok` and availability `in stock`/`in_stock` give `active` with `status_transition.reason = restocked`. `unknown` is not a restock. Live vocabulary today matches: evetech/takealot `in_stock`/`out_of_stock`.
- **Dead-link back-off:** 404/410 with a failed parse increments `meta_json.consecutive_failures` and sets `last_failure_at`. At 3 or more, the poller skips the listing for 24 h with no request and no row. After 24 h it retries once; a dead result gives 4 and a fresh 24 h, so the retry is daily. A good parse clears the count (`link_recovered` from dead_link).
- **Pause:** `pause_site` sets 1 h, or doubles the remembered hours up to a 24 h cap, with TTL = hours + 24 h. It clears on the next 200 after the pause has ended. The poller checks each site once per run. Behaviour inside one process is correct; the store selection is broken (D1).
- **Selection:** statuses `active`, `out_of_stock` and `dead_link`. Order is `max(fetched_at)` of non-`skipped` rows `NULLS FIRST`, then id, then round-robin across marketplaces. Spacing is per site (2 s; 5 s for an unknown site). The 600 s limit is checked before each listing and before a sleep that would cross it. Remaining limitation (already recorded): no Celery hard limit, so a fetch already in flight can overrun the limit by its timeouts.
- **Supervisor:** `$WorkerListingEnv` (both flags `'1'`) is merged into the worker's `ExtraEnv` only. `Start-Component` sets ExtraEnv in the supervisor's own process env for the launch, then restores the saved values in `finally`, so API, web and tunnel do not inherit the flags. `status.json` `env` now reports what the worker was given (`scope: worker`, `source`), plus the supervisor's own env separately. When the worker is adopted the env shows as not known (null). This is honest, but it means flags are unconfirmed after a supervisor restart that adopts a worker.

### (2) Tests and mutations (apps/api, venv python, `-p no:cacheprovider`)

- `tests/test_listing_capture_n0101_polling.py`: **16 passed**.
- The implementation's set (n0101, lc_u1, p5_live_fetch, takealot_listing_fetch, listing_auto_finder, listing_intelligence_v1, cpor_activation, cst_listing_seed_fields): **101 passed**.
- Neighbours (grid_fields, semantic_overlay_governed, promo_plan_builder): **102 passed**.
- Mutation M1 (`registry.py` line 516: restock branch set to `None, None`): **1 failed** (`test_out_of_stock_seen_in_stock_returns_to_active_as_restocked`), 15 passed.
- Mutation M2 (`registry.py` line 798: `if False and status in SITE_PAUSE_HTTP_STATUSES`): **2 failed** (`test_429_pauses_only_that_site_and_is_recorded`, `test_takealot_refusal_sends_no_follow_up_requests`), 14 passed.
- Restore: the file was copied back from a backup taken before mutation. sha256 of `registry.py` was `9a9b044d...bc569` before and after. sha256 of `git diff -- registry.py` was `2852c7a2...a1853` before and after (the file already carried the uncommitted N-0101 change, so "clean" means identical to its pre-mutation diff). `grep "False and status"` returns 0. Re-run: 16 passed. The backup was deleted. The running worker had loaded its modules at 16:31 and was not affected; the mutation was on disk for a few seconds each time.
- Gap: no test covers `default_site_pause_store()` (D1).

### (3) Live, read-only

`scripts/cip-supervisor-status.ps1 -Ports -Local -Public` at 09:09:44: supervisor pid 29088 alive, cycle 226, heartbeat 20 s. `env CIP_LISTING_LIVE_FETCH present=True CIP_LISTING_CAPTURE_SCHEDULE present=True`. Raw status: `scope: worker`, `source: launched by this supervisor`, `supervisor_process` both false. wsl, redis, worker (pid 37116, worker=1 beat=1), api and web all healthy. **Tunnel unhealthy** (F4). Local api `/health` 200, `/auth/me` 401; web `/login` 200, proxy `/auth/me` 401. Supervisor log: `worker: started pid 37116 (launch 1; CIP_LISTING_LIVE_FETCH present=True, CIP_LISTING_CAPTURE_SCHEDULE present=True)` at 16:31:48. Every API and web launch shows `present=False`. Task results show `enabled: True, should_run: True` and no `live_fetch_not_enabled` skip, so the flags are effective in the worker.

cip (`N0101_verify_db.py`; `current_database()` = `cip`, `transaction_read_only` = `on`, rolled back; no URL or secret printed). Observations since 2026-10-07 12:00 SAST, by half hour:

| Slot | amazon | evetech | takealot | Note |
|---|---|---|---|---|
| 10-07 17:00 | 51 | 88 | 79 | run 266 s |
| 10-07 17:30 | 51 | 88 | 79 | run 234 s |
| 10-07 18:00 | 51 | 88 | 79 | run 310 s |
| 18:30 to 20:30 | 0 | 0 | 0 | host in Modern Standby (F1) |
| 10-07 21:00 | 5 | 6 | 3 | 10 s awake, then hibernate |
| 21:30 to 08:30 (pre-wake) | 0 | 0 | 0 | hibernated (F1) |
| 10-08 08:30 | 50 | 50 | 13 | catch-up run from 08:55 |
| 10-08 09:00 | 53 | 126 | 61 | rest of 08:55 run plus 09:02 run |

- First fetches in each run start within 0 to 7 s across all three retailers, so retailers are interleaved.
- `customer_listing` status now: amazon active 51; evetech active 36, out_of_stock 52; takealot active 35, dead_link 42, out_of_stock 2.
- Transitions since 12:00: evetech `out_of_stock` 52, takealot `dead_link` 42, takealot `out_of_stock` 2. `restocked` 0 and `link_recovered` 0 (none happened live).
- out_of_stock kept polled: 104 Evetech `out_of_stock` observations today (52 listings by 2 runs).
- **Takealot dead links:** all 42 have `consecutive_failures = 3`, with `last_failure_at` between 10-07 18:00 and 18:04. Each has exactly 3 observations since 12:00 (17:00, 17:30, 18:00). There are **0 dead-link observations since 08:00 today**, and the 08:55 and 09:02 runs both log `skipped_backoff: 42` with 0 `skipped` rows written. Daily back-off is in effect. The first daily retry is due about 18:00 to 18:04 today and was not observed.
- Pauses: 0 observations with HTTP 403/429 and 0 with `parse_flags.site_paused` since 12:00. Redis `--scan` for `cip:listing_capture:site_pause:*` on db 0 (the app's `redis_url` db) and on db 1 (broker) returned no keys, and db 0 `dbsize` is 0. No pause occurred live, and none could have been written to Redis anyway (D1).

### (4) Run time limit

Worker log (`-Log 3000 -LogFile worker.err.log`), `listing capture poll:` lines:

| Start | polled | skipped_backoff | duration_seconds | stopped_reason |
|---|---|---|---|---|
| 10-07 17:00 | 218 | 0 | 266.39 | none |
| 10-07 17:30 | 218 | 0 | 233.906 | none |
| 10-07 18:00 | 218 | 0 | 310.453 | none |
| 10-07 21:02 | 15 | 3 | 42776.719 | time_limit (hibernation, F2) |
| 10-08 08:55 | 176 | 42 | **358.328** (longest awake run) | none |
| 10-08 09:02 | 176 | 42 | 306.078 | none |

All runs while the host was awake finished under 600 s; the longest was 358 s. The limit fired correctly on the first check after resume. `failed` was 0 in every run.

### C8 web gates

N-0101 changed no web file. The uncommitted `capabilities.ts` and `MarketSurface.tsx` copy edits belong to another node's sweep; the "Checked on a schedule and by hand" line comes from that sweep. `npx eslint` run from `apps/web` found no flat config (ESLint 9; exit 2). Not pursued, because those files are not in N-0101 scope. tsc was not run.

## Not verified / limitations

- No live restock and no live 403/429 occurred. These rely on the unit tests and the M1/M2 mutation kills.
- The daily dead-link retry (due about 18:00 today) was not observed.
- Overnight schedule continuity could not be shown (F1).
- The worker's process env was not read directly. It is inferred from the supervisor launch record and the task gate results.
- R2 only: same model family, no independent model consult.

## Files

- Report: `.eif/audit/PROGRAMME_20261007/N0101_VERIFY.md`
- Read-only query script: `.eif/audit/PROGRAMME_20261007/N0101_verify_db.py`
- Ledger payloads: `.eif/audit/PROGRAMME_20261007/N0101_ver_behavioral.json`, `N0101_ver_referent.json`, `N0101_ver_stage_verify.json`

## Re-verification (round 2)

- Verification run: `RUN-20261008-N0101-VER2`. Implementation run: `RUN-20261007-N0101-IMPL` (round 2 fix). Node rev 20, stage `validate`.
- Independence rung: **R2, fresh context** (separate subagent session, same model family; not a different model). Different `--run` from the implementation run and from the first verification run. Every result below was re-executed in this run; `N0101_IMPL.md` round 2 was read only to know which claims to test.
- Date: 2026-10-08, about 09:40 to 09:55 local (SAST).
- Lenses: GOV-008 verification-controller, reliability-sre-specialist, test-engineering-specialist.

### Verdict

**VERIFIED_WITH_LIMITATIONS. D1 is closed.** `default_site_pause_store()` now returns the Redis store when Redis answers, falls back to the process-local store only when Redis is unreachable, and logs that fallback with the exception type. Code errors are raised, not hidden. Two of my own mutants that bring the swallow back are caught by the new tests. The running worker (restarted 09:27:40) has logged no "Redis unavailable" or "Redis unreachable" line, and a fresh process picks `RedisSitePauseStore` on localhost:6379 db 0. The round 1 VERIFIED items still hold.

Ledger kinds: **referent = pass** (the claim "the site pause is in Redis; process-local only when Redis is unreachable" is now true as built). **behavioral = pass** (limitations below).

### (1) Code review: `apps/api/app/services/listing_capture/site_pause.py`

sha256 `8ebf07f7...99051`, the same hash the implementation recorded after its restore.

- `import redis` and `from app.core.config import get_settings` are now module-level imports. A broken import fails when the module loads and can no longer pass as an outage. `app.core.config.get_settings` exists, and `redis_url` defaults to `redis://localhost:6379/0` (config.py line 38).
- `_redis_client()` calls `redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=0.5, socket_timeout=2)`. It runs **outside** the `try`, so a bad URL (ValueError) is raised.
- `default_site_pause_store()` runs `client.ping()` inside `try`. The only exceptions it catches are `_REDIS_UNREACHABLE_ERRORS` = `redis.exceptions.ConnectionError`, `redis.exceptions.TimeoutError` and `OSError`. On those it returns the shared `_memory_store` and logs one WARNING per outage: `Redis unreachable (<Type>: <msg>); site pauses kept in this process only`. When Redis answers again it logs `reachable again` once. Any other exception propagates. The swallow is gone.
- The caller is unchanged: `registry.py` line 726 still uses `pause_store if pause_store is not None else site_pause.default_site_pause_store()`, and the lazy import is at line 713. `registry.py` sha256 is `9a9b044d...bc569`, identical to round 1, so the round 1 M1/M2 analysis still applies.
- Minor observations. None of these blocks closure.
  - **O1.** In redis-py 5.2.1, `AuthenticationError` is a subclass of `ConnectionError` (MRO checked). A wrong Redis password would therefore fall back as "unreachable". It would not be silent, because the log names `AuthenticationError`. There is no password on this local stack today.
  - **O2.** `paused_until()`, `has_pause_record()`, `pause_site()` and `clear_site_pause()` still catch `Exception` around store reads and writes. This code is unchanged from round 1. If Redis drops in the middle of a run, a paused site reads as "not paused" (fail-open). `paused_until` logs a warning when that happens; `has_pause_record` does not log. This is not the D1 pattern, because store selection still logs, but it is worth narrowing in U2.
  - **O3.** The fallback warning is logged once per outage and once per process, so later runs during the same outage are not logged again. This is documented in the docstring and is acceptable.

### (2) Tests and mutations (apps/api, `.venv` python, `-p no:cacheprovider`)

- `tests/test_listing_capture_site_pause_store.py`: **9 passed**.
- N-0101 set (site_pause_store, n0101_polling, lc_u1, p5_live_fetch, takealot_listing_fetch, listing_auto_finder, listing_intelligence_v1, cpor_activation, cst_listing_seed_fields): **110 passed**.
- Neighbours (grid_fields, semantic_overlay_governed, promo_plan_builder): **102 passed**.
- My own mutants, applied with `.eif/audit/PROGRAMME_20261007/N0101_ver2_mutate.py`. They differ from the implementer's M-D1, which restored the old function body.
  - **MV-A (swallowed import error), 09:45:54.** `_redis_client()` imports the non-existent `app.core.config.settings`, the client is built inside the `try`, and `ImportError` is added to the "unreachable" tuple. Result: **9 failed, 0 passed.** The Redis-selection and round-trip tests get `MemorySitePauseStore`, the log tests see the wrong type, and the code-error tests see nothing raised.
  - **MV-B (broad swallow), 09:46:24.** `except _REDIS_UNREACHABLE_ERRORS` is changed to `except Exception`. Result: **3 failed, 6 passed.** All three `test_code_errors_are_raised_not_hidden_as_an_outage` cases fail (AttributeError, ImportError, ResponseError).
- Restore. After each mutant the file was copied back from a backup taken just before it. sha256 was `8ebf07f7...99051` before, after MV-A's restore and after MV-B's restore. `MUTANT` count is 0 and the backup was deleted. `git status --porcelain -- apps/api/app/services/listing_capture` is identical before and after (`site_pause.py` untracked, `observation.py` and `registry.py` modified by N-0101 itself). `site_pause.py` is untracked, so `git diff` cannot cover it; the sha256 match is the clean check. Re-run after restore: 25 passed (store and n0101 files). Each mutant was on disk for about 15 s. The running worker had imported its modules at 09:27 and was not restarted, so it was not affected.

### (3) Live, read-only (no restart, no cip write)

- `scripts/cip-supervisor-status.ps1 -Log 60 -LogFile worker.err.log` at 09:48:06: supervisor pid 29088 alive, cycle 297. `env CIP_LISTING_LIVE_FETCH present=True CIP_LISTING_CAPTURE_SCHEDULE present=True`. wsl, redis (`PING -> +PONG`), worker (pid 44904, launches=2, worker=1 beat=1), api (pid 24948) and web (pid 45608) were healthy. The tunnel was unhealthy (launches=7, public 530); this is the known N-0073-scope issue (F4) and is unrelated.
- Supervisor log: `09:27:40 worker: started pid 44904 (launch 2; CIP_LISTING_LIVE_FETCH present=True, CIP_LISTING_CAPTURE_SCHEDULE present=True)`, healthy at 09:28:21. API launch 2 (2026-10-07 16:59:11) still shows both flags `present=False`.
- The current `worker.err.log` starts at `09:27:52 beat: Starting...`, so it covers the whole new worker. A search of the full file (122 timestamped lines, to 09:48:52) for `Redis unavailable|Redis unreachable|reachable again|refused with HTTP` found **0 matches**. Round 1's worker logged "Redis unavailable" at the start of every run. `Connected to redis://localhost:6379/1` is the Celery broker.
- Latest poll task (beat 09:30:00, task `b8819578`): `polled 176, failed 0, listing_count 218, skipped_backoff 42, skipped_paused {}, paused_sites {}, stopped_reason None, duration_seconds 312.703`, task succeeded in 313.187 s, `enabled True, should_run True`. The next slot (10:00) had not run by the end of this check.
- Fresh-process store check (`.eif/audit/PROGRAMME_20261007/N0101_ver2_live_store.py`: ping, scan and get only, no write, no URL or secret printed): `store_type RedisSitePauseStore` (selected in 0.090 s), `redis host localhost port 6379 db 0`, `site_pause_keys 0`, all three markets `None`, `fallback_warned False`.
- Real fallback path, same script with `REDIS_URL` pointed at a closed local port (6399), in-process only: `WARNING ... Redis unreachable (TimeoutError: Timeout connecting to server); site pauses kept in this process only`, `store_type MemorySitePauseStore`, 1.06 s. On this Windows host a closed port shows up as a timeout. The fallback adds about 1 s to a run and is logged.
- API process: pid 24948 has not been restarted since 2026-10-07 16:59 and runs without `--reload`. `registry.py` imports `site_pause` lazily, inside the poll function. The API's current `api.log` (1,090 lines) and `api.err.log` (160 lines) contain no `listing-capture/poll` request and no "Redis unavailable" line. This is a negative search of those files only. It points to the API not having loaded `site_pause` yet, in which case its first manual poll will load the fixed file from disk, but that is not proven.

### (4) Prior VERIFIED items, spot check

- Restock and back-off tests: `test_out_of_stock_seen_in_stock_returns_to_active_as_restocked`, `test_out_of_stock_unknown_availability_is_not_a_restock`, `test_poller_selects_out_of_stock_and_dead_link_oldest_due_first`, `test_consecutive_dead_results_drive_backoff_and_a_good_parse_resets`, `test_dead_link_with_two_failures_is_still_polled`, `test_429_pauses_only_that_site_and_is_recorded`, `test_403_pause_doubles_up_to_24h_and_clears_on_success` and `test_takealot_refusal_sends_no_follow_up_requests`: **8 passed**.
- `registry.py` is byte-identical to round 1, so the round 1 M1 (restock) and M2 (403/429 guard) kills still apply.
- Live back-off is still in effect: the 09:30 run logged `skipped_backoff 42`, the same as 08:55 and 09:02. The run time limit also still holds: 312.7 s, under 600 s, with `stopped_reason None`.
- C1 (worker-only flags) still holds after the worker restart (see the supervisor log above).

### Limitations (round 2)

- No live 403/429 has occurred since N-0101 went live, so no pause has been written to real Redis. Persistence is shown by the unit round-trip test with a fake client and by a live `RedisSitePauseStore` selection. A pause actually reaching Redis is not observed.
- No live restock and no live daily dead-link retry yet (the first retry is due about 18:00 to 18:04 today).
- The API process has not been restarted. Cross-process sharing on the manual-poll path rests on the lazy import plus a negative log search. Restarting the API when N-0101 is committed would remove this doubt (operator's call; no restart in this run).
- Host-asleep gaps (F1) are accepted per Warren's decision. Schedule continuity holds only while the host is awake.
- finops is still FAIL (unchanged, already deferred). The `app/query/cache.py` same-bug finding is deferred by the implementation run and was not re-checked here.
- R2 only: same model family, no independent model consult.

### Files (round 2)

- Mutation helper (temporary edit, restored): `.eif/audit/PROGRAMME_20261007/N0101_ver2_mutate.py`
- Read-only live store check: `.eif/audit/PROGRAMME_20261007/N0101_ver2_live_store.py`
- Ledger payloads: `.eif/audit/PROGRAMME_20261007/N0101_ver2_referent.json`, `N0101_ver2_behavioral.json`, `N0101_ver2_stage_verify.json`

## Re-verification (round 3)

- Verification run: `RUN-20261008-N0101-VER3`. Implementation run: `RUN-20261007-N0101-IMPL` (round 3, snapshot policy). Node rev 32, stage `validate`.
- Independence rung: **R2, fresh context** (separate subagent session, same model family; not a different model). Different `--run` from the implementation run and from VER and VER2. Every result below was re-executed in this run; `N0101_IMPL.md` "Round 3" was read only to know which claims to test.
- Date: 2026-10-08, about 21:20 to 21:45 local (SAST).
- Lenses: GOV-008 verification-controller, database-specialist, test-engineering-specialist.
- Decision under test (Warren, 2026-10-08): store a raw snapshot only when the extracted fields changed versus the previous successful observation, or the fetch/parse failed; clear raw snapshots older than 90 days (payload only; rows and fields kept forever).

### Verdict

**VERIFIED_WITH_LIMITATIONS.** The code does what the decision says, the tests catch my own mutants (one of them only through an SQL-text assertion, see T1), the live data on cip matches the policy row by row, no observation row was deleted, and the implementation's numbers reproduce exactly. The finops "pass" is honest in the sense the decision asks for: payload growth is bounded by the 90-day retention, and rows-forever is Warren's call. The retention job has not yet run on cip or in the worker, so its live behaviour rests on the cip_test and unit tests.

Ledger kinds: **behavioral = pass**, **referent = pass** (claims in `N0101_IMPL.md` Round 3 about `registry.py` and `snapshot_retention.py` are true as built; the reduction and Amazon-share numbers reproduce).

### (1) Code review

Hashes at the start of this run: `registry.py` sha256 `3f46e1c2121d56dc...` (the hash the implementation recorded), `snapshot_retention.py` `d61178f8307e3f1e...`, `tasks.py` `ac3628412a884db7...`, `celery_app.py` `2360a3e329b4836f...`.

Change detection (`apps/api/app/services/listing_capture/registry.py`):
- `previous_successful_observation()` selects the listing's latest row with `http_status = 200` and `parse_status = 'ok'`, ordered `fetched_at desc, id desc`, `limit 1`, with `raw_snapshot` deferred. It runs before the new row is added, so autoflush cannot return the new row. A non-ORM result counts as "no previous", which keeps the snapshot. Correct.
- The order of reasons in `record_observation` is right: `fetch_failed` (status not 200, or a fetch-side reason) and `parse_failed` are decided before any comparison, so **failures always store**. `prev_ok is None` gives `first_observation`, so **the first observation stores**. Otherwise `extraction_unchanged()` compares parser version, price (quantized to 4 dp, so a DB `Decimal` equals a float parse), availability, promo badge and every key in the parser's own flags. A status transition upgrades a skip to `status_transition`. The extracted fields, CPOR activation and status logic are still written on every row; only `raw_snapshot` is set to `NULL` on a skip.
- The parser-flag comparison is one-directional (it checks only keys in the new parse). I checked the parsers: each successful parse method always emits the same key set (keys may be `None`), and a change of method changes the `method` key, so a missing key cannot hide a change today. If a parser later emits optional keys, a key that disappears would not count as a change. Minor; not a defect now.
- `reparse_observation()` returns a row with no payload unchanged and logs it at INFO, so its extracted fields are never overwritten by a parse of nothing. Correct.

Retention (`apps/api/app/services/listing_capture/snapshot_retention.py`, task in `apps/api/app/worker/tasks.py`, beat in `celery_app.py`):
- Keyset batches (`id > :after_id ... order by id limit :batch_size`, default 5000) of rows with `fetched_at < now - 90 d` and a payload. Each batch runs `UPDATE ... SET raw_snapshot = NULL` and merges `snapshot_cleared` into `parse_flags`; a JSON null or a non-object is handled without loss. Commit after each batch. No new batch starts after 240 s. There is **no DELETE** anywhere in the module, and `rows_deleted` is a constant 0. **Bounded, batched, payload-only, never deletes rows.**
- RLS is off on `listing_observation` (`relrowsecurity false`, read on cip), so the worker's UPDATE cannot be filtered to zero rows by a tenant policy.
- The task honours `dev_beat_disabled()`, the same gate as the poll task. The supervisor sets `CIP_ENABLE_DEV_BEAT=1` for the worker (`scripts/cip-supervisor.ps1` line 564), so the worker's beat includes the entry.
- **O-V3-1 (doc).** No Celery `timezone` is set (`conf.timezone None`, `enable_utc True`), so `crontab(hour=3, minute=15)` fires at **03:15 UTC = 05:15 SAST**, not at 03:15 local as `N0101_IMPL.md` and the finops rationale imply. This is harmless, but the first retention run is due at about 05:15 SAST on 2026-10-09, and only if the host is awake (beat catches up once on wake, as seen for the poll at 08:55 this morning).
- **O-V3-2 (scale, database-specialist).** The only indexes on `listing_observation` are `pk_listing_observation (id)` and `ix_listing_observation_listing_id (listing_id)`. `EXPLAIN` of the previous-successful lookup is a bitmap scan on `listing_id`, then a filter on status and a sort. Rows are kept forever at about 48 per listing per day, so each lookup reads all of the listing's history: about 17,500 rows per listing after a year, and 218 lookups per run. It is cheap today (cost 65 at 4.6k rows). A partial index on `(listing_id, fetched_at desc, id desc) where http_status = 200 and parse_status = 'ok'` would make it constant time. It needs a migration, so it is out of scope here. The pre-existing "oldest due" selection query has the same growth. The retention select is a sequential scan of the heap (the `IS NOT NULL` check does not detoast). That is fine daily at this size, and it is checked against the time limit only between batches (there is no `statement_timeout`). Recommend `finding.defer` to U2 or a performance node.

### (2) Tests and mutations (apps/api, `.venv` python, `-p no:cacheprovider`)

- Policy file + N-0101 set (`test_listing_capture_snapshot_policy.py`, `site_pause_store`, `n0101_polling`, `lc_u1`, `p5_live_fetch`, `takealot_listing_fetch`, `listing_auto_finder`, `listing_intelligence_v1`, `cpor_activation`, `cst_listing_seed_fields`): **127 passed**.
- Neighbours (`grid_fields`, `semantic_overlay_governed`, `promo_plan_builder`): **102 passed** (229 in total, same as the implementation).
- cip_test DB file through `N0101_r3_run_db_tests.py`: `current_database() = cip_test`, **2 passed**, `listing_observation` rows 0 before and 0 after (rolled back).
- My own mutants, with `.eif/audit/PROGRAMME_20261007/N0101_ver3_mutate.py` (each differs from the implementation's M-S1 "always store"):
  - **MV3-A, compare with the previous observation of ANY status** (the `http_status == 200` and `parse_status == 'ok'` filters removed from `previous_successful_observation`), 21:29. Policy file **1 failed, 16 passed**: only `test_previous_successful_query_shape` fails, on its SQL-text assertion. DB file **2 passed** (survived).
  - **MV3-B, retention deletes rows** (the clear statement becomes `DELETE ... WHERE id = ANY(:ids)`), 21:30. Policy file **2 failed** (both retention tests hit the "no DELETE" assertion). DB file **1 failed** (`count(*)` 3 vs 5 before).
  - **MV3-C, retention ignores the 90-day cutoff**, 21:31. Policy file 17 passed (survived: the in-memory retention session does not model the cutoff). DB file **1 failed** (the 89.5-day row's payload was cleared: `bytes(None)`).
- **T1 (test gap, not blocking).** The "previous SUCCESSFUL" rule is guarded only by an SQL-text assertion. The behavioural unit tests use `MemorySession`, which applies the 200/ok filter itself whatever the query says, and the cip_test DB test has no "failure between two identical pages" sequence. MV3-A therefore passes every behavioural test. The SQL-shape test does kill it, so the requirement is met. Recommend adding one leg to `test_record_observation_unchanged_stores_no_snapshot_in_postgres`: ok, failed parse, then the same ok page, which should give no snapshot and point at the first id.
- Restore. Each mutant was copied back from a backup taken just before it. After all three: `registry.py` sha256 `3f46e1c2121d56dc...` and `snapshot_retention.py` `d61178f8307e3f1e...`, both identical to the start of the run. The sha256 of `git diff -- registry.py` was `c57d90f8...864247` before and after (identical). `git status --porcelain -- apps/api/app/services/listing_capture` was unchanged. `snapshot_retention.py` is untracked, so its sha256 is the clean check. `MUTANT` count 0 in both files; backups and the state file were deleted. Re-run after restore: policy + n0101 polling **33 passed**. Each mutant was on disk for about 15 to 30 s. The worker had loaded `registry` before 15:00 and was not restarted. The worker has never imported `snapshot_retention` (its task first runs at 05:15 SAST), so it could not load MV3-B or MV3-C.

### (3) cip, READ ONLY

Scripts: `.eif/audit/PROGRAMME_20261007/N0101_ver3_db.py` and `N0101_ver3_db2.py` (independent SQL, written in this run). Each printed `current_database() = cip` and `transaction_read_only = on`, ran with `SET TRANSACTION READ ONLY` and `statement_timeout 60s`, then rolled back. They used the venv python with `get_settings().database_url_sync` and `postgresql+psycopg`. No URL or secret was printed.

Snapshots per 30-minute slot (SAST):

| Slot | Rows | With | Without | Snapshot bytes |
|---|---|---|---|---|
| 13:00 (round 2 worker) | 176 | 176 | 0 | 18,410,397 |
| 13:30 (round 2) | 176 | 176 | 0 | 18,481,530 |
| 14:00 (round 2) | 176 | 176 | 0 | 17,259,821 |
| 14:30 (round 2) | 176 | 176 | 0 | 17,867,395 |
| 15:00 | 175 | 36 | 139 | 3,684,399 |
| 15:30 | 176 | 25 | 151 | 6,469,433 |
| 16:00 | 176 | 25 | 151 | 6,365,851 |
| 16:30 | 176 | 51 | 125 | 770,316 |
| 17:00 | 176 | 26 | 150 | 5,874,300 |
| 19:30 (cut by sleep) | 30 | 30 | 0 | 600 |
| 20:30 (20:45 run + 1 row from 19:30) | 219 | 94 | 125 | 332,417 |
| 21:00 | 176 | 52 | 124 | 482,426 |
| 21:30 (committed during this check) | 176 | 51 | 125 | 622,135 |

- **Reduction claim confirmed.** The 15:00 to 17:00 values equal the implementation's table to the byte. The average of those five full runs is 4.63 MB, against 18.00 MB for the four round-2 runs the same afternoon: **74.3% less**. That is "about 74%". Including the three later runs (20:45, 21:00, 21:30), eight full runs average 3.07 MB (83% less). One small difference: the implementation lists the 13:00 slot as 167 rows and 17.27 MB; I count 176 rows and 18.41 MB. Their probe was limited to `id > 3126`, which starts inside that slot. The conclusion is unchanged.
- **Amazon share confirmed.** By marketplace since 15:00 (before the 21:30 run): amazon 367 rows, 260 with a snapshot, 23.09 MB; evetech 625 rows, 25 with, 0.87 MB; takealot 312 rows, 54 with, 0.02 MB. Amazon is **96.3%** of all snapshot bytes since 15:00 and **97.1%** of the five-run window, so "about 95%" slightly understates it. Of Amazon's bytes, 20.64 MB are 240 `parse_failed` rows at HTTP 200 and 2.45 MB are 10 `changed` rows. Evetech's 0.74 MB is 14 `fetch_failed` rows at 404 with parse ok (listings 120 and 121, the deferred finding 2).
- **Policy invariants on live rows since 15:00:**
  - Failed fetch or parse rows without a snapshot: **0**.
  - Rows without a payload that lack `snapshot_skipped` (excluding back-off rows): **0**.
  - All **965** `unchanged` rows point at exactly the latest earlier HTTP-200 parse-ok row of the same listing (**0** wrong referents), with identical price, availability, promo and parser version (**0** mismatches).
  - Skipped rows that also carry a status transition: **0**.
  - `changed` rows whose core fields equal the previous success: **0** (no spurious "changed" rows from flag comparison).
  - 200/ok rows carrying a fetch-side reason, which would count as "previous successful": **0** ever.
- **"Previous successful", not "previous of any status", shown live.** 68 `unchanged` rows (58 Amazon after a CAPTCHA `parse_failed`; 10 Evetech after a status-0 sleep failure) come right after a failed observation, and in all 68 the referent is the earlier success, not the failure.
- **No observation row deleted.** Before the 21:30 run: 4,429 rows, ids 2 to 4,430, **0 id gaps**. After it committed: 4,605 rows, ids 2 to 4,606, **0 gaps**, sequence `last_value` 4,606. (An earlier reading of sequence 4,603 against max id 4,430 was the 21:30 run's uncommitted rows; the run commits once at the end.) The slots recorded by VERIFY round 1 still hold the same counts: 10-07 17:00, 17:30 and 18:00 at 218 each, 21:00 at 14, 10-08 08:30 at 113 and 09:00 at 240. Snapshots older than 90 days: 0. Rows with `snapshot_cleared`: 0. The oldest row is 2026-08-09 21:27 SAST.
- Table: `listing_observation` 456 MB in total, of which the heap is 3.3 MB; the rest is TOAST and indexes.

### (4) finops claim

The claim is honest against the decision. Snapshots are now stored only on change or failure, live, as shown above. The payload older than 90 days is cleared by a bounded job that never deletes rows. Rows are kept forever by Warren's decision. Growth is bounded rather than fixed. The per-run snapshot volume swings with what Amazon serves, from 0.33 to 6.47 MB per full run today. That gives about 0.02 to 0.31 GB a day, or about 1.4 to 28 GB at 90 days. In the worst case, all 51 Amazon pages are large CAPTCHA pages, about 14 MB per run, which caps at about 60 GB. The implementation's "about 20 GB" is a reasonable midpoint estimate, not a measured ceiling. Limits: retention has not run on cip or in the worker. Its first run is about 05:15 SAST on 2026-10-09 (UTC beat, O-V3-1) and should clear 0. The first real clearing is about 2026-11-07. Freed TOAST space is reused only after autovacuum.

### Limitations (round 3)

- Retention was verified on cip_test and in unit tests only. It was not run on cip (no cip writes) and has not yet run in the worker.
- No live `first_observation` or `status_transition` snapshot since 15:00 (all listings already had a success, and no transitions occurred). These rest on the unit and DB tests.
- Growth bounds are extrapolated from one day of runs, with the host asleep 17:29 to 20:44.
- T1: the "previous successful" filter is guarded by an SQL-text test only.
- R2 only: same model family, no independent model consult.

### Files (round 3)

- Mutation helper (temporary edits, restored): `.eif/audit/PROGRAMME_20261007/N0101_ver3_mutate.py`
- Read-only cip probes: `.eif/audit/PROGRAMME_20261007/N0101_ver3_db.py`, `N0101_ver3_db2.py`
- Ledger payloads: `.eif/audit/PROGRAMME_20261007/N0101_ver3_behavioral.json`, `N0101_ver3_referent.json`, `N0101_ver3_stage_verify.json`
