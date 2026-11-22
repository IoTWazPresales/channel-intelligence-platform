# CURRENT state

**Last updated:** 2026-11-22. Live migrations, Inventory, Line-up and database-map acceptance verified. Next: MapLibre screenshots for Warren.
**Branch:** `feat/integrate-20261103`. Product content pin `c685bf63`; confirm actual HEAD with `git rev-parse`.

## Branch and delivery

- Inventory `055bc770`/origin correction `f8bb446f` integrated at `2d374040`. Line-up correction `071be7bb` integrated at `7f2785d4`. Database-map corrections `23f47395`/`567f8bfa` integrated at `c685bf63`. Integration and feature branches pushed. No main merge/push.
- Live web: `c685bf63`, BUILD_ID `CbNqqIUC9jWVb7H6po90e`. API/worker retain earlier `b3b54f5e` deployment; their source did not change for this fix.
- Source/applied Alembic: `20261120_0065`. Existing untracked `.agents/`, `.eif/upgrade-history/`, `.eif/upgrade-work/`, `apps/api/.env.bak-20261117` preserved and unstaged.

## Database and environment

- Local Windows Mode B: API8001, web3000, native PostgreSQL/Redis. No Docker. Shared `cip_test` untouched by this continuation.
- Warren executed approved operator wrapper: natural0063 ->0064 ->0065 and current exited0. Coordinator separately sampled cip127.0.0.1:5432 as postgres READ ONLY: both tables present, schema/grants match rehearsal, all798 existing relation metadata entries and representative counts unchanged. Both new tables were empty at that check.
- Fresh operator backup `cip_20261122_144208.dump`:3,355,093,451bytes, SHA256 `bcff1ef7b4f06362e5619cd4900d0d0a6138b9a408e67c9f49ed1f051c3be985`, independently rehashed. Actual backup/list/upgrade/current/read-only proof: `.tmp/operator-ui-migration-20261122T124159Z-b48d2c53/`.
- Retained clone `cip_ui_migrate_20261122_1df81d9e4dcb`: real owner backup/restore, natural UP0065/DOWN0063/UP0065 all0 without stamping; schema/grants/owners/effective ACL/RLS/counts preserved. Proof `.tmp/coordinator-20261122/migration-proof/`. Same-session full cycle plus coordinator read-only sample, not cluster-wide disaster recovery.
- Coordinator did not execute protected migration. Service restarts/sign-in use normal application flows. Do not rerun operator migration wrapper against upgraded baseline.

## What is working / evidence

- **Inventory live:** canonical cover at `/inventory`, manual stock retained at `/inventory/hand-entered`; six live browser checks passed, including three filter-preserving legacy redirects/four same-origin hops and Movement route/tab. No page errors/business-write attempts. Movement dataset acceptance is outside those route checks.
- **Line-up live:**177 reporting plan items/six customer-period groups; header29cases/1460reporting lines excludes1235 non-reporting active commercial lines. Eight aligned columns/18visible actions; expanded detail renders PM-derived BU/workbench link; Close restores summary grain.
- **Open/Close corrected:** native grid row event and React button event previously toggled twice. Panel now excludes button/link/role-button native row events, following existing repository pattern. Only panel/test changed; shared grid/API/approval payloads/writers/layout untouched. Failed-before9/pass11; focused44 passed, separate reviewer20 passed/no blocker.
- Clean071be7bb source gates: lint0errors/48baseline warnings, nonincremental types0, production build0/84pages; full unfiltered web retry290files/1814tests exit0. Initial full run failed289files/1798tests on unhandled Vitest Windows-profile Temp-cache write; original log/exit retained. Verified-writable process-local TEMP/TMP retry required no product/config/error-suppression change; transient cause is not claimed fixed.
- Candidate production3107 and live3000 each passed five acceptance records plus ten real mouse/button-Enter/button-Space/plain-cell-keyboard Open/Close checks, no page errors/business-write attempts. Approval/edit/import writes deliberately untested; current plan dataset lacks non-reporting plan rows for a visual negative fixture.
- Web-only release used existing pnpm build/supervisor component restart. Web launches4->5; other launches unchanged. Two samples60.297s apart: web200/API readiness200, all six components healthy/counts unchanged. Proof `.tmp/coordinator-20261122/lineup-proof/live-verification.json`.

## Database-map acceptance / limits

