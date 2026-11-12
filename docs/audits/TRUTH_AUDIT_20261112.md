# Truth audit — 2026-11-12

Read-only audit of CIP. No product edits, no `cip` writes, no merges, no deletes. Writes made: 14 pushed `wip/rescue-20261112-*` branches and this file.

- Trunk audited: `origin/feat/integrate-20261103` @ `70338bd4`. VERIFIED
- `cip` probes ran with `current_database()` = `cip`, user `cip`, `default_transaction_read_only` = `on`, SELECT only, script piped on stdin (no file written). VERIFIED
- Every line below is labelled **VERIFIED** (checked in this session against git, trunk code or `cip`) or **ASSERTED** (taken from a document or inferred, not re-executed).

---

## 1. LOST items

Real work absent from the trunk, with no BACKLOG or decision covering it.

- **L1 — catalogue-gap scan performance fix.** Commit `d87eff35` ("Channel Ops KPI summary + product-master-gaps scan perf"), carried on all six 2026-07-12 UI branches (first on `origin/feat/channel-ops-kpi-and-gap-scan-perf`). It rewrote `scan_open_gaps_for_matches` to read distinct unresolved tokens per column with SQL `DISTINCT`, bounded by `limit`, match-only (its comment cites a ~318 s HeadersTimeout). About 106 changed lines in one file. VERIFIED
  - Trunk `apps/api/app/services/imports/product_master_gap_resolve.py:451-490` still loads every unresolved shipment row through `_unresolved_shipment_rows` (`load_evidence_rows`) and loops in Python. VERIFIED
  - The other half of the commit (proxy undici `headersTimeout`) is superseded: trunk `apps/web/src/app/api/v1/[[...path]]/route.ts:58-81`. VERIFIED
  - D-021 (`docs/STEWARD_ENGINE_DECISIONS.md`) lists the extract and do-not-resurrect items for this lineage and does not mention this fix. VERIFIED
  - Whether the trunk scan is still slow on `cip` today was not timed. ASSERTED
- **L2 — steward and CPOR queue-depth report.** `origin/feat/steward-queue-depth` (`df1e4fac`): `apps/api/scripts/ops/steward_queue_depth.py`, 617 lines, a read-only report of steward and CPOR queue depth on `cip` (plus a 16-line wrapper at `scripts/ops/`). No file, BACKLOG entry or equivalent exists on the trunk (searched `queue_depth`, `queue depth`). VERIFIED. Its imports may no longer resolve on the trunk. ASSERTED
- **L3 — PC-only work NOT rescued (guard denial, at risk until saved).** The temporary-index commit for dirty worktrees was denied twice: `SECRET_STAGE: cannot show git add publishes no secret file (RuntimeError); fail closed`. Per instruction it was stopped, not routed around. VERIFIED. What exists only on this PC:
  - `.worktrees/lane-p1` (`cursor/lane-p1-hosting-hardening-1376`, nothing pushed beyond `a3d0a9cd`): `docs/PI_DATA_MOVE_RUNBOOK.md` (115 lines, the cutover procedure for moving `cip` onto the hosted Docker stack), `apps/api/tests/test_pi_hosting_stack.py` (36 lines), `apps/api/.dockerignore` (23 lines), `apps/web/Dockerfile` (+3/−1), `docs/memory/CURRENT.md` (+2). None of it is on the trunk or any origin branch, and no BACKLOG entry was found for it. VERIFIED
  - `.worktrees/lane-a` (`feat/lane-a-listings-golive`): `autoconfig.py` +115/−16 and `apps/api/tests/test_listing_own_seller_autofill_db.py` (271 lines, not on the trunk). VERIFIED. Likely an earlier draft of what shipped as #88 from `lane-a2`. ASSERTED
  - `.worktrees/lane-f`: three test files, +81 lines, all differing from the trunk. VERIFIED. Likely an earlier draft of #87. ASSERTED
  - `.worktrees/n0108-cover-speed`: 33 `n0108_*` probe scripts and their `_out.txt` outputs. `.worktrees/queue-n`: 15 queue scripts (`queue_s6_backup.py`, `queue_s6_clone.py`, `queue_s8_backup.py`, …) and four `before_cip_*` JSON row images from 2026-11-10. `.worktrees/queue-n4`: two `before_cip_n0118_clone_*` JSON. `C:/AI/cip-b221`: 26 `.tmp_scan*.py`. `.worktrees/backlog-214-e5d4`: four `_prove_b214_*.py`. VERIFIED
  - Main checkout: `896539-896544.txt` (background-task logs), four `codex-review-8[5-8]-lane-*.txt` (UTF-16 Codex review transcripts, ~1.5 MB each), the `counts.md` edit, `.agents/` (EIF installer output). VERIFIED
  - Needed to save these: an operator grant for the temporary-index `git add`, or Warren running the commits. ASSERTED

