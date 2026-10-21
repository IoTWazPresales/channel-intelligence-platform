# N-0095 proof (2026-10-15)

Customer merge completion: alias seal at confirm (BACKLOG-081) with its companions (BACKLOG-083).
Product commits `694b46b8`, `5b076b1d`. Baseline: `BASELINE.md`.

## Acceptance criteria

1. **A confirmed merge mints approved loser-name aliases to the keeper.**
   `confirm_customer_full_merge_sync` seals each merged name as a global approved alias to the keeper,
   under both resolver keys when they differ. It moves an alias left on the merged record, reports an
   alias held by a third customer as a conflict (never overwritten, merge still completes) and never seals
   OPEN_CHANNEL. It writes a `customer_merge` platform audit event (steward, keeper, losers, rows moved per
   merged record, seal counts). Tests: `test_customer_merge_alias_seal_db.py` (10).
2. **Resolvers follow merged_into.** DB proof on cip_test, `test_merge_resolvers_follow_db.py` (5): DSI DB path
   and DSI resolution cache, shipment (alias token and stamped line), lineup (name/code map and alias map),
   sell-through (job anchor). Each returns the keeper for the merged record's name, code and an alias left on it.
   **Related-name worklist:** Customers → Duplicates → Related names. **Repair/backfill scripts:**
   `scripts/ops/backfill_merged_customer_alias_seals.py`, `scripts/ops/repair_open_channel_wrong_merge.py`,
   proven on clone `cip_n0095` before cip (`N0095_CLONE_PROOF.md`, PASS), then applied to cip
   (`N0095_CIP_APPLY.md`): 112 seal aliases minted, 0 conflicts, 28 test-fixture merges untouched, re-run plans 0.
3. **Tests, tsc, lint.** Full API pytest on cip_test: 2998 passed, 21 skipped, 0 failed. Full web vitest
   (one run, forks pool, 2 workers): 185 files, 864 passed, 0 failed. Web tsc exit 0; next lint clean on the changed files. No Python linter is installed.

## Warren's instructions for this node

- **Amazon:** not two live records. 26 "Amazon" was merged into 299 on 2026-07-11. Warren chose (in chat) a
  change-keeper action: Customers → Duplicates → **Past merges** lists the pair with rows, sell-through, cases
  and aliases now on each record and **Make this the keeper** (preview, reason, confirm). The keeper was not
  changed on cip. On the clone, 299 → 26 moved 10,786 rows and swapping back restored identical counts.
  Panel: `/admin/customers/duplicates?tab=past_merges&q=amazon`.
- **Test fixtures:** left untouched. Left out of the related-name and past-merges lists and the backfill, and
  counted (143 fixture customers on cip, 28 in merges).

## Limits

- Not rendered in the browser: the page redirects to sign-in. Component tests cover both tabs.
- Which rows came from 26 before the July merge was not recorded. New merges now record rows moved per record.
- Compuspeed LTD and SYNTECH DISTRIBUTION (PTY) LTD are merged into OPEN_CHANNEL; listed, not undone.
- cip_test lacks the alias table's indexes (drift). Old merge endpoints check sign-in only.
- Self-verified, same session and model; N-0099 does the second look.