- **Verified live:** canonical public catalog142tables/285FKlinks; normal sign-in/admin access, matching-card fit340px/zoom1, focused empty/clear restoration, three repeated empty/focus-toggle/restore cycles with all142positions preserved, exact FK mouse selection. Separate verifier independently executed all seven live checks on3000/c685, actualexit0; zero authenticated console/page errors/blocked writes. Four intentional pre-login401 errors retained. No live Save/drag/reset performed.
- Root cause confirmed in installed ReactFlow12.8.5: controlled props reach the store in a passive effect; minimap bounds filter hidden internal nodes. Private wrapper now gates from that same store through public useNodes. No graph remount, layout algorithm, backend/schema or writer change. Real-renderer regression caught eight invalid SVG attributes before; after12focused tests pass. Separate review independently12pass/no blocker.
- Clean567 source gates all0: lint0errors/48baseline warnings, nonincremental types0, build84pages, unfiltered291files/1818tests (623.31s), no retry/filter/config/suppression change. Private process TEMP/TMP write/read probe0. Source tree clean; integration product tree compared identical before release.
- **Browser persistence verified on retained clone with limitations:** actual production UI drag/expand/Save/reload, second-user separate Save, cross-tenant empty preference, return-to-first-user restoration; five records/all17core responses200/no browser errors. Actual normal cip-role app/auth/storage via ASGI IPC; four unrelated shell readers stubbed, fixture bearer tokens injected into ephemeral storage. Does not test Save through the Next HTTP proxy, password-login/logout or retained-client account switching; normal live sign-in/catalog/rendering are separately proved.
- Both committed clone layouts matched browser values before cleanup. Exact tenant1/app_user3/auth_session135/layout0 counts/full-row digests restored, source preferences READ ONLY/unchanged. Separate verifier independently re-executed read-only preflight and compared exact digests. Earlier real API owner/upsert/forged-header/body-field proof also passed. Shared cip_test untouched.
- Web-only canonical build/component restart0: web launches5->6, others unchanged. Two native read-only samples82.349s apart: web/API200, all six component states healthy, counts/build unchanged. Candidate3107PID38448 stopped after exact ownership checks; no candidate listener retained. Primary API/worker unchanged.
- Failures remain retained: original23f browser failed twice (Warren explicitly authorized correction), clone-browser run1 failed on invalid expanded-card width assertion (reviewed harness-only correction, run2passed), first stability collector called an unexported helper before any health query (fresh native collector passed). No failed artifact relabeled PASS. Rejected custom3108 launcher was never used; standard foreground production entrypoint was allowed. No policy/hook changes.
- Full evidence: `.tmp/coordinator-20261122/database-map-proof/lifecycle-correction/verification-report.md`, `full-verification/verification-report.md`, `live-browser-verification.md`, `web-release.json`, `live-web-stability.json`, `browser-persistence-run-2.json`.
- Canonical earlier stack deploy `deploy-20261122-145442.json` remains FAILED at busy-solo Celery ping; later idle ping and heartbeat were separate proof. BACKLOG-245 retains the canonical heartbeat follow-up. Other alias origins: BACKLOG-266. Earlier harness/Temp failures retained separately.

## Next

1. Capture MapLibre country/city/mall screenshots for Warren's approval before switching maps. ONE task/ONE delegated agent at a time.
2. Resume Discovery, Dashboard and AI-import in dependency order, one at a time. Requested library review follows original live lanes.
3. Next deploy-script reliability review: existing identity-bound heartbeat for busy solo (BACKLOG-245), rather than a relaxed ping timeout.

## Blockers requiring Warren

- MapLibre screenshot approval and any main promotion are separate explicit decisions.
- Codex session had no EIF runtime-session record on Nov22. Future protected DB mutations need installed operator route; never fabricate state/self-grant/use missing hooks as permission. Completed0064/65 prerequisite is fulfilled; no repeat approval needed.
- Required `engineering-rules.mdc` missing; no contents assumed, installed controls untouched.

## Original queue / continuity

- Discovery S1/S2/S3c/S5 separate; S3a uncommitted/incomplete lint, S4 failed saved checks, S3b Crawlee finder pending. Live Preview-only/exact-evidence links.
- Dashboard in `lane-c-20261120`: approved look/both themes/stock health BELOW sales charts; expanded replenishment/aged-stock mock-up and build pending. Saved light PNG duplicates dark; interactive switching works.
- AI-import spec `docs/ai-import-spec-20261120`; build/three-customer clone proof pending.
- Evidence `.tmp/coordinator-20261121/`, `.tmp/coordinator-20261122/lineup-proof/`, operator/clone folders above. Older decisions: [CURRENT snapshot](CURRENT-snapshot-20261121-before-coordinator.md); verify current code before resuming.