## 2. FALSE claims

No "done", "applied", "closed", "merged" or "verified" claim checked in this window turned out false in substance. These pointers or statuses are false:

- **F1** — `CONTEXT.md` changelog 2026-11-06 "N-0118 chain-key re-apply … Commit `06ababdf`". `06ababdf` is not on origin; it existed only in local `feat/n0118-cst-apply-c57a` (now rescued). The same patch is on the trunk as `b6c60970`, via #60 (`46c98213`). The cited hash is a pre-rebase pointer; the work itself landed. VERIFIED
- **F2** — `docs/BACKLOG.md` BACKLOG-081 status "Confirmed open (2026-09-21 N-0030 audit: `alias_seal` absent from tree)". The seal is on the trunk: `apps/api/app/services/customer_merge_alias_seal.py`, called from `apps/api/app/services/customer_full_merge.py:324-347` (landed 2026-10-15 in `694b46b8`, N-0095). The status was never updated. VERIFIED. BACKLOG-083 ("Parked") is in the same state: `customer_related_master_groups.py` and `RelatedNameGroupsSection.tsx` are on the trunk. VERIFIED. Whether every BACKLOG-083 companion (redirect, repair scripts) landed was not checked. ASSERTED
- **F3** — `apps/api/alembic/versions/20261105_0060_drop_uq_source_definition_code.py` docstring: "NOT applied. This revision is authored only; it has not been run against any database." On `cip`, alembic is `20261110_0061`, `uq_source_definition_tenant_code (tenant_id, code)` exists, and no global unique on `code` remains. VERIFIED

## 3. Wrong in `cip`

Every `cip` write claimed in the window matches the database (section 4). Open conditions found:

- `budget_ledger_entry` has row security off (`relrowsecurity = false`). CURRENT step 5 already lists it "for Warren". VERIFIED
- Compuspeed `1152` and Syntech `4145` are unmerged (`unverified`, `merged_into_customer_id` null) but own no foreign keys. Their historical customer rows stay on OPEN_CHANNEL because the 2026-08-08 absorb kept no repoint list. VERIFIED (status), ASSERTED (history, from CURRENT step 8)
- `listing_site_seller` has 0 rows, so the seller names the listing seed needs are still missing. VERIFIED
- 630 `TMP-CUST%` customers are not merged. VERIFIED. This matches CURRENT step 8 (628 + 2). VERIFIED
- Runtime, not `cip` data: at 23:30 SAST, after the PC shutdown, nothing listens on 8000 (API) or 6379 (Redis); Postgres 5432 is up and web 3000 answers 307. The API and worker need restarting. VERIFIED

## 4. Everything else

### 4.1 Rescue (step 1)

