# Coordinator handoff ? 2026-11-23

**Read [CURRENT](../../memory/CURRENT.md) first for subsequent changes. This is a point-in-time recovery pack.**

## Start here

Repository: `C:/Users/warren_eliason/channel-intelligence-platform`; remote `https://github.com/IoTWazPresales/channel-intelligence-platform.git`; integration branch `feat/integrate-20261103`. Pre-consolidation HEAD6c228052. Product web pin c685bf63 / BUILD_ID CbNqqIUC9jWVb7H6po90e; API/worker last deployed b3b54f5e. Last actual live acceptance was22November; documentation consolidation is23November, not a new smoke run.

Read memory palace -> CURRENT -> CONTEXT -> AGENTS and required rules. User asks one task / one delegated agent at a time, careful evidence and no guesses. Latest instruction is to consolidate and preserve context; no product work was started for the latest map feedback. A subsequent `continue` should resume the map revision brief, unless Warren sets another priority.

## Latest user direction

See [MAP_FEEDBACK](MAP_FEEDBACK.md). Country/city/mall markers and theme must match the shipping reference; pins/proposed pins belong in the right panel. Existing screenshots require revision. Prominent credit strip removal requested; retain attribution through a compliant less intrusive design. Provider decision remains unanswered. Do not interpret old pending approval questions as approval.

**Targets answer:** [TARGETS_STATUS](TARGETS_STATUS.md). Requested new Targets/Dashboard V2 is design/prototype only, not implemented/shipped. Draft light/dark styling exists; the discussed redesign has not been rolled out. Prior accepted Dashboard direction and stock-below-sales placement remain binding; expanded replenishment/aged-stock detail is unfinished.

## Delivery and evidence

| Work | Actual completion level |
|---|---|
| Migration0063 ->0064 ->0065 | Warren executed; independent read-only schema/grants/count/backup checks passed. Do not rerun migration wrapper. |
| Inventory | Integrated2d374040; six live route/redirect checks. Movement dataset acceptance remains outside those route checks. |
| Line-up | Integrated7f2785d4; native double-toggle corrected, live acceptance and ten mouse/keyboard gestures passed. Approval/import/edit writes not exercised. |
| Database-map | Integratedc685bf63 from567f8bfa; seven independently executed live checks passed. Full clean gates:291files/1818tests,lint/types/build0. Personal layout Save/reload/isolation proved on disposable clone with explicit ASGI IPC/shell-stub/session-fixture limits; exact cleanup separately rechecked READ ONLY. |
| MapLibre store map | Prototype code exists but defaultoff, provider settings empty. Three useful browser-only preview images captured; latest look requires revision. No rollout/settings/pin write. |
| Discovery V2 | S1/S2/S3c/S5 committed separately, not integrated; S3a/S4 dirty work preserved. S3b Crawlee finder pending. Old recorded64tests are not a fresh acceptance result; S3a lint incomplete and S4 saved checks failed. |
| Dashboard / Targets | Preserved design spec/two HTML prototypes, not a product implementation. |
| AI-assisted imports | Spec `docs/specs/AI_ASSISTED_IMPORT.md` on branch4c386d8a; implementation and three-customer clone proof pending. AI proposes, steward confirms deterministic rules. |
| Library review | Requested after original live lanes; read-only review still pending. |

[Verification summaries](evidence/) preserve outcomes and limits. Original raw logs/harnesses are local under `.tmp/coordinator-20261121` and `.tmp/coordinator-20261122`; they are not in Git and are not transferred as secrets-bearing raw history. Copied reports retain original local paths; those paths refer to evidence on Warren's PC. The summary is not a substitute for raw evidence if a later material claim requires rechecking.

## Active worktrees / recovery manifest

Git ancestry is not feature/UI acceptance. These values were re-executed during consolidation:

| Local worktree suffix | Branch | Base / tip | State |
|---|---|---|---|
| disc-s1-20261120 | `feat/discovery-s1-20261120` | `6fc12b3b` | Not integrated; clean |
| disc-s2-20261120 | `feat/discovery-s2-20261120` | `dac2a1bb` | Not integrated; clean |
| disc-s3-20261120 | `feat/discovery-s3-20261120` | `dac2a1bb` | Not integrated; dirty snapshot preserved |
| disc-s3c-20261120 | `feat/discovery-s3c-20261120` | `bf2f721b` | Not integrated; clean |
| disc-s4-20261120 | `feat/discovery-s4-20261120` | `dac2a1bb` | Not integrated; dirty snapshot preserved |
| disc-s5-20261120 | `feat/discovery-s5-20261120` | `a907be60` | Not integrated; clean |
| lane-c-20261120 | `docs/dashboard-v2-design-20261120` | `b4039a1d` | Ancestor of integration; dirty snapshot preserved |
| spec-ai-import-20261120 | `docs/ai-import-spec-20261120` | `4c386d8a` | Not integrated; clean |
| lane-a2-20261120 | `feat/lane-a2-prices-20261120` | `033b98b4` | Ancestor of integration; clean |
| lane-f-20261120 | `feat/lane-f-map-20261120` | `5c889c5c` | Ancestor of integration; clean |

