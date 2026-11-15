# Wave 1 inventory — gathered on this PC 2026-11-15

Read-only inventory of this PC's CIP checkout. Nothing was deleted: no branch, worktree, or stash. No `cip` write. No merge of any `fix/w1d-*` branch. Wave 1 was not started.

**How this was gathered.** `git fetch origin` in `C:\Users\warren_eliason\channel-intelligence-platform`. Unmerged means the tip is not an ancestor of `origin/feat/integrate-20261103` (`e301126c`, "docs: close BACKLOG-232"). `origin/main` is `46368f6c` and **is** an ancestor of that trunk, so a tip missing from the trunk is also missing from `main`. Local and `origin/` names that share a SHA are one row. Patch check: `git cherry origin/feat/integrate-20261103 <branch>` (`+` = patch not on the trunk, `-` = patch-equivalent). `stash@{0}` was read with `git stash show -p` (empty) and then its third parent, because that command does not show untracked files.

**Marks.** **superseded** = do not rebuild or merge; the work is on the trunk, rejected, or replaced by a named branch. **still needed** = not on the trunk and not rejected. **data or control-plane** = not product work; do not use it as an upgrade source and do not delete it.

---

## Still needed

Do not merge these in the inventory commit. The four `fix/w1d-*` branches are the W1-D fixes. Several worktrees have uncommitted edits; they were left as found (other helpers may own them).