| Source | Rescue branch (pushed) | Content | |
|---|---|---|---|
| stash@{0} | `wip/rescue-20261112-stash0-context-current-pre-rebuild` | CONTEXT/CURRENT edits, 2026-11-05 | VERIFIED |
| stash@{1} | `wip/rescue-20261112-stash1-ns2-sellthrough-teleport` | SellThrough* UI, BusinessCalendarPanel, `.eif/audit` (2,238 files) | VERIFIED |
| stash@{2} | `wip/rescue-20261112-stash2-ns2-merged-leftover-teleport` | merged-leftover tests, audit files (312 files) | VERIFIED |
| stash@{3} | `wip/rescue-20261112-stash3-ns2-eif-guard-wip` | `eif_guard.py` WIP | VERIFIED |
| stash@{4} | `wip/rescue-20261112-stash4-ns1a-promo-planner-doc` | PROMO_PLANNER_CAPABILITY.md | VERIFIED |
| stash@{5} | `wip/rescue-20261112-stash5-design-backlog` | BACKLOG +34 | VERIFIED |
| stash@{6} | `wip/rescue-20261112-stash6-eif-v070-current-md` | CURRENT.md | VERIFIED |
| stash@{7} | `wip/rescue-20261112-stash7-ops-grid-workflow-bar` | dual-agent workflow doc | VERIFIED |
| stash@{9} | `wip/rescue-20261112-stash9-shipment-steward-imports-page` | imports page +76 | VERIFIED |
| stash@{10} | `wip/rescue-20261112-stash10-main-dsi-steward-workspace` | DSI steward workspace (9 files) | VERIFIED |
| stash@{11} | `wip/rescue-20261112-stash11-main-dsi-phase0-scripts` | 5 scratch files | VERIFIED |
| `chore/eif-v0.7.0-host-upgrade` = `docs/design-language-v1` (5 unpushed) | `wip/rescue-20261112-eif-v070-host-upgrade` | EIF v0.7.0 + Phase A/B mint docs | VERIFIED |
| `feat/promote-provisionals-run` (4 unpushed, subset of the above) | `wip/rescue-20261112-promote-provisionals-run` | mint docs | VERIFIED |
| `feat/n0118-cst-apply-c57a` (2 unpushed) | `wip/rescue-20261112-n0118-cst-apply-c57a` | `06ababdf`, `9c80b3ed`; patches already on the trunk | VERIFIED |

- stash@{8} was not pushed: its tracked diff is empty, and its untracked tree is a Postgres data directory (`apps/api/.cip-alembic-smoke-pg`, 1,288 files) plus `celerybeat-schedule.*`. That is data, not work. VERIFIED
- Every stash was scanned for credentials before pushing; the only hits were localhost dev defaults (`cip:cip`), the same strings already on the trunk. VERIFIED
- No stash was dropped and no worktree or branch was removed. VERIFIED
- Worktrees whose only change is the guard event log (`backlog-214-c57a`, `n0118-c57a`) have nothing to rescue. VERIFIED

### 4.2 Unmerged branches (step 2)

150 origin branches checked with `git cherry` against the trunk, then by file content. 22 have patches the trunk lacks. VERIFIED

