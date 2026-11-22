# CURRENT state

**Last updated:** 2026-11-22. Warren's live migrations verified; Inventory is deployed and browser-verified. Initial deploy-script failure is preserved alongside supplemental worker/stability evidence.
**Branch:** `feat/integrate-20261103`. Product content pin `2d374040`; confirm actual HEAD with `git rev-parse`.

## Branch and delivery

- Inventory product `055bc770` and origin correction `f8bb446f` are independently reviewed, integrated (`041f1c65`, then `2d374040`) and pushed to the integration branch. Lane `feat/lane-a1-nav-20261120` is also pushed at `f8bb446f`.
- Deployed integration checkout `b3b54f5e` through the supported script; no main merge/push. Product content remains `2d374040` (later commits are documentation only).
- Source Alembic head is `20261120_0065` (tenant settings 0064, private UI layouts 0065).
- Pre-existing untracked `.agents/`, `.eif/upgrade-history/`, `.eif/upgrade-work/`, and `apps/api/.env.bak-20261117` are preserved and unstaged.

## Database and environment

- Local Windows, Mode B: API 8001, live web 3000, local PostgreSQL/Redis. No Docker.
- Warren ran the approved operator wrapper. Upgrade 0063 -> 0064 -> `20261120_0065` and Alembic current exited 0. Coordinator independently rechecked `cip`, owner postgres, 127.0.0.1:5432 in a read-only transaction: both new tables exist; columns/constraints/indexes/grants match rehearsal, all 798 existing relation metadata entries and representative counts are unchanged. Both new tables were empty at this check.
- Fresh operator backup `cip_20261122_144208.dump`: 3,355,093,451 bytes; SHA256 `bcff1ef7b4f06362e5619cd4900d0d0a6138b9a408e67c9f49ed1f051c3be985`, independently rehashed. Actual backup/list/upgrade/current and schema evidence: `.tmp/operator-ui-migration-20261122T124159Z-b48d2c53/`.
- Coordinator did not execute the protected migration; Warren did. Coordinator subsequently restarted API, worker and web using `scripts/cip-deploy.ps1 -Execute`. Existing application startup/scheduled tasks and browser sign-in use their normal flows.
- Recovered Nov21 backup remains preserved. Fresh Nov22 owner backup, TOC listing and real restore passed: 3,353,527,730 bytes, SHA256 `c7c14cd993418f78d6acac84667101648e11db45311f3bd50a7b3b104a11f152`. Backup and proof are under `.tmp/coordinator-20261122/migration-proof/`.
- Shared `cip_test` is preserved: its earlier proof restamped Discovery revision `20261121_0065` to UI 0064 before applying 0065. That is insufficient for the intended natural 0063 -> UI0065 transition.

## What is working / evidence

- `/inventory` reuses `CoverLensView` inside `StockChrome`; hand-entered stock is retained at `/inventory/hand-entered`, with unchanged APIs, payloads and grid preference keys.
- Legacy cover redirects preserve filters and incoming origin. Actual Next 15.5.15 adapter regressions failed before the fix. Supported normalization option plus native request URL/incoming Host fixed the origin change; forwarded-host/query values do not select destinations.
- Independent final review: no blocker; 52 middleware tests and 6 extra adapter edge checks passed.
- Final clean worktree `2d374040`: lint 0 errors / 48 warnings, 290 web files / 1,805 tests, typecheck, and production build (84 pages), all actual exits 0.
- Nov22 browser proof `inventory-proof-fixed-build-3`: actual exit 0, six checks passed: Inventory cover, three legacy filter-preserving redirects, hand-entered page, and Movement route/selected tab. All four redirect hops retain 127.0.0.1:3107. Login 200, no page errors or blocked business writes.
- Verification limit: isolated web 3107 against the existing API; not live web 3000. Movement data was still loading, so only its route/tab is proven. Earlier failed harness/sign-in/origin evidence remains preserved.
- **Proven live Nov22:** six browser navigation checks passed on 127.0.0.1:3000, login 200, no page errors/blocked writes; all four legacy redirect hops stayed on the same origin. Inventory cover has real charts/metrics; hand-entered page and Movement route/tab are preserved. Proof: `.tmp/coordinator-20261121/inventory-live-20261122-1/`. Movement dataset acceptance remains outside these route checks.
- Supported deployment rebuilt 84 pages, BUILD_ID changed `kIYO9J_leRx3BlIbkbQIY` -> `WfiWBIVESYJytPrLZcybX`, ordered API/worker/web restarts healthy, readiness 200. Supplemental samples 60.057 seconds apart returned web 200 with all six component launch counts unchanged.