| Ref | SHA | Why it is still needed |
|---|---|---|
| `fix/w1d-gap-scan-sql-20261113` and `origin/` same | `3f11c469` | Catalogue-gap scan rewritten as SQL. Not the 2026-07-12 channel-ops branch. Worktrees `.worktrees/w1d-gap-scan`, `.worktrees/review-fix-w1d-gap-scan-sql-20261113`, `.worktrees/bc82e0-gap-scan` are detached or on this SHA and had no tracked dirt. |
| `fix/w1d-listing-poll-20261113` and `origin/` same | `3b64c6df` | Sites with no reader, plus a reader-restore script. `.worktrees/w1d-listing-poll` had tracked dirt: `listing_capture/autoconfig.py`, `registry.py`, `site_pause.py`, `test_listing_capture_n0101_polling.py`, `test_listing_site_autoconfig.py`. Review and `bc82e0-listing-poll` checkouts of the same SHA were clean. |
| `fix/w1d-no-hardcoded-customers-20261113` and `origin/` same | `4c6764d5` | CST bootstrap and article-alias import without fixed customer ids. `.worktrees/w1d-hardcode` had tracked dirt: `endpoints/mappings.py`, `cst_article_alias_import.py`, `merge_redirect.py`, `test_cst_article_alias_import.py`. The review worktree of this SHA was clean. |
| `fix/w1d-rls-budget-ledger-20261113` and `origin/` same | `37e4db5c` | Migration `20261113_0062` for `budget_ledger_entry` row security. Not applied. `.worktrees/w1d-rls-budget` and the review worktree were clean. |
| `feat/steward-queue-depth` and `origin/` same | `7348f0f6` | `git cherry` `+2`. No `steward_queue_depth` symbol under `apps/` on the trunk. The report is absent. Not a Wave 1 unit. |
| `feat/cst-alias-bulk-actions` and `origin/` same | `bf2afd49` | `git cherry` `+28`. BACKLOG-080 is still **Parked** (batch confirm/reject). D-021 extracted it out of the killed ops-grid stack. |
| `feat/ci-live-e2e` and `origin/` same | `f7fe99d8` | `git cherry` `+1`. BACKLOG-099 is **Deferred** by Warren (2026-10-15, N-0096). |
| `origin/wip/rescue-20261112-files-lane-p1` (origin only) | `9d3a6c85` | PI cutover files not on the trunk: `docs/PI_DATA_MOVE_RUNBOOK.md`, `apps/api/tests/test_pi_hosting_stack.py`, `apps/api/.dockerignore`, `apps/web/Dockerfile`, `docs/memory/CURRENT.md`. The same uncommitted files are still in `.worktrees/lane-p1` (branch tip `a3d0a9cd` is on the trunk). |
| `cursor/docs-current-backlog-225-0bd5` (PR #89) | `9fbe7f52` at inventory start | Docs PR this file is added on. Its pin of trunk `efe3643a` and "D-0143 still open / BACKLOG-232 do not use helpers" is stale: the trunk is `e301126c`, D-0143 is decided, BACKLOG-232 is closed. This commit keeps the trunk text and adds the upgrade-source paragraph. |

Uncommitted product edits whose **branch tip is already on the trunk** (so the branch is superseded, the dirt is not):

| Worktree | Branch tip | Tracked dirt left in place |
|---|---|---|
| `.worktrees/e-n0108` | `fix/e-n0108-cover-latest-20261113` @ `267ee883` (on trunk) | `apps/api/app/services/woc_observation_read.py` |
| `.worktrees/e-n0110` | `fix/e-n0110-stock-gap-20261113` @ `267ee883` (on trunk) | `cst_steward.py`, `customer_stock_gap.py`, `customer_stock_gap_cause.py`, `customer_sell_through.py`, `customer_sell_through_apply.py`, three stock-gap tests, `CstStockGapSection.tsx` and its test |

---

## Superseded

Patch-equivalent to the trunk (`git cherry` all `-`, zero `+`), or a later trunk file already contains the feature, or D-021 says do not take the branch.

| Ref | SHA | Evidence |
|---|---|---|
| `fix/b215-test-isolation`, `fix/b216-rls-nonsuperuser`, `fix/customer-fk-count-savepoint-2`, `fix/drop-uq-source-definition-code`, `fix/dsi-resolution-cache-tid`, `fix/grant-cip-role-four-tables-2`, `fix/test-cleanup-20261105` and their `origin/` twins | see `git cherry` | each `+0`. The 2026-11-05 test and grant fixes are on the trunk under other SHAs. |
| `cursor/backlog-210-215-216-done-30b6` | `fcbfe370` | `+0`. `origin/cursor/backlog-210-215-216-done-30b6` is the extra merge commit `98c98cb9` (not an ancestor). Docs-only "mark done" merge; do not merge it again. |
| `cursor/fix-shipment-sheet-memory-tenant-2f77`, `cursor/pricing-page-padding-e640` and `origin/` twins | `a5cf88d5`, `ae1b4b44` | each `+0`. |
| `origin/cursor/m5c-tenant-filter-55de` | `9559c60d` | `+0`. Tenant mapping is on the trunk (`20261103_0055`). |
| `feat/n0100-part-a` and `origin/` | `f865b32c` | `+0`. |
| `feat/n0118-cst-apply-c57a`, `wip/rescue-20261112-n0118-cst-apply-c57a` and `origin/` | `9c80b3ed` | `+0` `-2`. The chain-key re-apply is on the trunk (truth-audit F1: the cited `06ababdf` was rewritten; the patch matches). |
| `origin/wip/rescue-20261112-files-n0118-c57a` | `4e9c4da7` | Same apply files plus `.eif/runtime-events.jsonl` and docs. Product patch is the superseded N-0118 work. The events log is control-plane; do not treat the branch as an upgrade. |
| `wip/backlog-214-c57a` and `origin/` | `f36a27b9` | Cherry `+1` because the rescue commit does not apply as a patch. CURRENT step 5: these idempotent migrations went in via #82 `a3d0a9cd`. |
| `wip/backlog-214-e5d4` and `origin/` | `5b57def9` | Same migrations plus `apps/api/_prove_b214.py`. CURRENT step 5 calls the e5d4 leftover superseded. |
| `origin/wip/rescue-20261112-files-backlog-214-c57a` | `383cdf74` | Those migrations plus `.eif/runtime-events.jsonl`. |
| `origin/wip/rescue-20261112-files-backlog-214-e5d4` | `2697115a` | Those migrations, `_prove_b214*.py`, and `.eif/runtime-events.jsonl`. |
| `origin/wip/rescue-20261112-files-grant-migration` | `d959efc3` | `20261105_0058_grant_cip_four_tables.py` plus two probe scripts. CURRENT records `0058`–`0060` already on `cip`. |
| `feat/listing-site-autoconfigure` and `origin/` | `be56d9cc` | Cherry `+3` (later edits, so the old patches do not apply). Trunk `autoconfig.py` already has `_seller_values` and `_seed_seller`. |
| `origin/wip/rescue-20261112-files-lane-a` | `edfaa6c9` | Earlier `autoconfig.py` plus `test_listing_own_seller_autofill_db.py`. Lane A shipped as #88. `.worktrees/lane-a` still has a dirty `autoconfig.py` on tip `a3d0a9cd`. |
| `origin/wip/rescue-20261112-files-lane-f` | `14d89d49` | Three test files (129 insertions vs trunk). Lane F shipped as #87. `.worktrees/lane-f` still has dirty `test_cpor_customer_soh_check.py` and `PlanVsExecutedView.test.tsx`. |
| `feat/channel-ops-kpi-first-layout` `0a727ee8`, `feat/channel-ops-ag-grid-chrome` `2a0eae69`, `feat/pve-exception-list-parity` `44eb8bd0`, `feat/shipping-layout-rhythm` `4dfc5411`, `feat/channel-ops-kpi-and-gap-scan-perf` `dc614fe5`, and `origin/` twins | 2026-07-12 | D-021 (`docs/STEWARD_ENGINE_DECISIONS.md`) says do not resurrect channel-ops KPI cards (Waves 1–3). BACKLOG-085 is Done. The lost gap-scan perf on `dc614fe5` is replaced by `fix/w1d-gap-scan-sql-20261113`, not by merging this stack. |
| `fix/web-grid-community-stabilization` and `origin/` | `66da6c66` | D-021: **Do not take.** |
| `fix/pm-bulk-upsert-coercion-and-sql-types` and `origin/` | `558d0886` | BACKLOG-086 **Closed — not needed**. |
| `feature/background-tasks-shipment-evidence-pm` and `origin/` | `a8ac66f5` | May 2026 background-task and shipment-mapping branch. Trunk has `services/imports/background_tasks` and the listing endpoints. |
| `cursor/customer-sales-pipeline-2787` and `origin/` | `94008d1e` | May pipeline. Replaced by customer sell-through and listing capture on the trunk. |
| `origin/cursor/dev-env-setup-2787` `faaceb45`, `origin/cursor/setup-dev-environment-ab45` `eb30b23b` | May dev-env | `database_url_sync_migrate` is in trunk `alembic/env.py`. Dashboard and exceptions have been rebuilt since. |
| `cursor/cloud-agent-1779984010444-wxmy7` and `origin/` | `45c16151` | Same era as rescue `stash10`. DSI steward workspace was rebuilt on the trunk. |
| `cursor/cloud-agent-1779897120532-z2oy3` and `origin/` | `5833d3ad` | Same era as rescue `stash11` (scratch scripts). |
| `feat/report-schedules-beat` and `origin/` | `2ae6192e` | BACKLOG-098 **Shipped 2026-08-17**. |
| `origin/docs/stage1-memory-refresh` | `acdd96a2` | Cherry `+2`. Cut from old `main`. PR #89 says do not merge it. Stale `AGENTS.md` / `CURRENT` / `CONTEXT`. |
| `origin/feat/cst-hist-8x4q-game-w27` | `8b408208` | Merge commit of PR #31 ("backlog-068 landed quarter"). One commit not in the trunk ancestry; `git diff-tree` shows no file of its own. The parents' work is already in history. |
| `wip/rescue-20261112-stash0-context-current-pre-rebuild` and `origin/` | `662bb1a3` | 2026-11-05 CONTEXT/CURRENT edits (8 insertions). Later CURRENT commits replace them. |
| `wip/rescue-20261112-stash4-ns1a-promo-planner-doc` and `origin/` | `e056d666` | `PROMO_PLANNER_CAPABILITY.md` wording (17/17). |
| `wip/rescue-20261112-stash5-design-backlog` and `origin/` | `3cd1dbd8` | BACKLOG text on top of the v0.7.0 tree (172 files). The design-backlog delta is docs; the tree is the control-plane upgrade below. |
| `wip/rescue-20261112-stash6-eif-v070-current-md` and `origin/` | `285e47dc` | CURRENT.md on the same v0.7.0 tree. |
| `wip/rescue-20261112-stash7-ops-grid-workflow-bar` and `origin/` | `bcac4b6c` | Ops-grid workflow bar. D-021 killed that stack. |
| `wip/rescue-20261112-stash9-shipment-steward-imports-page` and `origin/` | `d8ce4a5b` | Imports page, 76 lines. Shipment steward performance work landed later on the trunk. |
| `wip/rescue-20261112-stash10-main-dsi-steward-workspace` and `origin/` | `aa80579e` | 9-file DSI steward workspace from May. Rebuilt since. |
| `feat/promote-provisionals-run`, `wip/rescue-20261112-promote-provisionals-run` and `origin/` | `29b5fbff` | Docs stamp only (3 files, 36 insertions) on an older checkpoint. |
| `chore/eif-v0.7.0-host-upgrade`, `docs/design-language-v1`, `wip/rescue-20261112-eif-v070-host-upgrade` and `origin/` of the rescue | `0449e7f1` | 172 files: `.agents` 132, `.eif` 30, `.cursor` 7, plus docs and `CONTEXT.md`. The host is already past this install (CURRENT's guard is `945f6f0b` from `eif-lean`). Do not re-upgrade from this SHA. |

Worktree branch tips that **are** on the trunk (not in `--no-merged`), so the checkout is superseded even when the directory remains:

`feat/backlog-221-competition-wire` (`C:/AI/cip-b221`, `b440905b`), `feat/lane-a-listings-golive`, `cursor/lane-a-listings-7c39` (#88), `feat/lane-b-cpor-cases`, `cursor/lane-b2-cpor-cases-ea30` (#86), `cursor/lane-d-brief-dashboards-3efe` (#85), `feat/lane-f-small-fixes`, `cursor/exvat-soh-inventory-a44b` (#87), `cursor/lane-p1-hosting-hardening-1376` (tip `a3d0a9cd`; the PI files are the still-needed row above), `fix/grant-cip-role-four-tables` (`20b16135`), `perf/n0108-latest-observation`, `docs/queue-step5-backlog214`, `fix/backlog-214-fresh-db`, `docs/w1d-listing-capture-check-20261113` (`d9a3a686`), `cursor/verify-serial-3efe`, detached `52cec5d7`, `267ee883`, `c87847e8` (#80). Tracked trees were clean except where a still-needed or leftover-draft row above names the dirt.

---

## Data or control-plane

Not product lanes. Do not delete. Do not use as an EIF upgrade source. CIP upgrades come only from `C:\AI\eif-lean` through `C:\AI\update-eif-guard.ps1`.

| Ref | SHA | What it holds |
|---|---|---|
| `fix/backlog-225-eif-linux-identity` and `origin/` | `f4f4272b` | Cherry `+1`. Guard, policy, `.eif/runtime/programme`, `.gitattributes`, and two `apps/api/scripts/ops/*backlog_225*` scripts. PR #89 records it as rejected. `.worktrees/backlog-225-eif` has a dirty `apply_backlog_225_eif_decision_b.py`. |
| `wip/folder-rescue-20261112` and `origin/` | `bc683207` | 15 `.eif` files, `.cursor/eif-runtime-policy.json`, `UsersWorkspace.tsx` (4 lines), `docs/BACKLOG.md` (3 lines). Draft control-plane state from the 2026-11-12 trunk switch. |
| `origin/wip/programme-runtime-20261112` | `334879bb` | Commit message is a snapshot of host `.eif/runtime/programme` before an upgrade. Parent is on the trunk; `git diff-tree` shows no file change. |
| `origin/wip/rescue-20261112-files-n0108-cover-speed` | `bdbc39e9` | 33 `apps/api/scripts/ops/n0108_*` probe scripts and `*_out.txt`, plus `.eif/runtime-events.jsonl`. The cover-speed code is on the trunk (`perf/n0108-latest-observation` tip is an ancestor). |
| `origin/wip/rescue-20261112-files-queue-n` | `c7f7887b` | Queue probe scripts (`queue_s6_*`, `queue_s8_backup.py`, `_queue_*.py`) and `before_cip_*.json` row images under `.eif/audit/`. Evidence of the 2026-11-10 serial queue, not a product branch. |
| `origin/wip/rescue-20261112-files-queue-n4` | `4d53d81e` | Two `before_cip_n0118_clone_*.json` files. |
| `origin/wip/rescue-20261112-files-cip-b221` | `af9b00eb` | 26 `.tmp_scan*.py` / `.tmp_slim*.py` scratch scripts. `C:/AI/cip-b221` tracked tree was clean. |
| `wip/rescue-20261112-stash1-ns2-sellthrough-teleport` and `origin/` | `2a990b1f` | 2,238 files: 2,134 under `.eif`, 96 under `apps`, plus `.cursor`. Teleport stash. Control-plane bulk with a small app slice from `feat/ns-2-brief-nav-collapse`. |
| `wip/rescue-20261112-stash2-ns2-merged-leftover-teleport` and `origin/` | `f2aef980` | 312 files: `.agents` 132, `apps` 109, `.eif` 58, plus `.cursor-recovery` and `replay_tmp.py`. |
| `wip/rescue-20261112-stash3-ns2-eif-guard-wip` and `origin/` | `3b02beba` | `eif_guard.py` WIP (1 file, 199/292). Old guard text. The installed guard is the later `eif-lean` install. |
| `wip/rescue-20261112-stash11-main-dsi-phase0-scripts` and `origin/` | `f9b406bd` | Stash commit (3 parents) from May. `git diff-tree` shows no tracked names; truth audit recorded 5 scratch files. Not a product branch. |
| `wip/recover-dirty-tree-before-data-reload` and `origin/` | `d02419b3` | Removes tracked local artifacts (7 files, 33,734 deletions), mostly `.specstory`. |
| `stash@{0}` | `d5de067c` | See below. |

---

## stash@{0}

Command run: `git stash show -p 'stash@{0}'`. Exit 0. **No patch.** The index parent matches the base, so there is no tracked diff for that command to print.

| Parent | SHA | Role |
|---|---|---|
| 1 (base) | `267ee883` | `WIP on feat/integrate-20261103` — N-0102 re-charter. This commit **is** on the trunk. |
| 2 (index) | `f375c599` | `git diff stash@{0}^1 stash@{0}^2` is empty. |
| 3 (untracked) | `6cbb9c49` | 147 files. |

The untracked tree is control-plane and review scrap, not product code:

- `.agents/skills/<specialist>/SKILL.md` and `references/contract.md` (the EIF specialist set)
- `.cursor/rules/eif-core.mdc`, `.cursor/rules/eif-project-adapter.mdc`
- `.eif/runs/RUN-20261113-W1-ORCH/RUN_LOG.ndjson`
- `.eif/upgrade-history/1794514454197024100/journal.json`, `.eif/upgrade-work/journal.json`
- `896539.txt` through `896544.txt`
- `codex-review-85-lane-d.txt`, `codex-review-86-lane-b.txt`, `codex-review-87-lane-f.txt`, `codex-review-88-lane-a.txt`

**Mark: data or control-plane.** Not dropped.

Other stashes were not dropped and were not expanded with `git stash show -p` (only `stash@{0}` was required). They remain `stash@{1}` through `stash@{12}`. Their earlier rescues are the `wip/rescue-20261112-stash*` branches above. `stash@{8}` is still only a stash (the 2026-11-12 truth audit said its untracked tree is a Postgres data directory; it was not re-expanded here and it was not dropped).

---

## Every worktree (2026-11-15)

Tracked dirt is `git status --porcelain --untracked-files=no` unless a row says untracked. No worktree was removed.

| Path | HEAD | Mark |
|---|---|---|
| `C:/Users/warren_eliason/channel-intelligence-platform` | `feat/integrate-20261103` `e301126c` clean | trunk. Not edited by this inventory. |
| `C:/AI/cip-b221` | `feat/backlog-221-competition-wire` `b440905b` clean | superseded tip. Scratch scans are the files-cip-b221 branch (data). |
| `.worktrees/backlog-214-c57a` | `f36a27b9` clean | superseded |
| `.worktrees/backlog-214-e5d4` | `5b57def9` clean | superseded |
| `.worktrees/backlog-225-eif` | `f4f4272b` dirty `apply_backlog_225_eif_decision_b.py` | data or control-plane |
| `.worktrees/bc82e0-gap-scan` | detached `3f11c469` clean | still needed (w1d gap-scan). Another helper. Not touched. |
| `.worktrees/bc82e0-listing-poll` | detached `3b64c6df` clean | still needed (w1d listing-poll). Another helper. Not touched. |
| `.worktrees/e-n0108` | `267ee883` dirty `woc_observation_read.py` | tip superseded; uncommitted edit still needed |
| `.worktrees/e-n0110` | `267ee883` dirty (10 files, listed above) | tip superseded; uncommitted edits still needed |
| `.worktrees/grant-migration` | `fix/grant-cip-role-four-tables` `20b16135` clean | superseded (tip on trunk) |
| `.worktrees/lane-a` | `a3d0a9cd` dirty `autoconfig.py` | superseded draft of #88; snapshot on files-lane-a |
| `.worktrees/lane-a2` | `000e1e1d` clean | superseded (#88) |
| `.worktrees/lane-b` | `a3d0a9cd` clean | superseded |
| `.worktrees/lane-b2` | `7c07e226` clean | superseded (#86) |
| `.worktrees/lane-d` | `cc96e3ed` clean | superseded (#85) |
| `.worktrees/lane-f` | `a3d0a9cd` dirty two test files | superseded draft of #87; snapshot on files-lane-f |
| `.worktrees/lane-f2` | `b1c665b6` clean | superseded (#87) |
| `.worktrees/lane-p1` | `a3d0a9cd` dirty Dockerfile and CURRENT; untracked `.dockerignore`, `test_pi_hosting_stack.py`, `PI_DATA_MOVE_RUNBOOK.md` | tip superseded; those PI files still needed (also on files-lane-p1) |
| `.worktrees/merge-20261111` | detached `52cec5d7` clean | superseded (deploy commit on trunk) |
| `.worktrees/merge-20261113` | detached `267ee883` clean | superseded |
| `.worktrees/n0108-cover-speed` | `230c84b6` clean | superseded. Probe output is files-n0108 (data). |
| `.worktrees/n0118-c57a` | `9c80b3ed` clean | superseded |
| `.worktrees/pr89-amend` | `cursor/docs-current-backlog-225-0bd5` | this inventory's worktree |
| `.worktrees/queue-n` | `24c7bcaf` clean | superseded. Scripts are files-queue-n (data). |
| `.worktrees/queue-n4` | detached `c87847e8` clean | superseded (#80) |
| `.worktrees/queue-n5` | `fix/backlog-214-fresh-db` `6ef8c36f` clean | superseded (#82) |
| `.worktrees/review-fix-w1d-gap-scan-sql-20261113` | detached `3f11c469` clean | still needed |
| `.worktrees/review-fix-w1d-listing-poll-20261113` | detached `3b64c6df` clean | still needed |
| `.worktrees/review-fix-w1d-no-hardcoded-customers-20261113` | detached `4c6764d5` clean | still needed |
| `.worktrees/review-fix-w1d-rls-budget-ledger-20261113` | detached `37e4db5c` clean | still needed |
| `.worktrees/verify-pr60` | detached `9c80b3ed` clean | superseded |
| `.worktrees/verify-serial` | `604b6c2b` clean | superseded (#84) |
| `.worktrees/w1d-gap-scan` | `3f11c469` clean | still needed |
| `.worktrees/w1d-hardcode` | `4c6764d5` dirty (4 files) | still needed |
| `.worktrees/w1d-listing-check` | `d9a3a686` clean | superseded (listing-capture check is on the trunk) |
| `.worktrees/w1d-listing-poll` | `3b64c6df` dirty (5 files) | still needed |
| `.worktrees/w1d-rls-budget` | `37e4db5c` clean | still needed |

---

## EIF checkouts (not CIP branches)

Verified in the two EIF directories on this PC. Neither fact was taken from a CIP doc.

- `C:\AI\eif-lean`: checked out `fix/backlog-225-cross-host` at `4b14e09`. `origin/feat/lean-enforcement-profile` is `56b41d0`. `origin/main` and local `main` are `f03832d`. Neither branch tip is an ancestor of EIF `main` (`git merge-base --is-ancestor` exit 1).
- `C:\AI\engineering-intelligence-framework`: checked out `fix/session-local-retry-policy` at `1061934`, dirty, behind `origin` by 3. `eif-lean` is a linked worktree of this repo (`fix/backlog-225-cross-host` shows that path). This checkout must never be an upgrade source.
- `C:\AI\update-eif-guard.ps1` sets its EIF directory to `C:\AI\eif-lean` and refuses to upgrade without `-ReviewedSha`.