| Branch | Class | Evidence | |
|---|---|---|---|
| six 2026-07-12 UI branches (stack of 24 shared commits + 1 each) | PARKED / SUPERSEDED by **D-021** (`docs/STEWARD_ENGINE_DECISIONS.md`, killed `ops-master-grid-shell-parity`, same base `618448c`) | the ID BACKLOG-074 was reused (on the trunk it is CST E2) | VERIFIED |
| `channel-ops-kpi-first-layout` (KPI cards above filter bar), Waves 1–3 | SUPERSEDED | D-021 "do not resurrect channel-ops KPI cards (Waves 1–3)"; BACKLOG-079 regression trap | VERIFIED |
| `cst-alias-bulk-actions` (`bf2afd49`, batch confirm/reject) | PARKED | BACKLOG-080; trunk `cst_steward.py:679,696` has per-alias confirm/reject only | VERIFIED |
| `pve-exception-list-parity` (U4f) | SUPERSEDED | BACKLOG-085 Done; trunk `PlanVsExecutedView.tsx:225-229,422` has URL params, lens, AG Grid pagination | VERIFIED |
| `channel-ops-ag-grid-chrome` (U4g) | SUPERSEDED | trunk `sell-out/SellOutTab.tsx:358-433` ModuleDataSection + EnterpriseDataGrid | VERIFIED |
| `shipping-layout-rhythm` | SUPERSEDED | trunk `shipping/page.tsx` is now `InboundShipmentsWorkspace` | VERIFIED |
| `channel-ops-kpi-and-gap-scan-perf` | gap-scan perf **LOST** (L1); proxy timeout SUPERSEDED | see L1 | VERIFIED |
| shared: related-names + merge alias seal | SUPERSEDED | trunk `customer_merge_alias_seal.py`, `customer_related_master_groups.py`, `RelatedNameGroupsSection.tsx` (N-0095) | VERIFIED |
| `feat/steward-queue-depth` | **LOST** (L2) | | VERIFIED |
| `feat/listing-site-autoconfigure` | SUPERSEDED | trunk `listing_capture/autoconfig.py:600,622` (`_seller_values`, `_seed_seller`); trunk file is a superset | VERIFIED |
| `feat/report-schedules-beat` | SUPERSEDED | BACKLOG-098 Shipped 2026-08-17; trunk `report_schedule_runner.py`, `worker/tasks.py:14-17` (`progress_at`), `lineup/budget_position.py:30,87,105` | VERIFIED |
| `feat/ci-live-e2e` | PARKED | BACKLOG-099 "Deferred 2026-10-15 by Warren (N-0096)" | VERIFIED |
| `fix/web-grid-community-stabilization` | SUPERSEDED (rejected) | D-021 "Do not take" | VERIFIED |
| `fix/pm-bulk-upsert-coercion-and-sql-types` (+ same commit on `feature/background-tasks-shipment-evidence-pm`) | SUPERSEDED | BACKLOG-086 "Closed — not needed" 2026-08-16 | VERIFIED |
| `feature/background-tasks-shipment-evidence-pm` (May) | SUPERSEDED | trunk background-task listing `endpoints/imports.py:1626`, `services/imports/background_tasks`; DSI column intel `dsi_mapping_workflow.py:888` | VERIFIED (architecture); per-feature parity ASSERTED |
| `cursor/customer-sales-pipeline-2787` (May) | SUPERSEDED | replaced by CST `customer_sell_through.py:1577`, listing capture `models/listing_capture.py:43` | VERIFIED (architecture); ASSERTED (no unique function lost) |
| `cursor/dev-env-setup-2787`, `cursor/setup-dev-environment-ab45` (May) | SUPERSEDED | `database_url_sync_migrate` in trunk `alembic/env.py:107`; dashboard/exceptions rebuilt since | VERIFIED (setting); ASSERTED (UI) |
| `cursor/cloud-agent-1779984010444-wxmy7`, `-1779897120532-z2oy3` | SUPERSEDED / scratch | same content as stash@{10} / stash@{11}; DSI steward rebuilt since | ASSERTED |
| `wip/backlog-214-c57a`, `wip/backlog-214-e5d4` | SUPERSEDED | BACKLOG-214 Done, #82 `a3d0a9cd`; c57a content all on the trunk; e5d4 differs only by `apps/api/_prove_b214.py` | VERIFIED |
| `wip/folder-rescue-20261112`, `wip/programme-runtime-20261112` | rescue snapshots (EIF control-plane state), not product work | | VERIFIED |

### 4.3 Claims checked TRUE (step 3)

`cip` (read-only, `current_database()` = `cip`):

- Alembic on `cip` = `20261110_0061` (CONTEXT 11-12, CURRENT lines 17 and 93). VERIFIED
- Step 8: customers 1152 and 4145 `unverified`, not merged; 19 and 5013 still merged into 1; distributors 12 and 51 not merged; 2 `customer_identity_unmerge` audit events; distributor sell-out rows 786 and 178. VERIFIED
- Step 6 / BACKLOG-139: cases 3/309/310/311 workflow = status (cancelled/settled/cancelled/settled); 310 cases, 1,508 events, 4 `workflow_status_repair`; projection drift 0. VERIFIED
- Step 4 / N-0100 B1: `app_user.job` nullable, `ck_app_user_job` present, 3 users, 0 jobs set. VERIFIED
- Step 7 / D4 `0056`: `report_type`, `line_state`, `raw_source_row` nullable; `ix_shipment_ev_obs_evidence_line (evidence_line_id, id DESC)`; view has no `sel.pod_date`. VERIFIED
- Step 2 / N-0118: facts customer 11 = 1,544 and 12 = 4,237; total 20,546; superseded `restated_by_newer_load` 51 (units 1, SOH 15) and 82 (units 3, SOH 31). VERIFIED
- Step 3: listing seed `product_url_pattern` and `page_id_pattern` on customers 20, 52, 299. VERIFIED
- My accounts / Stage 1b grants: role `cip` has S/I/U/D on `user_customer_account`, `site_candidate`, `dc_served_account`, `store_dc_tenant_config`, and USAGE/SELECT on `user_customer_account_id_seq`; DELETE on `listing_site` (0059). VERIFIED
- M5c `0055`: `tenant_id` on `source_definition` and all six alias tables; `uq_source_definition_tenant_code`. VERIFIED
- BACKLOG-137: `cpor_case_line.window_start` / `window_end` NOT NULL on `cip`. VERIFIED
- Open book (CONTEXT 10-29): import job 1339 exists, `completed`. VERIFIED. The 765 / 51,705 counts are point-in-time. ASSERTED

