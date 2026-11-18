# Wave 2 verification harness

Recorded 2026-11-18 (CIP alignment Section D item 10). Branch `feat/w2-verification-matrix-20261118`.

This is the reusable tooling for **Wave 2: verify on the running web app** in
`docs/CIP_ORCHESTRATOR_WAVES.md` (PR #113). It was built and checked without a running app: the
browser matrix was only listed (`--list`) and its pure logic is covered by vitest. The figure
checker's unit tests run with database connections forbidden; its database test
(`test_figure_check_db.py`) is reported passing on `cip_test` by the coordinator and was not re-run
in the fix round that added the views and the readonly session rule. The pass itself (deploy, test
instance with real files, live run) still needs authorization; see the last section.

## Parts

| Part | File | What it does |
|---|---|---|
| Matrix | `apps/web/src/lib/verification/matrix.ts` | Viewports (desktop 1280x800, mobile 390x844), states (`loaded`, `empty`, `error`, `loading`), the `WAVE1_ROUTES` view manifest (paths, `?tab=` lenses, `?plan=<id>`), `buildMatrix`, `isWriteRequest`, `resolveAuth` (readonly never signs in), `evaluateErrorIndication` and `interceptionProblem` (state checks). Pure TS, no Playwright. |
| Matrix tests | `apps/web/src/lib/verification/matrix.test.ts` | Vitest: matrix size and ids, all four states in both modes, dynamic views skipped or discovered, every manifest path is a real page, every query view is selected by a value the app reads and mounts a test id that exists, login counts as a write, `resolveAuth` refuses readonly without a session, an informational alert is not an error indication, a state case fails when nothing was intercepted. |
| Browser pass | `apps/web/e2e/wave2-matrix.spec.ts` + `apps/web/playwright.wave2.config.ts` | Takes a session once per worker (an existing one in readonly; login only in full), visits every case, guards writes, screenshots, checks the state, writes results. No webServer. |
| Figure checks | `apps/api/scripts/verify/figure_check.py` | Read-only SQL per figure, compared with the page figure within a tolerance; markdown + JSON output. |
| Figure tests | `apps/api/tests/unit/test_figure_check_guard.py` (no DB), `apps/api/tests/test_figure_check_db.py` (`cip_test`; not run yet) | SQL screen, comparison maths, read-only session, `--expect-db` refusal. |

## The route manifest

`WAVE1_ROUTES` lists the in-app **views** Wave 1 touched. Each entry has its `source` (the W1-A..W1-E
item or the `docs/memory/CURRENT.md` merge line) and is checked by the vitest suite to exist as
`apps/web/src/app/(app)/<path>/page.tsx`. Paths are static segments only.

Some Wave 1 work does not render on the bare page, so a view is a path plus a selector:

| View | Why it is separate |
|---|---|
| `/promotions?plan=<id>` | The quantity and export workspace (`data-testid="plan-workspace"`) mounts only with `?plan=`; bare `/promotions` is the plan list. The id comes from `CIP_VERIFY_ID_PLAN`, or (when unset) the spec reads it read-only: it opens `/promotions` in a second page of the same session and takes the first id of the `GET /api/v1/cpor/cases` list the app itself fetches. No case found: the cases are recorded `skipped` with the reason (a gap, never a pass). |
| `/listing-capture?tab=sites`, `?tab=links`, `?tab=coverage` | The Sites, Links and Coverage lenses mount only for their `tab` value (`marketLensFromLocation`). `?tab=proposals` (N-0103) and `?tab=intelligence` (N-0076 activation) are listed for the same reason. |
| `/admin/cst-steward?tab=stock-gap` | The N-0110 stock-gap section mounts only for that tab. |
| `/commercial-planner/cpor-cases/[id]` | Id from `CIP_VERIFY_ID_CPOR_CASE`, or the same read-only lookup. |

A view that names a `mount` test id fails its `loaded` and `loading` cases when that element is not
visible, so a page that silently shows the default lens cannot pass as the lens. The vitest suite
checks that each query value is one the app reads and that each `mount` id exists in the app. To
add a view, add an entry with its source; the tests refuse a path that has no page. Case ids and
screenshot names use `<path>~<query>`, for example `listing-capture~tab-sites@desktop#loaded.png`
and `promotions~plan-id@mobile#error.png`.

The mapping from a wave item to a page is the harness author's reading of the shell navigation
(`apps/web/src/features/shell/navConfig.ts`) and the page components. Review it before the pass;
a missing route is a gap in the evidence, not proof the route is fine.

## States

| State | Produced by | Passes when |
|---|---|---|
| `loaded` | Real responses | No MUI error alert is visible, no uncaught page error, no crash or not-found screen; the view's `mount` element is visible. |
| `empty` | Each GET `/api/**` is fetched, then every JSON array becomes `[]` (count/total numbers become 0) | At least one response was emptied, and an empty-state text (`/no .*(data\|results\|rows…)\|nothing\|empty/i`) or grid "no rows" overlay is visible. |
| `error` | Each GET `/api/**` is answered with HTTP 500 `{"detail": "Wave 2 verification: simulated server error"}` without reaching the server | At least one request was intercepted **and** an error-specific indication is visible: the injected detail text, an error-severity MUI alert, an alert (no info/success/warning severity) with failure wording, or `Request failed (500)` / `Server error (500)`. An informational alert (every MUI `Alert` has `role="alert"`) or the word "error" in page copy does not count. |
| `loading` | Each GET `/api/**` is held `CIP_VERIFY_LOADING_DELAY_MS` (default 4000) | At least one request was held, and a progress bar, spinner, skeleton or `aria-busy` element is visible before the responses arrive; then as `loaded`. |

A state case whose interception never fired fails with `<state>: no GET /api/** request ... so the
page was never put in this state`. `results.ndjson` carries the counts as `intercepted`
(`{error, empty, loading}`) and, for `error`, the `errorIndication` that was accepted.

All four states run in **both** modes. They are produced in the browser by intercepting GET
requests (`empty` does a real GET and edits the response; `error` never reaches the server), so
readonly runs need no data change and no write. Auth endpoints (`/api/v1/auth/**`) are never
rewritten, so the session stays valid.

## Write guard (both modes)

Before every navigation, `page.route('**/*')` checks each request with `isWriteRequest`: any
method other than GET, HEAD and OPTIONS is a write. **POST `/api/v1/auth/login` is a write**: it
commits an `AuthSession` row. Writes are **aborted** and listed in the case's `blockedWrites`. The
login request is let through only in **full** mode, only in the sign-in step (`allowLogin`), and is
logged; the page cases never get that exemption.

- **readonly** (live app): never signs in (see Sessions below). Blocked writes are listed in the
  attachment and results; they do not fail the case. No form is submitted at all.
- **full** (test instance): a blocked write fails the case, because the spec does not interact, so
  anything blocked was sent while the page rendered. `CIP_VERIFY_ALLOW_WRITES=1` lets writes
  through (still listed as `allowedWrites`); it is never the default and should be set only on the
  test instance.

Expect blocked POSTs on pages that read through POST endpoints (for example dashboard widgets that
run `POST /query/v2/execute`). On the live app that means those widgets render without data in the
readonly run; record it as a finding, do not relax the guard.

## Sessions

| Mode | Session |
|---|---|
| readonly | An **existing** session only: `CIP_VERIFY_STORAGE_STATE=<Playwright storageState file>` or `CIP_VERIFY_SESSION_TOKEN=<token>`. The run **refuses to start** (clear error at load, also for `--list`) when neither is set, even if `CIP_VERIFY_EMAIL`/`CIP_VERIFY_PASSWORD` are set; those are ignored in readonly. The login page is never opened. |
| full | The same two, else the verification user's login (`CIP_VERIFY_EMAIL`, `CIP_VERIFY_PASSWORD`), which writes a session row on the **test instance** only. |

The app keeps its token in `localStorage` under `cip.auth.token.v1`; the spec turns
`CIP_VERIFY_SESSION_TOKEN` into a storage-state file under `.tmp/wave2/auth/` (git-ignored). The
operator issues the readonly session out of band (for example a storageState saved after the
operator's own sign-in); this harness does not create one on the live database. Never copy a token
or a storage-state file into the repository or an audit.

## Order of a pass

1. **Deploy** Wave 1 (brief section 8) and record the deployed commit.
2. **Test instance** on `cip_test` with the uploaded real files and any queued migrations (brief section 7).
3. **Full run against the test instance** (all states):

   ```bash
   # from apps/web
   CIP_VERIFY_BASE_URL=<test instance URL> CIP_VERIFY_MODE=full \
   CIP_VERIFY_EMAIL=<verification user> CIP_VERIFY_PASSWORD=<from the operator> \
   CIP_VERIFY_ID_CPOR_CASE=<optional case id on cip_test> CIP_VERIFY_ID_PLAN=<optional plan id> \
   CIP_VERIFY_FIGURES=<optional checks.json> \
   npx playwright test -c playwright.wave2.config.ts
   ```

4. **Figure checks on the same database** as the run (`cip_test` for step 3):

   ```bash
   # from apps/api
   python scripts/verify/figure_check.py --checks <checks.json> \
     --db-url <postgresql+psycopg:// URL for cip_test> --expect-db cip_test \
     --page-figures ../web/.tmp/wave2/figures.ndjson --out ../web/.tmp/wave2/figures
   ```

5. **Readonly run against the live app** (all states by interception, one worker, no retries, no
   login): same command as step 3 with `CIP_VERIFY_MODE=readonly`, the live URL and an existing
   session (`CIP_VERIFY_STORAGE_STATE` or `CIP_VERIFY_SESSION_TOKEN`; no email or password). Then step 4 with a
   read-only connection to `cip` and `--expect-db cip` (the checker opens a read-only session and
   refuses anything but a single SELECT, but the operator decides whether it may connect to `cip`).
6. **Fix units** for each defect (Wave 1 rules, review, merge), then repeat steps 3-5 for the
   routes they touched. Wave 2 ends when the pass is clean.
7. **Write `docs/audits/WEBAPP_VERIFICATION_<date>.md`** (below).

Delete `apps/web/.tmp/wave2/` before a pass: results and figures are appended, each line carries
the run's `runId`.

## Environment variables

| Variable | Required | Meaning |
|---|---|---|
| `CIP_VERIFY_BASE_URL` | yes | Running web app (origin). The config throws without it; it never starts a server. |
| `CIP_VERIFY_MODE` | yes | `readonly` (live) or `full` (test instance). Anything else throws. |
| `CIP_VERIFY_STORAGE_STATE` | readonly: this or the token | Path of a Playwright storageState file holding an existing signed-in session. Used as is (no login, no copy). Not together with the token. |
| `CIP_VERIFY_SESSION_TOKEN` | readonly: this or the file | Existing session token; written to a storage-state file for the run. Not together with the file. |
| `CIP_VERIFY_EMAIL`, `CIP_VERIFY_PASSWORD` | full mode without a session | Verification user, entered through the login page once per worker (a write on the test instance). Ignored in readonly. Never hard-coded. |
| `CIP_VERIFY_ID_CPOR_CASE` | no | Concrete id for `/commercial-planner/cpor-cases/[id]`; without it the spec looks one up read-only, and records the cases `skipped` if there is none. Letters, digits, `_`, `-` only. |
| `CIP_VERIFY_ID_PLAN` | no | Concrete plan (case) id for `/promotions?plan=<id>`; same lookup and `skipped` rule. |
| `CIP_VERIFY_ALLOW_WRITES` | no | `1` lets writes through in **full** mode only. Default off. Ignored in readonly. |
| `CIP_VERIFY_FIGURES` | no | Checks JSON; for checks with a `selector`, the `loaded` cases on that `route` capture the page figure. |
| `CIP_VERIFY_LOADING_DELAY_MS` | no | Hold time for the `loading` state (default 4000). |
| `CIP_VERIFY_IDLE_TIMEOUT_MS` | no | Network-idle wait (default 20000). Not reaching idle is recorded (`networkIdle: false`), not a failure. |
| `CIP_VERIFY_RUN_ID` | no | Set by the config if absent (ISO timestamp). |

Figure checker flags: `--checks`, `--db-url` (required; `postgresql+psycopg://` or `postgresql://`),
`--expect-db` (required), `--out` (directory), `--page-figures` (optional), `--statement-timeout-ms`.

## Checks file

```json
[
  {
    "name": "brief.open_cases",
    "route": "/brief",
    "selector": "<CSS selector of the figure on the page>",
    "sql": "SELECT count(*) FROM <table> WHERE <condition with %(param)s>",
    "params": {"param": "<value>"},
    "expected": null,
    "tolerance": "0.5%"
  }
]
```

`expected` is the page figure: type it in, or leave it `null` and pass `--page-figures` so the
value captured by the spec is used (if desktop and mobile show different values the check fails as
`page_inconsistent`). `tolerance` is absolute (`0.01`) or relative to the database value (`"0.5%"`).
Each query must return one row and one column. Checks files are run data: keep them out of the
repository if they name a customer, retailer, distributor, site or product.

The SQL screen refuses: anything not starting with `SELECT` or `WITH`; `;` batches; dollar
quoting; and the words `INSERT UPDATE DELETE MERGE TRUNCATE ALTER DROP CREATE GRANT COPY CALL DO
INTO` anywhere (string literals included), plus session-changing or external functions
(`set_config`, `dblink`, `pg_terminate_backend`, `nextval`, `pg_sleep`, ...). Rewrite a query that
trips on a literal (for example compare with a parameter instead).

## Outputs

All under `apps/web/.tmp/wave2/` (git-ignored):

| Path | Content |
|---|---|
| `results.ndjson` | One line per case: `id`, `route`, `url`, `viewport`, `state`, `status` (`pass`, `fail` or `skipped` with `skipReason`), `problems`, `consoleErrors`, `pageErrors`, `blockedWrites`, `allowedWrites`, `intercepted`, `errorIndication`, `networkIdle`, `screenshot`, `runId`, `mode`. A `skipped` case is a gap in the evidence, not a pass. |
| `screens/<case id>.png` | Full-page screenshot, e.g. `screens/brief@desktop#loaded.png`. |
| `figures.ndjson` | Page figures captured for checks with a `selector`. |
| `figures/figure_checks.md`, `.json` | Figure check table and machine-readable results (when `--out` points there). |
| `report.json`, `test-results/` | Playwright JSON report and per-test attachments (`wave2-case.json`). |
| `auth/worker-<n>.json` | Storage state written from `CIP_VERIFY_SESSION_TOKEN` or a full-mode login. Contains a session token: never copy it into the repo or an audit. |

## Feeding `docs/audits/WEBAPP_VERIFICATION_<date>.md`

For each run (test instance, live): the deployed commit, mode, `runId`, and a table built from
`results.ndjson` (case id, status, problems, blocked writes) with each screenshot referenced by its
path. Then the figure check table from `figure_checks.md` with the database it ran on. Then the
defects: each failing case or mismatch becomes a fix unit with its case id, and the re-run that
closed it. Lab/spec comparisons (MIGRATE / CORRECT / BLOCKED) are separate and not produced by this
harness. Copy no session token, credential or customer data into the audit.

## What still needs authorization

- **Deploy** of the merged Wave 1 (brief section 8).
- **Test instance** on `cip_test` with the uploaded real files and queued migrations (section 7).
- **The live read-only run** against the deployed app, and whether the figure checker may open a
  read-only session on `cip`.
- **A verification user and its credentials** for the test instance (`CIP_VERIFY_EMAIL` /
  `CIP_VERIFY_PASSWORD`), and **an existing session for the live readonly run**
  (`CIP_VERIFY_STORAGE_STATE` or `CIP_VERIFY_SESSION_TOKEN`) issued by the operator. No account or
  session is added to `cip` by this work, and readonly mode never signs in.
- **Running `apps/api/tests/test_figure_check_db.py` on `cip_test`**: reported passing by the
  coordinator; re-run it on the test instance before the pass.
- Tracked as BACKLOG-249.
