# CURRENT state

**Last updated:** 2026-11-22. Live migrations, Inventory and Line-up navigation/interaction verified. Next: database-map acceptance, then MapLibre screenshots for Warren.
**Branch:** `feat/integrate-20261103`. Product content pin `7f2785d4`; confirm actual HEAD with `git rev-parse`.

## Branch and delivery

- Inventory `055bc770`/origin correction `f8bb446f` integrated at `2d374040`. Line-up correction `071be7bb` integrated at `7f2785d4`. Integration and feature branches pushed. No main merge/push.
- Live web: `7f2785d4`, BUILD_ID `LDwtnkNCD92sXjO_YUHSi`. API/worker retain earlier `b3b54f5e` deployment; their source did not change for this fix.
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

## In progress / not proven

- ONE task/ONE delegated agent at a time. Current task: database-map view fixes/acceptance. Candidate `23f47395` locally committed on `fix/db-map-fit-empty-20261122` (two files only), NOT integrated/pushed/deployed. Old lane-E branch preserved.
- Database-map live read-only proof matched142tables/285FKlinks; auth/search/neighbours/relationship selection worked. Focused fit shrank cards to30px (zoom0.08888); zero-match focus produced minimap NaN SVG, clear recovered. Candidate fits actual matches and mounts minimap only with visible nodes. Backend/schema/global positions/Save unchanged. Before2fail/9pass, after11passed, lint/types0; frozen install restored25locked packages, no manifest/lock edit. Separate reviewer11tests/lint/diff0, no source blocker.
- Reviewer custom3108 dev command (temporary tsconfig/dist + hidden server) was rejected BEFOREexecution by automatic approval review: generic CreateProcess "blocked by policy", no detailed reason/EIF code. No config/server created, no retry/alternate launcher by reviewer. Candidate real-browser proof remains pending. Exact command/error is retained in `.tmp/coordinator-20261122/database-map-proof/independent-review/` and session messages; do not assume all launch methods are authorized or infer a reason.
- Sole child `/root/database_map_fix_review` runs FULLSOURCEGATES ONLY on clean detached23f47395 verification tree, with a fresh verified-writable process-local TEMP/TMP. Logs `.tmp/coordinator-20261122/database-map-proof/full-verification/`. Server startup/config generation is not authorized to this child.
- Private Save/readback/user isolation still UNVERIFIED. Read-only clone preflight confirms retained `cip_ui_migrate_20261122_1df81d9e4dcb` at0065, layouts0, active admins1/3 and viewer2. In-process ASGI/real-SQL clone-only API proof plan is under parent review; no fixture DML authorized yet. Such API proof must not be labeled browser Save proof. Source cip/shared cip_test writes remain out of scope.
- Root identity-checked/stopped old isolated3107 PID60852 before the new candidate build; verification tree now23f47395. Earlier3107 PID86740/review3108 processes also stopped. No new isolated listener is claimed.
- Canonical stack deploy `deploy-20261122-145442.json` remains FAILED at busy-solo Celery ping: successful~21.5s listing chunks occupied10s ping window, then88-listing completion. Exact idle ping later exit0 and heartbeat matched PID. Supplemental checks are separate; do not rewrite original run OK. Follow-up: BACKLOG-245.
- Other legacy origins: BACKLOG-266. Earlier failed harness/verifier evidence (locale, padded headers, nested empty stability array, Temp I/O) retained, never relabeled PASS.

## Next

1. Finish/review database-map view fixes and source/browser gates; prove private-layout Save/reload/isolation on the disposable clone before claiming that capability.
2. Capture MapLibre country/city/mall screenshots for Warren's approval before switching maps.
3. Resume Discovery, Dashboard and AI-import in dependency order, one at a time. Requested library review follows original live lanes.
4. Next deploy-script reliability review: existing identity-bound heartbeat for busy solo (BACKLOG-245), rather than a relaxed ping timeout.

## Blockers requiring Warren

- MapLibre screenshot approval and any main promotion are separate explicit decisions.
- Codex session had no EIF runtime-session record on Nov22. Future protected DB mutations need installed operator route; never fabricate state/self-grant/use missing hooks as permission. Completed0064/65 prerequisite is fulfilled; no repeat approval needed.
- Required `engineering-rules.mdc` missing; no contents assumed, installed controls untouched.

## Original queue / continuity

- Discovery S1/S2/S3c/S5 separate; S3a uncommitted/incomplete lint, S4 failed saved checks, S3b Crawlee finder pending. Live Preview-only/exact-evidence links.
- Dashboard in `lane-c-20261120`: approved look/both themes/stock health BELOW sales charts; expanded replenishment/aged-stock mock-up and build pending. Saved light PNG duplicates dark; interactive switching works.
- AI-import spec `docs/ai-import-spec-20261120`; build/three-customer clone proof pending.
- Evidence `.tmp/coordinator-20261121/`, `.tmp/coordinator-20261122/lineup-proof/`, operator/clone folders above. Older decisions: [CURRENT snapshot](CURRENT-snapshot-20261121-before-coordinator.md); verify current code before resuming.