Trunk code:

- BACKLOG-006 `shipment_mapping_candidates_list.py:42` pops `line_ids`; -091 `PlanVsExecutedView.tsx:649` "Over-plan intake" + `a1_pve.py:31` alias; -144 test seeds its own distributor and rolls back; -149 `brief/page.tsx` → `OverviewHub`; -150 `stock/page.tsx` → `StockContainer`; -200 no `MasterColumnPickerDialog` left; -210 `lineIdentifier.ts:89` used by `useFactColumns.ts`; -214 `prove_fresh_db_build.py`; -215 the four named tests reference none of DIST-01 / SKU-ALPHA-01 / CUST-1001; -216 `tests/_rls_role.py:42` + `ci.yml:75` NOSUPERUSER NOBYPASSRLS; -218 `shipment_change_events.py:33` (BACKLOG-218 comment, on-board / port ETA); -219 `brief_signals.py:662`; -220 `shipment_evidence_report_detect.py:13`; -221 `competition.py:156,165`; -222 `brief_signals.py:130-146`; -223 `stock_carry_forward_execute.py:26`; -224 0 tracked files under `.cip-alembic-smoke-pg`, `.gitignore:44`; -135 partial `customer_soh_check.py` `soh_tolerance` / `vat_basis_unknown`; -140 `customer_code_mint.py`. VERIFIED
- N-0118 NB1/NB3: `customer_sell_through_apply.py:74` `_LOOKUP_CHUNK_SIZE = 5000`, `:79` `_PY_WHITESPACE`; `customer_sell_through_supersede.py:57` `_ID_CHUNK_SIZE = 5000`. VERIFIED
- Merges #60, #65–#76, #78–#80, #82, #84–#88 are all on the trunk at the cited hashes; tip `4fce3b40` = Merge #84. VERIFIED

Commits from 2026-11-09 to 11-12 (stale `index.lock` window):

- All 129 hash-shaped tokens cited in CONTEXT (since 10-15) and CURRENT were resolved. Every commit cited for 11-09 to 11-12 exists on origin and is in the trunk. The only cited commit missing from origin is `06ababdf` (F1). Two tokens (`516b908a…`, `cc1810cf…`) are sha256 prefixes, not commits. VERIFIED
- `.git/index.lock` is absent in the main checkout now. VERIFIED

### 4.4 UNVERIFIABLE in this audit

- Test-pass counts (API 3,809 / web 1,272, E1–E10 suite counts, focused pytest runs): not re-run. ASSERTED
- `cip_test`-only claims (alias supersede counts, rolled-back proofs) and browser checks. ASSERTED
- Deploy health at 2026-11-12 18:23 (`/health/ready` 200, Celery ping): it can't be checked after the fact; the API is down now (section 3). ASSERTED
- BACKLOG-218 "existing observations backfilled on cip 2026-11-01", BACKLOG-203 "closed on cip_test", "cip aliases were not changed" (11-03): not probed. ASSERTED
- Backup files and sha256 values under `cip-apply-logs\` were not opened. ASSERTED

### 4.5 Guard events and deviations

- `SESSION_CLOSURE_REQUIRED` on the first call; verifier returned `SESSION_CLOSURE_OK`. VERIFIED
- `SECRET_STAGE` ×2 on the temporary-index `git add` (dirty worktrees): stopped, see L3. VERIFIED
- `PROTECTED_BRANCH_PUSH` on a push whose refspec came from `$(git for-each-ref …)` (read as a wildcard); re-issued with the 14 `wip/rescue-20261112-*` names spelled out, which the guard allowed. VERIFIED
- `SHIM_TOOL_UNMAPPED` on TaskStop for a read-only background scan; it ran to completion. VERIFIED
- `FOREIGN_PATH` on writing the probe script to the scratchpad; it was piped on stdin instead. VERIFIED
- One `cd` into `.worktrees/queue-n` during a read; the session folder was moved back to the root on the next call. VERIFIED
