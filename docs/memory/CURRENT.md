# CURRENT state

**Last updated:** 2026-11-22. Inventory implementation verified with limitations; deployment prerequisite in progress.
**Branch:** `feat/integrate-20261103`. Product content pin `2d374040`; confirm actual HEAD with `git rev-parse`.

## Branch and delivery

- Inventory product `055bc770` and origin correction `f8bb446f` are independently reviewed, integrated (`041f1c65`, then `2d374040`) and pushed to the integration branch. Lane `feat/lane-a1-nav-20261120` is also pushed at `f8bb446f`.
- No main merge/push or live deployment has been performed in this continuation.
- Source Alembic head is `20261120_0065` (tenant settings 0064, private UI layouts 0065).
- Pre-existing untracked `.agents/`, `.eif/upgrade-history/`, `.eif/upgrade-work/`, and `apps/api/.env.bak-20261117` are preserved and unstaged.

## Database and environment

- Local Windows, Mode B: API 8001, live web 3000, local PostgreSQL/Redis. No Docker.
- Fresh direct read-only check on 2026-11-22 returned `cip`, `transaction_read_only=on`, revision `20261118_0063`; `public.tenant_setting` and `public.user_ui_layout` are absent. PostgreSQL 18.3 owner preflight was independently confirmed by the database agent.
- No coordinator/child live DB mutation or primary service restart has occurred. Browser sign-in uses the existing authentication flow.
- Recovered Nov21 backup remains preserved. Fresh Nov22 owner backup completed with exit 0: 3,353,527,730 bytes, SHA256 `c7c14cd993418f78d6acac84667101648e11db45311f3bd50a7b3b104a11f152`; `pg_restore --list` passed. Backup is under `.tmp/coordinator-20261122/migration-proof/`; full clone restore/migration proof is pending.
- Shared `cip_test` is preserved: its earlier proof restamped Discovery revision `20261121_0065` to UI 0064 before applying 0065. That is insufficient for the intended natural 0063 -> UI0065 transition.

## What is working / evidence

- `/inventory` reuses `CoverLensView` inside `StockChrome`; hand-entered stock is retained at `/inventory/hand-entered`, with unchanged APIs, payloads and grid preference keys.
- Legacy cover redirects preserve filters and incoming origin. Actual Next 15.5.15 adapter regressions failed before the fix. Supported normalization option plus native request URL/incoming Host fixed the origin change; forwarded-host/query values do not select destinations.
- Independent final review: no blocker; 52 middleware tests and 6 extra adapter edge checks passed.
- Final clean worktree `2d374040`: lint 0 errors / 48 warnings, 290 web files / 1,805 tests, typecheck, and production build (84 pages), all actual exits 0.
- Nov22 browser proof `inventory-proof-fixed-build-3`: actual exit 0, six checks passed: Inventory cover, three legacy filter-preserving redirects, hand-entered page, and Movement route/selected tab. All four redirect hops retain 127.0.0.1:3107. Login 200, no page errors or blocked business writes.
- Verification limit: isolated web 3107 against the existing API; not live web 3000. Movement data was still loading, so only its route/tab is proven. Earlier failed harness/sign-in/origin evidence remains preserved.

## In progress / not proven

- ONE task and ONE delegated agent at a time. Sole active child `/root/ui_migration_clone` is verifying the existing 0064/0065 migrations using a fresh owner backup and a newly named disposable clone; no product edits, shared-test mutations or live migrations are authorized for that agent.
- Unique target `cip_ui_migrate_20261122_1df81d9e4dcb` was checked nonexistent before creation. Clone restore and natural UP/DOWN/UP verification are in progress; do not claim PASS or restamp to make proof pass.
- Owned isolated web PID 86740 serves corrected `2d374040` on 127.0.0.1:3107; confirm process identity before stopping it.
- Last primary deploy record (Nov21 00:35) failed at Celery ping despite healthy restarts. Worker task acceptance and primary stability remain unproven.
- Other legacy redirect handlers retain pre-existing NextURL origin behavior; follow-up origin audit is BACKLOG-266. Inventory verification does not close the whole navigation batch.

## Next

1. Finish disposable clone migration proof and operator handoff. Use the canonical migration entrypoint with explicit targets and both sync URLs bound to the intended DB.
2. Obtain an operator-supported live execution path, apply approved additive migrations after a fresh backup, then recheck actual identity/revision/tables.
3. Run the supported deployment/readiness sequence and browser-verify Inventory on 3000. Accept each remaining lane separately.
4. Resume the original queued lanes below, one at a time.

## Blockers requiring Warren

- Current Codex session has no EIF runtime-session record (rechecked Nov22). `C:/AI/eif-lean/tools/session_grant.py` rejects absent state: a session must have made a real hook call. Protected live execution requires an operator-supported route; never fabricate state, self-grant, or use missing hooks as permission.
- Operator execution-path question remains pending (operator terminal or an existing guarded/granted session). Elapsed time is not an answer.
- MapLibre prototype country/city/mall screenshots need Warren's approval before switching maps. Main promotion remains a separate explicit instruction.

## Original queue / continuity

- Line-up fix, database map and MapLibre prototype are integrated but awaiting live acceptance. Discovery S1/S2/S3c/S5 remain separate; S3a is uncommitted with incomplete lint; S4 has failed saved checks; S3b Crawlee finder is pending. Live discovery stays Preview-only; exact evidence only for links.
- Dashboard design remains in `lane-c-20261120`. Warren approved the look, both themes and stock health BELOW sales charts. Expanded replenishment/aged-stock mock-up and product build are pending. Saved light PNG duplicates dark; interactive theme switching works.
- AI-assisted import spec is on `docs/ai-import-spec-20261120`; build/three-customer clone proof pending. Requested read-only library review follows original live lanes.
- Local evidence: `.tmp/coordinator-20261121/` and `.tmp/coordinator-20261122/migration-proof/`; browser results/screenshots under `.worktrees/verify-inventory-20261121/.tmp/coordinator-20261121/inventory-proof-fixed-build-3/`.
- Required `engineering-rules.mdc` is missing; no contents were assumed. Installed controls remain untouched.
- Prior detailed state/decisions are preserved in [CURRENT snapshot](CURRENT-snapshot-20261121-before-coordinator.md); verify relevant current code before resuming an older item.