## In progress / not proven

- ONE task and ONE delegated agent at a time. Database and worker-diagnosis children finished. Shared `cip_test` remains untouched by this continuation. Inventory navigation is verified live; the entire navigation/importer backlog is not closed.
- Fresh retained clone `cip_ui_migrate_20261122_1df81d9e4dcb` restored naturally at 0063; canonical UP0065 / DOWN0063 / UP0065 and current commands all exited 0, without stamping. Keys, types, cascading FKs, checks, index, app-role grants and zero seed rows passed. Existing counts stayed 1 tenant / 3 users / 5,623 customers / 435 ledger rows / 340 import jobs in all four snapshots.
- All 798 existing relation owners, effective ACLs (including grantors/options) and RLS flags matched. Earlier verifier failures are retained: explicit/default ACL representation was normalized using PostgreSQL defaults and the sequence object code was corrected from uppercase S to documented lowercase s. No real privileges were altered to satisfy the comparison.
- Before Warren's live upgrade, coordinator independently sampled source0063/clone0065 read-only. Retained clone/rehearsal limitations: same-session full cycle execution verification; database-level ACL/settings and cluster-global roles/passwords are not disaster-recovery tested.
- Owned isolated web PID 86740 serves corrected `2d374040` on 127.0.0.1:3107; confirm process identity before stopping it.
- Canonical deploy record `deploy-20261122-145442.json` remains **FAILED at Celery ping**. Read-only diagnosis proved Windows solo was executing ~21.5s listing-poll chunks during the 10s ping; the poll completed 88 listings at 14:56:12. Same-command ping then passed exit0, one node/pong, with no config change/restart. Fresh Redis heartbeat matched worker PID. Script acceptance/readiness alignment is deferred in BACKLOG-245; do not relabel the original run OK.
- Supplemental stability artifacts: `.tmp/coordinator-20261122/web-stability{,-verified}.json`. The first wrapper falsely exited1 because an empty helper collection was wrapped as `[[]]`; raw actual timestamps/codes/counts were independently validated and preserved. This is supplemental evidence, not an edit to the failed canonical record.
- Other legacy redirect handlers retain pre-existing NextURL origin behavior; follow-up origin audit is BACKLOG-266. Inventory verification does not close the whole navigation batch.

## Next

1. Accept the next integrated lane separately: Line-up row/header/reporting behavior on the live application.
2. Verify database-map lane separately; capture MapLibre country/city/mall screenshots for Warren's approval before switching maps.
3. Resume original Discovery, Dashboard and AI-import lanes in dependency order, one at a time.
4. Future deploy-script reliability review: align busy-solo liveness with the existing worker heartbeat, per BACKLOG-245; do not simply relax the ping timeout.

## Blockers requiring Warren

- Current Codex session has no EIF runtime-session record (rechecked Nov22). `C:/AI/eif-lean/tools/session_grant.py` rejects absent state: a session must have made a real hook call. Protected live execution requires an operator-supported route; never fabricate state, self-grant, or use missing hooks as permission.
- This migration/operator prerequisite is fulfilled. Further protected database mutations still require the installed operator route; the operator wrapper must not be rerun against the now-upgraded baseline.
- MapLibre prototype country/city/mall screenshots need Warren's approval before switching maps. Main promotion remains a separate explicit instruction.

## Original queue / continuity

- Line-up fix, database map and MapLibre prototype are now deployed but awaiting their own live acceptance. Discovery S1/S2/S3c/S5 remain separate; S3a is uncommitted with incomplete lint; S4 has failed saved checks; S3b Crawlee finder is pending. Live discovery stays Preview-only; exact evidence only for links.
- Dashboard design remains in `lane-c-20261120`. Warren approved the look, both themes and stock health BELOW sales charts. Expanded replenishment/aged-stock mock-up and product build are pending. Saved light PNG duplicates dark; interactive theme switching works.
- AI-assisted import spec is on `docs/ai-import-spec-20261120`; build/three-customer clone proof pending. Requested read-only library review follows original live lanes.
- Local evidence: `.tmp/coordinator-20261121/` and `.tmp/coordinator-20261122/migration-proof/`; browser results/screenshots under `.worktrees/verify-inventory-20261121/.tmp/coordinator-20261121/inventory-proof-fixed-build-3/`.
- Required `engineering-rules.mdc` is missing; no contents were assumed. Installed controls remain untouched.
- Prior detailed state/decisions are preserved in [CURRENT snapshot](CURRENT-snapshot-20261121-before-coordinator.md); verify relevant current code before resuming an older item.