Full paths and dirty file lists: [workstreams.json](workstreams.json). Do not modify/clean the original worktrees during recovery. The old Claude coordinator was6804f503-0421-4eeb-8a46-4297a5561121; its logs were orientation evidence, not current state. No Claude/Cursor usage is assumed available. Some delegated agents hit usage limits; no background child task remains required.

## Portable recovery on another agent / machine

1. Fetch/pull the latest `origin/feat/integrate-20261103`; do not switch to or promote main. The ordinary docs, draft HTML and screenshots are now in that branch.
2. [recovery/workstreams.bundle](recovery/workstreams.bundle) preserves the seven separate Discovery/AI-spec branch refs and their commits relative to the integration history. Fetch the integration branch first to obtain bundle prerequisites. `git bundle verify docs/handoffs/2026-11-23/recovery/workstreams.bundle` must pass. `git bundle list-heads` names the refs.
3. If needed, import refs without overwriting working branches: `git fetch docs/handoffs/2026-11-23/recovery/workstreams.bundle 'refs/heads/*:refs/remotes/handoff/*'`. Then inspect a specific recovered ref in a new worktree.
4. [recovery/uncommitted-workstreams.zip](recovery/uncommitted-workstreams.zip) preserves S3a/S4 tracked patches and untracked source/tests plus the original Dashboard draft files. [Manifest](recovery/manifest.json) records exact base commits, entries and SHA256 hashes. Extract to a separate recovery directory, inspect, create a clean worktree at the recorded base, check/apply its tracked patch there, then restore that snapshot's untracked files. Never blindly apply to integration or an existing dirty worktree.
5. Both Discovery patches were checked against disposable indexes at their recorded base. Archive entries/hash integrity and Git bundle verification passed. This proves recovery integrity, not implementation correctness. No unreviewed product code was promoted by this consolidation.

Original Dashboard files are additionally preserved byte-for-byte at `docs/design/dashboard-v2/{index,targets-builder}.html` and `docs/specs/DASHBOARD_V2.md`. A readme labels them design-only and keeps their original provenance.

No `.env`, credentials, database dump, log, node_modules, venv, installed hook/policy or raw chat history is included. Provision credentials separately through the operator's approved mechanism. Do not copy another session's grants.

## Database/runtime boundaries ? do not rediscover or bypass

- Windows local Mode B; no Docker. Web3000/API8001/Postgres5432 databasecip/Redis6379. Python API venv3.12; system Python3.14 is only suitable for non-API documentation tooling.
- Applied/source UI migration20261120_0065 last verified22November. Sharedcip_test was not touched by this continuation. A historical Claude stamp on sharedcip_test is not natural migration proof.
- Retained disposable clone: `cip_ui_migrate_20261122_1df81d9e4dcb`. Real backup/restore and natural0063->0065->0063->0065 passed without stamps. Personal layout fixtures restored exactly:tenant1/app_user3/auth_session135/layout0 at last proof.
- Operator backup `cip_20261122_144208.dump`,3355093451bytes, SHA256bcff1ef7b4f06362e5619cd4900d0d0a6138b9a408e67c9f49ed1f051c3be985. Local folder `.tmp/operator-ui-migration-20261122T124159Z-b48d2c53/`; it is deliberately not in this pack.
- Coordinator observed no registered EIF session on22November. Future protected live DB mutations require a supported operator route; never fabricate session state, self-grant or borrow Claude credentials. No ALLOW_TESTS_ON_DEV_DB was set.
- Cloud first-call guard rules still apply. Stop on identity/integrity/policy denials; never edit hooks, policy, .claude or CLAUDE.md. Required engineering-rules.mdc was missing and remains unmodified.
- A bundled hidden custom3108dev launcher was automatically rejected with generic blocked-by-policy before execution; do not replay it. Standard foreground Next production entrypoint was allowed. Candidate3107servers were ownership-checked and stopped; stale PIDs in reports are historical, not kill targets.
- Native Windows solo Celery can be busy beyond inspect-ping timeout. Canonical stack deploy22November FAILED at ping and remains FAILED; later idle ping/heartbeat/stability are separate evidence. BACKLOG-245 is the existing follow-up; read DEV_TOPOLOGY before worker/queue changes.

## Gates and next work

No full product test rerun was needed for this docs/archive-only consolidation. Last product gates at567f8bfa are recorded above; integration product tree compared identical before release. Existing flat ESLint config was used with process-local ESLINT_USE_FLAT_CONFIG=true; do not silently replace tooling or edit project rules. Preserve original failure logs and the two-attempt stop rule.

Next: map revision (BACKLOG-268), then the original Discovery -> Dashboard/Targets (BACKLOG-269) -> AI import -> library-review sequence, unless Warren reprioritizes. BACKLOG-267 location ambiguity must be reviewed before bulk confirmation; BACKLOG-266 covers other legacy redirect origins. No main promotion authorized.
