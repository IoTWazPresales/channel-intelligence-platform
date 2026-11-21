# CURRENT state

**Last updated:** 2026-11-21, coordinator continuation checkpoint. Task 1 is still in progress.
**Branch:** `feat/integrate-20261103`. Confirm actual HEAD with `git rev-parse`; the current product content pin is `041f1c65`.

## Branch and delivery

- Primary was fetched and fast-forwarded to remote `453e495d`, then Inventory product `055bc770` was merged locally as `041f1c65`.
- These two Inventory commits have not been pushed. Nothing was pushed or merged to `main`.
- Source Alembic graph has one head: `20261120_0065` (tenant settings 0064, private UI layouts 0065).
- Pre-existing untracked `.agents/`, `.eif/upgrade-history/`, `.eif/upgrade-work/`, and `apps/api/.env.bak-20261117` are preserved and unstaged.

## Database and environment

- Local Windows, Mode B: primary API on 8001, web on 3000, local PostgreSQL and Redis. No Docker.
- Last recovered live DB observation: Claude's read-only check at 2026-11-21 13:23 SAST returned `cip`, revision `20261118_0063`, and neither `tenant_setting` nor `user_ui_layout`.
- This coordinator has not freshly queried the DB, migrated it, written business data, or restarted primary services.
- Recovered backup: `C:/Users/warren_eliason/cip-apply-logs/20261121-premigrate/cip-full-owner-premigrate-20261121-032130.dump`, 3,350,658,181 bytes; backup log exit 0. Restore validity was not freshly proven.
- Old clone proof is insufficient: the shared `cip_test` was on Discovery revision `20261121_0065`; Claude restamped it to UI revision 0064 before applying 0065. Use a new disposable clone before relying on the live migration path. Preserve shared `cip_test`.
- Live changes remain subject to the operator's explicit migration authorization and the installed protected-database grant mechanism. The old Claude request was session-specific; do not bypass a denial or self-grant.

## What is working / evidence

- Inventory at the isolated 3107 server renders the existing `CoverLensView` inside `StockChrome` with real cover data. This is not live 3000 proof.
- Original hand-entered page is preserved at `/inventory/hand-entered`; independent review confirmed the same APIs, payloads, grid and preference keys.
- Independent focused review: 45 tests in 5 files, changed-file ESLint, nonincremental tsc and diff check passed, actual exits 0.
- Clean worktree at `041f1c65`: frozen install, full lint (0 errors, 48 warnings), full web suite (290 files / 1,784 tests), typecheck, and production build (84 pages), all actual exits 0.
- The primary full lint run was cancelled because old generated builds under `apps/web/.tmp` were included. It is not a PASS; the clean-checkout lint result above is the verified source check.

## In progress / not proven

- ONE task and ONE delegated agent at a time: Inventory correction, not accepted or deployed.
- Browser attempt 1 exposed an ambiguous test selector, now corrected. Attempt 2 rendered Inventory, then reached Login after a legacy cover redirect; it did not pass.
- Diagnosis proved `/stock?lens=cover&family=Notebook` returns 307 from 127.0.0.1 to localhost. Origin-local auth storage is absent at localhost, so `/auth/me` returns 401. No evidence of an expired/revoked session.
- The actual installed Next 15.5.15 adapter normalizes loopback origins and rewrites even a middleware-only Host correction. Supported fix is `skipMiddlewareUrlNormalize` plus a native URL from raw `request.url` for this redirect.
- Active child `/root/inventory_redirect_diagnose` may change only `apps/web/next.config.ts`, `apps/web/src/middleware.ts`, and its test in `lane-a1-20261120`; no commit, DB work or primary restart. Four new adapter regressions failed before the fix; all 31 original tests passed. Independent review follows.
- Isolated old-code server: PID 36340 on 127.0.0.1:3107, worktree `verify-inventory-20261121`, serving `041f1c65`. Rebuild/restart the owned server before checking any newer fix.
- Last primary deploy record (2026-11-21 00:35) is FAILED at Celery ping despite healthy component restarts. A supervisor health report is not proof that the worker accepts tasks.

## Queued scope (not concurrent)

1. Finish Inventory origin fix, independent review, final checks, and browser proof; then complete supported migration/deployment prerequisites before live acceptance.
2. Prove pending Line-up fix, database map and MapLibre prototype on running screens. They are in remote `453e495d`, not accepted live. Map prototype country/city/mall screenshots still need Warren's approval before switching maps.
3. Discovery V2: S1/S2/S3c/S5 branches are not integrated; S3a foundations remain uncommitted (64 recorded tests, incomplete lint); S4 has failed saved checks; S3b Crawlee finder is pending. Live discovery remains Preview-only; links require exact evidence.
4. Dashboard design is in `lane-c-20261120`. Warren approved the look, both themes, and stock health BELOW sales charts. Revised replenishment/aged-stock mock-up and product build are pending. The saved light screenshot duplicates dark; interactive theme switching is available.
5. AI-assisted import spec is on `docs/ai-import-spec-20261120`; implementation and three-customer clone proof remain pending. Requested read-only library review follows the original live lanes.

## Evidence and continuity

- Coordinator notes and gate logs: `.tmp/coordinator-20261121/` (local, not committed test evidence).
- Browser evidence: `.worktrees/verify-inventory-20261121/.tmp/coordinator-20261121/inventory-proof/` and `inventory-proof-first-attempt/`.
- Redirect and actual Next-adapter diagnosis: `.tmp/coordinator-20261121/inventory-redirect-diagnostic/`.
- Required `engineering-rules.mdc` is missing; no contents were assumed and no protected runtime files were repaired.
- Prior detailed state/decisions and historical claims are preserved in [CURRENT snapshot](CURRENT-snapshot-20261121-before-coordinator.md). Read the relevant backlog/decision and current code before resuming an older item.
