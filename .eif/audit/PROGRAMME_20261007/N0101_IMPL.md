# N-0101 implementation (N-0085 U1): listing polling under the supervisor

Run RUN-20261007-N0101-IMPL. Lenses: backend-engineer (owner), test-engineering-specialist, reliability-sre-specialist.
Design: `N0085_DESIGN.md` (U1). Decisions: D-0061 (polling on, every 30 min, once supervised), D-0063 (ordinary browser User-Agent, polite per-site spacing, per-site pause on 403/429 1 h doubling to 24 h, per-run time limit; no CAPTCHA solving, proxy/IP rotation or bot-protection evasion).

Status: implementation done and tests green; live beat measurement below. Self-verification only; GOV-008 verification is a later, separate run.

## Discovery (AS-IS, observed 2026-10-07 on tree a86eff94 + dirty working tree)

Code (FACT, read in this run):
- `apps/api/app/services/listing_capture/registry.py` `poll_active_listings`: selects `status == 'active'` only, ordered by id; one global `time.sleep(RATE_LIMIT_SECONDS[mkt])` between every fetch; no run time limit; no site refusal handling; calls `record_observation(session, listing, http_get=getter)` without `consecutive_dead`, so `should_backoff_dead_link` (threshold 3, 24 h) never fires.
- `record_observation`: sets `dead_link` on 404/410 (Takealot: REST 404 plus failed EAN recovery) and `out_of_stock` when availability contains "out"; nothing ever sets a listing back to `active`. Status history = `customer_listing.status` + `status_observed_at` plus the observation rows; there is no transition log table.
- `observation.py`: `LISTING_CAPTURE_USER_AGENT = "CIP-listing-capture/1.0"` (CIP-identifying; D-0063 replaces it). `default_http_get` returns `(status, body)`; HTTP errors come back as their status, network errors as `(0, "")`.
- Gates: beat entry `listing-capture-poll` every 30 min (`worker/celery_app.py`); task `listing_capture.poll_listings` (`worker/tasks.py`) returns skipped unless `dev_beat_disabled()` is false (supervisor sets `CIP_ENABLE_DEV_BEAT=1`), `CIP_LISTING_CAPTURE_SCHEDULE` in (1/true/on) and `CIP_LISTING_LIVE_FETCH` in (1/true/on).
- `scripts/cip-supervisor.ps1`: worker `ExtraEnv` = `CIP_ENABLE_DEV_BEAT, PYTHONUNBUFFERED, CIP_SUPERVISOR_CHILD, CIP_CELERY_BEAT_SCHEDULE`; header says it never sets `CIP_LISTING_*`; status.json `env` reports the supervisor's own process env (read by `cip-supervisor-status.ps1` as `env.CIP_LISTING_*_present`). `scripts/dev-worker.js` spawns celery with `env: process.env`, so ExtraEnv reaches the worker and beat.
- No site-state table exists (`listing_site_state` is U2's M2). `customer_listing.meta_json` (JSONB) is the only existing per-listing JSON field. Redis is available (`settings.redis_url`, used by `app/query/cache.py`).

cip (read-only SELECT, `current_database()` = cip, probe `N0101_probe.py`):
- `customer_listing`: amazon 51 active, evetech 88 active, takealot 79 active (218, all `active`).
- `listing_observation`: 168 rows (max id 169). amazon 52 (last 2026-08-09), evetech 44 (last 2026-08-10), takealot 72 (last 2026-08-13; 42 ok, 24 parse_failed shells, 6 x 404). No `meta_json.consecutive_failures` on any listing.

## Files changed (uncommitted, working tree on a86eff94)

- `apps/api/app/services/listing_capture/observation.py`: `LISTING_CAPTURE_USER_AGENT` is now an ordinary desktop Chrome string (`Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36`) per D-0063; `default_http_get` also sends a browser `Accept` and `Accept-Language: en-ZA,en;q=0.9` (Takealot API keeps `Accept: application/json` + Referer). New constants: `DEFAULT_RATE_LIMIT_SECONDS=5` (a retailer with no entry), `SITE_PAUSE_HTTP_STATUSES={403,429}`, `SITE_PAUSE_BASE_HOURS=1`, `SITE_PAUSE_MAX_HOURS=24`, `POLL_RUN_TIME_LIMIT_SECONDS=600`. No CAPTCHA solving, proxy or IP rotation, no retry-on-refusal.
- `apps/api/app/services/listing_capture/site_pause.py` (new): per-site pause record `{marketplace, http_status, paused_at, until, hours}` in Redis key `cip:listing_capture:site_pause:<marketplace>` with TTL = (hours + 24 h); 1 h, doubling while remembered, cap 24 h; cleared by the next HTTP 200 from that site after the pause. Falls back to a process-local store when Redis is unreachable. Not durable across a Redis flush: U2's `listing_site_state` (M2) should take it over.
- `apps/api/app/services/listing_capture/registry.py`:
  - `record_observation`: status transitions written on the observation as `parse_flags.status_transition {from,to,reason}` (the observation row is the history; `status`/`status_observed_at` updated as before). Reasons: `restocked` (out_of_stock seen in stock -> active), `link_recovered` (dead_link with a good parse -> active), `out_of_stock`, `dead_link`. "Unknown" availability is not a restock. Dead results (same 404/410 rule) increment `meta_json.consecutive_failures` and set `meta_json.last_failure_at`; a good parse clears both. `consecutive_dead` now defaults to the tracked count (explicit values behave as before).
  - `poll_active_listings`: polls `active`, `out_of_stock`, `dead_link`; ordered by the listing's last non-skipped observation (never checked first), then id; round-robin across marketplaces; skips listings in dead-link back-off (3 consecutive, 24 h after the last failure) without a request or a row; per-site spacing measured from the end of that site's last request; on a 403/429 the wrapped getter sends nothing more to that site for the listing (Takealot's EAN search is not sent), the body is dropped so no price is parsed from a refusal page, the site is paused and the observation gets `parse_flags.site_paused`; paused sites are skipped for the rest of the run and later runs until `until`. Stops starting fetches at 600 s. Return adds `skipped_backoff`, `skipped_paused`, `paused_sites`, `stopped_reason`, `duration_seconds` (task and POST /poll pass it through).
- `scripts/cip-supervisor.ps1`: `$WorkerListingEnv = CIP_LISTING_CAPTURE_SCHEDULE='1', CIP_LISTING_LIVE_FETCH='1'` (matches the `1/true/on` parse in `registry.py` and `worker/tasks.py`) merged into the worker's ExtraEnv only; header comment rewritten; the launch log line reports what the child received; status.json `env` now reports the running worker's launch env (`scope`, `source`; null when adopted or not running) with the old key names kept so `cip-supervisor-status.ps1` still reads it, and the supervisor's own env under `env.supervisor_process`. PowerShell parser: 0 errors.
- `apps/api/tests/test_listing_capture_n0101_polling.py` (new, 16 tests) and `apps/api/tests/test_listing_capture_p5_live_fetch.py` (fake `record_observation` accepts the new kwarg; the poll test uses a memory pause store instead of the real Redis).
- Web: not changed. `capabilities.ts` "Checked on a schedule and by hand" is true once the worker polls; "scheduled for its first fetch" (MarketSurface toast) is also true (never-checked listings go first).

## Tests

- `apps/api/.venv/Scripts/python.exe -m pytest -q tests/test_listing_capture_n0101_polling.py tests/test_listing_capture_lc_u1.py tests/test_listing_capture_p5_live_fetch.py tests/test_takealot_listing_fetch.py tests/test_listing_auto_finder.py tests/test_listing_intelligence_v1.py tests/test_cpor_activation.py tests/test_cst_listing_seed_fields.py` (from apps/api): **101 passed**.
- Neighbours that mention listings (`test_grid_fields.py`, `test_semantic_overlay_governed.py`, `test_promo_plan_builder.py`): **102 passed**.
- New tests cover: restock (out_of_stock -> active, `restocked`), unknown availability is not a restock, out_of_stock transition recorded, query selects all three statuses with oldest-due NULLS FIRST and excludes skipped rows, an out_of_stock listing is fetched, 3 consecutive 404 -> back-off (no request, no row) -> checked after 24 h -> `active` with the count cleared, `link_recovered`, 429 pauses only that site (1 request, others unaffected, recorded on the observation, no price from the refusal body, next run skips it), 403 doubling 1/2/4/8/16/24/24 and clear on success, Takealot refusal sends no follow-up request, 10-min limit (fake clock), round-robin order, per-site spacing, UA has no cip/bot/python token and is what `default_http_get` sends.
- First run of the new file: 2 failures, both fixed. (1) The poller's injected `now` disagreed with the second back-off check inside `record_observation` (real clock); the poller now owns the decision and passes `consecutive_dead=0`. (2) The spacing test assumed spacing ran from request start; the code measures from the end of the previous request (the politer choice); the test was corrected.
- ruff is not installed in the venv (not run). tsc/eslint: no web files touched.

## Live (2026-10-07, SAST)

Restart: `scripts/cip-supervisor-stop.ps1 -Restart` at 16:31 (the supervisor script itself changed). The worker, API, web and tunnel were all supervisor-owned (`adopted=False`), so a full restart stops and restarts all four. It does not adopt them, as the brief expected. The API therefore restarted too and runs the new listing code (POST /poll is still 503 there, because the API gets no `CIP_LISTING_LIVE_FETCH`). It also loaded whatever the N-0071 run had in the working tree at 16:31.
- Status after the restart (`cip-supervisor-status.ps1 -Ports -Local -Public`, 16:33): `env CIP_LISTING_LIVE_FETCH present=True CIP_LISTING_CAPTURE_SCHEDULE present=True`. All six components are healthy: worker=1, beat=1, local api /health 200, /auth/me 401, web /login 200.
- **The public link changed**: from `build-ebooks-heading-scoring.trycloudflare.com` to `declared-calgary-burning-proc.trycloudflare.com`. Public /login is 200 and /api/v1/auth/me is 401. Anyone using the old link needs the new one (link.html / status page).
- No early trigger was used. Both runs below are ordinary beat runs (`listing-capture-poll`, `crontab */30`).

Read-only measurements (`N0101_probe.py`, `N0101_probe2.py`, `N0101_probe3.py`, `N0101_probe4.py`; `current_database()` = cip each time; Celery results read from the result backend via `N0101_redis_probe.py`):

| | Run 1 (beat 17:00) | Run 2 (beat 17:30) |
|---|---|---|
| Task result | polled 218, failed 0, skipped_backoff 0, paused none, stopped_reason null | polled 218, failed 0, skipped_backoff 0, paused none, stopped_reason null |
| Duration | 266.4 s | 233.9 s |
| New observations (id range) | 218 (170..387): amazon 51, evetech 88, takealot 79 | 218 (388..605): amazon 51, evetech 88, takealot 79 |
| HTTP | amazon 51 x 200 (11 ok, 40 parse_failed); evetech 86 x 200 ok + 2 x 404 parsed ok; takealot 37 ok, 20 x 200 parse_failed, 22 x 404 | the same split (amazon 9 ok / 42 failed) |
| Status transitions | evetech 52 active -> out_of_stock; takealot 42 active -> dead_link, 2 -> out_of_stock | none (out_of_stock and dead_link listings re-polled, unchanged) |
| 403/429 pauses | none (no `cip:listing_capture:site_pause:*` keys) | none |
| Stored snapshot bytes | 20.6 MB (evetech 16.6 MB at 188 KB each, amazon 3.8 MB, takealot 0.3 MB) | 19.7 MB |

- Fetch order: the first 12 fetches of each run alternate evetech, takealot, amazon (the retailers are mixed). Run 1 put the never-checked listings first.
- `listing_observation` before: 168 rows, last fetch 2026-08-13. After run 2: 604 rows, table 60 MB.
- Registry after run 2: amazon 51 active; evetech 36 active, 52 out_of_stock; takealot 35 active, 42 dead_link, 2 out_of_stock. 42 takealot listings have `consecutive_failures` = 2. They will reach 3 at 18:00, and from 18:30 they are checked once a day.
- What the transitions are: (a) Takealot dead_link: all 42 have a PLID in the URL, the REST details call returned 404, and none ever had a good observation. 22 have no EAN; for the other 20 the EAN search returned 0 results. The pre-existing rule ran for the first time since 13 Aug. (b) Evetech out_of_stock: all 52 pages carry JSON-LD `availability: OutOfStock` (before this run, 5 of 44 were out of stock). This was not checked by eye on the site. (c) Amazon: 28 of the 40 failures are CAPTCHA or automated-access pages served with HTTP 200 (about 3.8 KB each), so they do not trigger the 403/429 pause.
- A live restock (out_of_stock -> active) has not happened yet. It is covered by the unit tests only, and the next runs will show it when one of the 54 out-of-stock listings comes back.

## Open items

1. **Storage and load (FinOps, needs a call before this runs for days).** About 20 MB of gzip snapshots per run x 48 runs = **about 0.95 GB a day, about 29 GB a month** in cip (`listing_observation.raw_snapshot`). Evetech accounts for 80% of it. Upstream that is roughly 4.2k Evetech page downloads a day. Cheap options (orchestrator or Warren decides; not built here): keep the raw snapshot only when parsing fails, or when price/stock changed since the previous observation; a retention job (latest N per listing); a per-site poll interval (the design's `poll_minutes` setting, U2). Stopgap: remove the two flags from `$WorkerListingEnv` and restart the worker.
2. **Amazon CAPTCHA pages (HTTP 200).** These are not paused under D-0063's 403/429 rule. Options: treat a detected CAPTCHA page as a refusal (pause, never solve), or stop polling Amazon until N-0085 decision 1. Recorded with `finding.defer`.
3. 42 Takealot dead links need rediscovery (U2, N-0102). The 52 Evetech out-of-stock pages are worth a spot check by eye.
4. Durability: the site pause is in Redis (TTL) and `consecutive_failures` is in `meta_json`, until U2's M2 (`listing_site_state`) and M4 (`consecutive_failures`, `next_due_at`). `delisted` listings are not polled yet (design: weekly). `retired` does not exist yet.
5. The single solo worker is busy about 4 min of every 30 with polling. Other tasks queue behind it (accepted in design CHALLENGE 7). The 600 s limit stops new fetches; one in-flight Takealot check can add up to 3 x 20 s. There is no Celery hard time limit.
6. The UA says Chrome/150 (extrapolated from Chrome's 4-week release cadence; my knowledge is dated). Refresh it to the current stable major version from time to time.
7. Uncommitted. Nothing was committed or staged.

## Round 2 (2026-10-08, after GOV-008 FAILED narrow, defect D1)

Run RUN-20261007-N0101-IMPL, round 2. Lenses: backend-engineer (owner), test-engineering-specialist. Trigger: `N0101_VERIFY.md` (RUN-20261008-N0101-VER) defect D1. Self-verification only; GOV-008 re-verification is a later, separate run.

### Cause (FACT, confirmed in this run)

`default_site_pause_store()` ran `from app.core.config import settings` inside `try/except Exception`. `app.core.config` has no module-level `settings` (only `get_settings()`, `@lru_cache`, line 194). The `ImportError` was caught and logged as "Redis unavailable", so the store was always the process-local `MemorySitePauseStore`. The round 1 claim "the site pause is in Redis" (Files changed, Open item 4) was false as built.

The app has no shared Redis client helper. The worker builds Celery from `get_settings()` (`worker/celery_app.py`: broker `celery_broker_url`, db 1). The app-data Redis is `get_settings().redis_url` (db 0), which is what `app/query/cache.py` meant to use. The pause store now uses that.

### Change (`apps/api/app/services/listing_capture/site_pause.py`, the only product file changed)

- `import redis` and `from app.core.config import get_settings` are module-level imports, so a broken import fails loudly when the module loads and is never treated as an outage. `redis` is a hard dependency (`requirements.txt`: `redis>=5.2.0,<5.3.0`).
- `_redis_client()` builds `redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=0.5, socket_timeout=2)`.
- `default_site_pause_store()` pings. It falls back to the process-local store **only** on `redis.exceptions.ConnectionError`, `redis.exceptions.TimeoutError` or `OSError` (Redis genuinely unreachable). It logs one warning per outage, naming the exception type and message (no URL or secret): `listing capture: Redis unreachable (<Type>: <msg>); site pauses kept in this process only`. When Redis answers again it logs `Redis reachable again` once and resets the flag. Any other error (AttributeError, ImportError, ResponseError, a bad URL) is raised, not hidden.
- Module docstring updated to match. Store classes, pause rules, key prefix and TTL are unchanged.

### Tests

New file `apps/api/tests/test_listing_capture_site_pause_store.py`, 9 tests, no real Redis (`redis.Redis.from_url` replaced by a fake):
- Reachable client gives `RedisSitePauseStore`, never the memory store, with `from_url` called with `get_settings().redis_url` and no warning.
- Redis store round-trips a pause record under `cip:listing_capture:site_pause:<marketplace>`.
- ConnectionError, TimeoutError and OSError on ping each give the shared memory store and **exactly one** warning across two calls, naming the exception type.
- After an outage and a recovery, a second outage warns again ("reachable again" logged once).
- AttributeError, ImportError and ResponseError on ping are raised, with no fallback warning.

Commands (from `apps/api`, `apps/api/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`):
- New file alone: **9 passed**.
- N-0101 set (new file + `test_listing_capture_n0101_polling.py test_listing_capture_lc_u1.py test_listing_capture_p5_live_fetch.py test_takealot_listing_fetch.py test_listing_auto_finder.py test_listing_intelligence_v1.py test_cpor_activation.py test_cst_listing_seed_fields.py`): **110 passed** (101 before + 9).
- Neighbours (`test_grid_fields.py test_semantic_overlay_governed.py test_promo_plan_builder.py`): **102 passed**.

Mutation M-D1 (`N0101_r2_mutate.py apply`): `default_site_pause_store()` replaced by the original body (swallowed `from app.core.config import settings` behind `except Exception`). Result: **9 failed, 0 passed** in the new file (the Redis test fails with the store being `MemorySitePauseStore`; the log-once tests fail on the message; the code-error tests fail because nothing is raised). Restored (`restore`): sha256 of `site_pause.py` `8ebf07f7...99051` before mutation and after restore; `grep MUTANT` = 0; backup deleted; N-0101 set re-run **110 passed**. The mutant was on disk for a few seconds; the worker was not restarted until after the restore.

### Live (2026-10-08, SAST)

- 09:27:39 `scripts/cip-supervisor-stop.ps1 -Component worker -Restart`. Supervisor log: stop tree 37116 (operator restart), `worker: started pid 44904 (launch 2; CIP_LISTING_LIVE_FETCH present=True, CIP_LISTING_CAPTURE_SCHEDULE present=True)` at 09:27:40. Worker ready 09:27:54.
- `cip-supervisor-status.ps1 -Local` at 09:28:41: worker **healthy** pid 44904, worker=1 beat=1; wsl, redis (`PING -> +PONG`), api (pid 24948, unchanged since 2026-10-07 16:59) and web (pid 45608) healthy; local api /health 200, /auth/me 401, web /login 200. Only the worker was restarted. The tunnel restart at 09:27:41 (launch 6) is the supervisor's own 10-minute `/ready` rule (launches 4 and 5 at 09:07 and 09:17); the tunnel was already unhealthy before this run (VERIFY F4, N-0073 scope). New public hostname `pole-inspections-medicine-quickly`, public 530 at 09:28:54.
- Store check (`N0101_r2_live_store.py`, venv python from `apps/api`, read-only: ping, scan, get; no write): `store_type RedisSitePauseStore`, `redis_host localhost port 6379 db 0`, `site_pause_keys 0`, `get amazon/evetech/takealot None`. No pause was created.
- First beat run on the new worker (09:30:00): worker log 09:28 to 09:35 has **no** "Redis unavailable" or "Redis unreachable" line (round 1 worker logged "Redis unavailable" at the start of every run). Result: `polled 176, failed 0, skipped_backoff 42, skipped_paused {}, paused_sites {}, stopped_reason None, duration_seconds 312.703`, task succeeded in 313 s. No 403/429 occurred, so no pause key exists; Redis persistence of an actual pause is shown by the unit round-trip test, not live.

- **Open: the API process still runs the round 1 code.** API pid 24948 has been up since 2026-10-07 16:59 and was not restarted (brief: worker only). Until the API restarts, a manual `POST .../listing-capture/poll` there still uses its own process-local store, so it does not see worker pauses. The next API restart picks up the fix with no other change. That poll endpoint returns 503 there anyway, because the API is not given `CIP_LISTING_LIVE_FETCH`, so this has no effect today.

### Finding (recorded `finding.defer`, not fixed: outside write scope)

`apps/api/app/query/cache.py` `_try_redis()` has the same bug: `from app.core.config import settings` inside `except Exception`, logged at DEBUG. The P3-2 query cache has never used Redis. Same fix shape applies.

### Files (round 2)

- Changed: `apps/api/app/services/listing_capture/site_pause.py` (untracked, uncommitted).
- New: `apps/api/tests/test_listing_capture_site_pause_store.py` (untracked, uncommitted).
- Audit: `N0101_r2_mutate.py`, `N0101_r2_live_store.py`, payloads `N0101_r2_*.json`.
- Nothing committed or staged. No cip writes.

## Round 3 (2026-10-08): snapshot policy

Run RUN-20261007-N0101-IMPL, round 3. Lenses: backend-engineer (owner), test-engineering-specialist, database-specialist. Trigger: finops FAIL (round 1: about 20 MB of gzip page snapshots per run, about 0.95 GB a day in cip) and Warren's decision of 2026-10-08: store a raw page snapshot only when the extracted fields changed versus the listing's previous successful observation, or the fetch/parse failed; clear raw snapshots older than 90 days (payload only; rows and extracted fields kept forever); all retailers. No migration: `listing_observation.raw_snapshot` is already nullable (read on cip: `is_nullable = YES`). Self-verification only; GOV-008 is a later, separate run.

The round took two sessions. The first wrote the code and tests and restarted the worker at 14:49:56 SAST, then hit a usage limit while waiting for the 15:00 beat run. The second session (this write-up) re-acquired the lease, re-ran the tests and the mutation, checked the live worker and measured cip read-only.

### Change

`apps/api/app/services/listing_capture/registry.py`
- `previous_successful_observation(session, listing_id)`: the listing's latest observation with HTTP 200 and `parse_status = 'ok'`, by `fetched_at desc, id desc`, with `raw_snapshot` deferred (not loaded). It runs before the new observation is added, so autoflush cannot find the new row. A non-ORM result (mocked session) counts as "no previous", which keeps the snapshot (the safe direction).
- `extraction_unchanged(prev, parsed, parser_version)`: true only if the parse is ok and parser version, price (compared as stored, `Numeric(18,4)`, so a float parse equals a DB Decimal), availability, promo badge and every key the parser put in its own flags (method, VAT basis, Takealot PLID/TSIN/SKU, RRP, canonical URL, SKU match) all match. Fetch-side flags, CPOR activation and status transitions are not compared.
- `record_observation`: snapshot reason, in order: `fetch_failed` (status not 200, or a fetch-side reason), `parse_failed`, `first_observation` (no previous successful observation), `changed`, and `status_transition` (a status change keeps the page even when the fields match, e.g. a recovered dead link at the same price). Kept rows carry `parse_flags.snapshot_stored = <reason>`. Otherwise the row is stored with `raw_snapshot = NULL`, `parse_flags.snapshot_skipped = 'unchanged'` and `parse_flags.unchanged_since_observation_id`. Extracted fields, CPOR activation and status logic are unchanged and still written on every row.
- `reparse_observation`: an observation without a payload (skipped as unchanged, or cleared by retention) is returned untouched and logged at INFO. Its extracted fields are never overwritten by a parse of nothing.

`apps/api/app/services/listing_capture/snapshot_retention.py` (new)
- `clear_expired_snapshots(session, now, retention_days=90, batch_size=5000, time_limit_seconds=240)`: keyset batches (`id > after_id ... order by id limit n`, rows with `fetched_at < now - 90 days` and a payload), `UPDATE ... SET raw_snapshot = NULL` plus `parse_flags.snapshot_cleared = {reason: retention, retention_days, cleared_at}` merged into the existing flags (a JSON null or non-object is handled without loss), commit per batch, no new batch after the time limit. It never deletes rows (`rows_deleted` is always 0). Postgres reuses the freed TOAST space after (auto)vacuum; the file does not shrink without `VACUUM FULL`.

`apps/api/app/worker/tasks.py` + `celery_app.py`
- Task `listing_capture.clear_expired_snapshots` (honours `dev_beat_disabled`), beat entry `listing-capture-snapshot-retention`, daily at 03:15.

### Tests (re-run this session, from `apps/api`, `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`)

`apps/api/tests/test_listing_capture_snapshot_policy.py`, 17 no-DB tests: first observation stores; unchanged stores no snapshot but keeps fields and points at the previous id; changed price stores; changed availability or promo stores; failed parse stores, and the next ok observation compares with the last success (not the failure); failed fetch stores even when fields match; parser version change stores; DB Decimal price equals float parse; status transition keeps the snapshot; Takealot parser-flag change counts as changed; mocked session without a previous observation keeps the snapshot; shape of the previous-successful query; re-parse skips an observation without a snapshot; re-parse with a snapshot still re-parses; retention batches by keyset, commits each batch and never issues DELETE; retention stops at the time limit; beat entry is daily 03:15 and the task is registered.

`apps/api/tests/test_listing_capture_snapshot_db.py`, 2 Postgres tests, cip_test only (skip on any other database), one transaction always rolled back: (1) first / unchanged / changed price / failed parse through `record_observation`, then re-parse of the payload-less row is a no-op; (2) retention with rows at 120 d (already empty), 100 d, 90.5 d, 89.5 d and 0 d: only the 100 d and 90.5 d payloads are cleared, extracted price and existing flags kept, `snapshot_cleared` added, row count unchanged, 89.5 d and today untouched, a second run clears 0. Run with `N0101_r3_run_db_tests.py` (points DATABASE_URL(_SYNC) at cip_test in-process; refuses any other name).

Results:
- Snapshot policy file + N-0101 set (`test_listing_capture_site_pause_store.py test_listing_capture_n0101_polling.py test_listing_capture_lc_u1.py test_listing_capture_p5_live_fetch.py test_takealot_listing_fetch.py test_listing_auto_finder.py test_listing_intelligence_v1.py test_cpor_activation.py test_cst_listing_seed_fields.py`): **127 passed** (110 + 17).
- Same + neighbours (`test_grid_fields.py test_semantic_overlay_governed.py test_promo_plan_builder.py`): **229 passed** (127 + 102).
- cip_test DB file: `current_database() = cip_test`, **2 passed**, `listing_observation` rows 0 before and 0 after (rolled back).

Mutation M-S1 "always store the snapshot" (`N0101_r3_mutate.py apply`: `if snapshot_reason is None:` became `if False:`): policy file **5 failed, 12 passed** (unchanged; changed availability/promo, whose unchanged leg fails; failed-parse-then-ok; Decimal price; Takealot flag change). DB file **1 failed, 1 passed** (the unchanged row still had a payload). Restored (`restore`): `registry.py` sha256 `3f46e1c2...c747757` before the mutation and after restore, `grep MUTANT` = 0, backup deleted. The 229-test run above was after the restore. The worker was not restarted during or after the mutation, so it never loaded the mutant.

### Live (2026-10-08, SAST)

Worker: `cip-supervisor-status.ps1 -Local` at 20:55: worker **healthy**, wrapper pid 44720 (launch 2), worker=1 beat=1, env `CIP_LISTING_LIVE_FETCH` and `CIP_LISTING_CAPTURE_SCHEDULE` present. Process creation times (CIM): wrapper 44720 at **14:49:56**, both python children at **14:50:00**; Celery `ready` 14:50:13. Round 3 file mtimes: `tasks.py` and `celery_app.py` 14:38, `snapshot_retention.py` 14:44:41, `registry.py` 14:48:32. The worker started after the last round 3 change, so it runs the round 3 code; no restart was needed this session. API, web, wsl, redis and tunnel were healthy and not touched.

Beat runs on the round 3 worker (worker log task results):

| Run | Result | Note |
|---|---|---|
| 15:00 | polled 175, failed 1, skipped_backoff 42, 327 s | failed = listing 218, `http.client.IncompleteRead` raised from `default_http_get` (no observation row; finding 3) |
| 15:30 | polled 176, failed 0, 356 s | |
| 16:00 | polled 176, failed 0, 334 s | |
| 16:30 | polled 176, failed 0, 236 s | |
| 17:00 | polled 176, failed 0, 310 s | |
| 17:30-19:00 | none | machine asleep: worker log silent 17:29:40-19:30:24; System log Kernel-Power 506/507 at 17:28-17:29, 507 at 19:30:24 |
| 19:30 | polled 31, stopped_reason time_limit, 4,442 s | sleep 19:30:38 (Kernel-Power 42) to 20:44:27 (507); 30 fetches just before sleep failed with status 0; on wake the monotonic clock was past 600 s, so the run stopped |
| 20:45 | polled 218, failed 0, skipped_backoff 0, 245 s | the 24 h dead-link back-off windows had expired, so the 42 backed-off Takealot links were retried |

cip, READ ONLY (`N0101_r3_live_probe.py baseline`, `N0101_r3b_live_breakdown.py 3126`, `N0101_r3b_rowsize.py 3126`; each printed `current_database() = cip` and ran under `SET TRANSACTION READ ONLY` (`transaction_read_only = on` printed); venv python, `get_settings().database_url_sync` with `postgresql+psycopg`; nothing secret printed). Rows grouped by 30-minute slot:

| Slot | Rows | With snapshot | Without | Snapshot bytes |
|---|---|---|---|---|
| 13:00 (round 2 worker) | 167 | 167 | 0 | 17.27 MB |
| 13:30 (round 2 worker) | 176 | 176 | 0 | 18.48 MB |
| 14:00 (round 2 worker) | 176 | 176 | 0 | 17.26 MB |
| 14:30 (round 2 worker) | 176 | 176 | 0 | 17.87 MB |
| **15:00** | 175 | 36 | 139 | **3.68 MB** |
| **15:30** | 176 | 25 | 151 | **6.47 MB** |
| **16:00** | 176 | 25 | 151 | **6.37 MB** |
| **16:30** | 176 | 51 | 125 | **0.77 MB** |
| **17:00** | 176 | 26 | 150 | **5.87 MB** |
| 19:30 (cut by sleep) | 30 | 30 | 0 | 600 B (status 0 fetch failures, 20 B each) |
| 20:30 slot (the 20:45 run, plus 1 row at 20:44:27 from the 19:30 run) | 219 | 94 | 125 | 0.33 MB |

The five full regular runs averaged **4.63 MB** of snapshots (range 0.77-6.47), against 17.3-18.5 MB on the round 2 worker that afternoon and about 20 MB in round 1: **about 74% less**. Rows without a snapshot average **624 bytes** each (`parse_flags` is 522 B of that, mostly CPOR activation).

What is stored now (rows by marketplace and reason, ids > 3126):
- **Takealot and Evetech** are almost all `skipped:unchanged` (37/37 and 85-86/88 per run). Changed rows in five runs: 1 Takealot (price, promo, SKU flags) and 1 Evetech (price and availability).
- **Amazon is about 95% of the bytes**: 17-49 `parse_failed` rows per run at HTTP 200 (pages up to about 270 KB each; at 16:30 and 20:45 the 49 failed pages were 4-14 KB each), plus 2-5 `changed` rows per run (8 price-only; 2 parser-version changes). These are the CAPTCHA/robot pages of open item 2, stored because the decision keeps every failed parse.
- **Two Evetech listings (120, 121) return HTTP 404 every run and are stored every run as `fetch_failed`** (52.7 KB each, 105 KB per run). Their 404 page parses `ok` with a price (`method html_zar`), so the dead-link rule (404 **and** parse failed) never fires; they stay `active` and are never backed off. See finding 2.
- 20:45: 43 Takealot `fetch_failed` (status 0/404, or 200 with a fetch-side reason), 11 KB in total: the 42 retried dead links.

Growth (estimated from the measurements, not measured over days): 4.63 MB x 48 runs = **about 0.22 GB a day** of snapshots (was about 0.95), and about 5 MB a day of payload-less rows (176 x 48 x 624 B). With the 90-day retention, snapshot payload stops growing at about **20 GB** at this rate (0.22 GB x 90); rows grow about 1.9 GB a year, kept forever by decision. cip `listing_observation` is 455 MB now (473 MB is TOAST). The oldest row is 2026-08-09, so nothing is over 90 days yet (`with snapshot older than 90 d = 0`), and the first retention run that clears anything will be about 2026-11-07. Retention was **not run against cip** (brief); its only evidence is the cip_test test and the unit tests. Its first beat run will be 03:15 on 2026-10-09 and should report `snapshots_cleared 0`.

Not measured: the retention task on cip or in the worker; a full day of runs (the machine slept 17:29-20:44); a real status-transition snapshot live; vacuum reuse of cleared space.

### Findings (round 3)

1. **Amazon failed-parse pages dominate what is left** (about 95% of snapshot bytes). Kept as decided (a failed parse stores). Treating a detected CAPTCHA page as a refusal (open item 2; D-0063 pause, never solve), or N-0085 decision 1 on Amazon, would cut most of the remaining 0.22 GB a day. Not built: needs a decision.
2. **Evetech 404 pages parse as ok** (listings 120 and 121): never marked dead, never backed off, polled and snapshotted every run. Pre-existing dead-link rule (preserved in round 1), outside the snapshot scope. Recorded `finding.defer`.
3. **A fetch that raises records no observation.** Listing 218 at 15:00: `IncompleteRead` from `default_http_get` propagated to the poll loop (counted `failed`, logged with traceback), so no row and no snapshot exist for that failure. Pre-existing, outside the snapshot rule ("fetch failed" can only store a fetch that returned a status). Recorded `finding.defer`.
4. **Laptop sleep.** The 600 s run limit uses `time.monotonic()`, which on Windows counts sleep, so a run that sleeps stops on wake (19:30: 4,442 s, 31 polled). Fetches right before sleep fail with status 0 and are stored (20 B each, harmless). The runs due at 17:30-19:00 never happened. Not a code defect; noted for the always-on setup (N-0073).

### Files (round 3)

- Changed: `apps/api/app/services/listing_capture/registry.py`, `apps/api/app/worker/tasks.py`, `apps/api/app/worker/celery_app.py`.
- New: `apps/api/app/services/listing_capture/snapshot_retention.py`, `apps/api/tests/test_listing_capture_snapshot_policy.py`, `apps/api/tests/test_listing_capture_snapshot_db.py`.
- Audit: `N0101_r3_mutate.py`, `N0101_r3_run_db_tests.py`, `N0101_r3_cip_test_probe.py`, `N0101_r3_live_probe.py`, `N0101_r3_missing_probe.py`, `N0101_r3_replay_probe.py`, `N0101_r3b_live_breakdown.py`, `N0101_r3b_rowsize.py`, payloads `N0101_r3_*.json`, `N0101_r3b_*.json`.
- Nothing committed or staged. The only cip writes were the product's own poller observations; every probe ran READ ONLY. cip_test writes were inside rolled-back transactions.

### Ledger (round 3, `--run RUN-20261007-N0101-IMPL`)

`node.lease.acquire` (node rev 25), `evidence.add` x2 (this file; `snapshot_retention.py`), `node.quality` finops **fail -> pass**, testing, reliability and observability updated (all pass), `finding.defer` x2 (findings 2 and 3; finding 1 is round 1 open item 2, already deferred), `node.stage` -> **validate**, `node.lease.release`. Programme rev 1799. `program.py verify`: `integrity_ok true`; `gates_ok false` only for the existing acknowledged gate debt on N-0006, N-0013, N-0014, N-0015 and N-0016 (nothing on N-0101). No `node.verification`, no completion: GOV-008 re-verification is a different run.
