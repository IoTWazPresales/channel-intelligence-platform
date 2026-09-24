# N-0046 — BACKLOG-143 worktrees and leftover state (inventory, 2026-09-24)

Run N0046_IMPL_20260924. Nothing was removed: dropping databases is `destructive_data` (policy false), worktree removal deletes files, and the branch is also on the remote. Every item below is Warren's call; exact commands are given. `cip` is never touched.

## Git worktrees (`git worktree list`)
| Path | HEAD | Local changes | Proposal |
|---|---|---|---|
| `.wt-baseline-4ea1782/` | 4ea1782e | 0 | remove: `git worktree remove .wt-baseline-4ea1782` |
| `.wt-bisect-5b55c81/` | 5b55c819 | 0 | remove: `git worktree remove .wt-bisect-5b55c81` |
| `.wt-main-baseline/` | 4ea1782e | 13 untracked (`_run_*.py`, `pytest-*.txt`, `backlog-*.md`, `context-*.md`, `phase4-prompt.txt`) | archive those 13 files first (they are session notes from the R1c/R1d RBAC merge), then `git worktree remove .wt-main-baseline` |
| `C:\Users\warren_eliason\.tmp\dsi_baseline` | 55787653 | not inspected (outside repo roots) | Warren |
| `C:\Users\warren_eliason\cip-clean-runtime` | f6a8ee81 | not inspected (outside repo roots) | Warren |

## Branch
`feat/shipping-mailer-recipients` (local + origin), tip `b5cf3a03` "docs: pin VERIFY PASS for shipping-mailer recipients". BACKLOG-143 says it carries the 0019 migration; cip is at `20260906_0022`, so 0019 has since landed by another path — check with `git log --oneline main..feat/shipping-mailer-recipients` and close it if empty of unique work.

## Databases on the local server (sizes, `pg_database_size`)
`cip` 2,415 MB (live, keep) · `cip_test` 20 MB (keep: the only writable proof DB, used by N-0039/N-0040/N-0047..N-0050) · `postgres`.
Leftover clones and smoke DBs, ~35 GB total: `cip_merged_leftover_repair` 2,325 MB (alembic 0019, last import 2026-08-19) · `cip_ns4_settle_clone` 2,326 MB (0020, 2026-09-02) · `cip_unit3_smoke`, `cip_unit4_smoke`, `cip_unit6a_smoke`, `cip_unit6c_smoke` (≈2,281 MB each; 6c at 0010, 2026-08-05) · `cip_po_carry_smoke` 2,281 · `cip_oc_absorb_smoke` 2,275 · `cip_invoice_grad_smoke` 1,991 · `cip_lineup_month_smoke` 1,991 · `cip_bulk_smoke` 1,988 · `cip_planD_smoke` 1,982 · `cip_pland_smoke` 1,913 · `cip_alembic_smoke` 1,254 · `cip_clone_dup066` 1,131 · `cip_alembic_empty` 15.
Proposal: drop all of them except `cip` and `cip_test` (Warren, as a superuser: `DROP DATABASE <name>;` one per line). Note the `cip` role cannot `CREATE DATABASE` today, so these cannot be recreated by the agent; if Warren wants clone proofs on a full current copy, grant CREATEDB to a separate role or create one fresh clone (`CREATE DATABASE cip_clone_20260924 TEMPLATE cip` with no connections to cip) and drop the stale ones.

## Other
`.tmp_lf_rerun.txt`: already gone (N-0030). Scratch files: see N-0045 archive script.
