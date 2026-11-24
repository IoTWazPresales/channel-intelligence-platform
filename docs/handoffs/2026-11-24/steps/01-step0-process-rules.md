# Step 0 — process rules, log and docs

- **Status:** In progress (session 1). Not merged. Not live-proven (docs only; no restart).
- **Branch:** `docs/impl-process-rules-20261125`
- **Worktree:** `C:\Users\warren_eliason\channel-intelligence-platform\.worktrees\impl-step0`
- **Base:** `origin/feat/integrate-20261103` at `ca8f5f7f`
- **PR:** compare URL after the docs push. `gh` was not used in this session.
- **Commits:** `4a076379` merged `docs/live-screen-audit-20261119` (docs file only). `6ab1ce71` docs rules, logs, audit copy, reference PNGs, CURRENT, BACKLOG, CONTEXT.
- **EIF node:** `N-0120` (explicit id). Events through `program.py`: `node.add`, `baseline.add` (`BLN-0019`), `node.lease.acquire`, `node.baseline`, `node.stage` to `implement`. Run `IMPL_step0_20261125`.

## Checklist

- [x] Read memory palace, CURRENT, CONTEXT, cursor rules present on disk, EIF manifest, autonomy policy, EIF CURRENT, WORK_ITEM, CONSULT, routing matrix
- [x] Worktree from `origin/feat/integrate-20261103` at `ca8f5f7f`, branch pushed
- [x] `RULES.md` with verbatim standing rules and t454u (`Compare-Object` MATCH, 14 lines and 13 lines)
- [x] Implementation log and eight step logs
- [x] Recovery audit copied (`docs/audits/RECOVERY_AUDIT_20261124.md`, 42614 bytes)
- [x] Four reference PNGs copied, not moved
- [x] 19 Nov audit merged (`docs/` only): `docs/audits/LIVE_SCREEN_AUDIT_20261119.md`
- [x] CURRENT and BACKLOG corrections cite file:line or commit
- [x] Planner mock-up checked: not on disk
- [x] Docs commit `6ab1ce71` (push recorded in Resume notes)
- [ ] Programme ledger commit — blocked. `git add` of the `.eif` programme paths was denied `CONTROL_PLANE_PROTECTED` on 2026-11-25. N-0120 exists only in the dirty worktree ledger, not in `7406e1b7`.

## ASSUMPTIONS

- A0-1: audit copied to `docs/audits/RECOVERY_AUDIT_20261124.md`.
- A0-2: four reference PNGs are committed so other worktrees can see them. Warren can refuse.
- A0-3: logs live under `docs/handoffs/2026-11-24/` because `docs/handoff/` does not exist.
- A0-4 (from `00-EIF-FLOW.md`, not a new product decision): open product decisions keep the prompt defaults. This step does not build those screens.
- A0-5: node id `N-0120` because `program.py` auto-id tried `N-0006`, which already exists. The id counter is behind explicit ids (119 node.add events, max id 119).

## STOP items waiting for Warren

- Live `cip` writes: none were needed. Still stopped: schedule flag, site confirmations, listing links, reader restore.
- Planner mock-up image.
- Whether to keep the four reference PNGs (A0-2).
- Appearance settings: per-user vs per-tenant (BACKLOG-283).
- Commit of `.eif/program/**` if the guard keeps returning `CONTROL_PLANE_PROTECTED`.
- The failed auto-id `add-node` cannot succeed. Closure may stay `SESSION_RETRY_REQUIRED` until an operator reviews an equivalent success. This session did not call `--resolve-equivalent`.

## Gates run

Worktree install, from the main repo folder:

`pnpm --dir <worktree> install --frozen-lockfile --prefer-offline`

Exit 0. Lockfile up to date. +587 reused. Done in 3m 0.2s. pnpm 9.15.9.

From `<worktree>\apps\web`:

- `node node_modules\vitest\vitest.mjs run src/theme/cipTheme.test.ts` — exit 0, 4 passed, Vitest duration 23.72s, stopwatch 27016 ms.
- `node_modules\.bin\tsc.cmd --noEmit -p .` — exit 0, stopwatch 53826 ms.
- `node node_modules\eslint\bin\eslint.js src/theme/cipTheme.ts` — exit 0, stopwatch 14408 ms, flat config (env var unset).
- Same eslint command with `ESLINT_USE_FLAT_CONFIG=false` — exit 2, no eslintrc found. Not the passing command.

Database path only, after dot-sourcing `terminals\disc_test_env.ps1`: `/cip_test`.

No production `next build` (docs step; the prompt says no build or restart).

`git diff --check` and `git diff --stat` against integrate: run after the docs commit and recorded in Resume notes.

## Live proof

None. Docs only. No deploy, no restart, no browser pass. The acceptance line "RULES.md is on origin/feat/integrate-20261103" is not met in session 1. `00-EIF-FLOW.md` says session 1 does not merge.

## Docs-vs-code conflicts (recorded, not silently picked)

1. Step prompt says `0bd7ed1b` rewrote 6 `MarketSurface.test.tsx` tests. `git show 0bd7ed1b` is a 5-line `beforeEach` (`nav.search = 'tab=observations'`). The matrix swap and the test file's larger edit are in `f1a561cb` (`MarketSurface.tsx` +11, `MarketSurface.test.tsx` +30 in the stat). CURRENT states the git fact.
2. Step prompt says readers were removed on purpose on 19 Nov. `LIVE_SCREEN_AUDIT_20261119.md` line 31 names commit `3ea6cce4` on 3 Nov for the code deletion. Line 146 says Warren stopped the 19 Nov restore because the deletion was on purpose. CURRENT states both dates.
3. `web_discovery/__init__.py` lines 9-10 say the schedule applies auto-linked sites. `apply.py` lines 300-313 queue `auto_accept` as proposed. BACKLOG-274 was corrected to the code. The comment was not edited (product code is out of scope).
4. Step prompt T11 says the diff may contain only `docs/` and the PNGs. `00-EIF-FLOW.md` says commit `.eif/program` files that `program.py` wrote and `.eif/audit/IMPL_step0_20261125/`. EIF flow wins. If the guard denies committing `.eif`, those files stay uncommitted in the worktree and are listed here.
5. `engineering-rules.mdc` is named by the memory palace and is not in `.cursor/rules/` (CURRENT already said it was missing). Not invented.

## Proposed for Warren

Do not edit `.cursor/rules` in this step. If you want the standing rules enforced as a Cursor rule, a later approved change can point at `docs/handoffs/2026-11-24/RULES.md` instead of pasting a second copy.

## Specialist passes (in this session)

`00-EIF-FLOW.md` says write these to `.eif/audit/IMPL_step0_20261125/`. The Write tool returned `PROTECTED_PATH` for `.worktrees/impl-step0/.eif/audit/...` (manifest protected path `.worktrees/*/.eif/**`). The passes are recorded here instead. They were not a second model.

### knowledge-documentation-steward (GOV-005)

Citations in CURRENT and BACKLOG were checked against the files named there. Verbatim rule blocks match the handoff and the prompt README (`Compare-Object` MATCH). Conflicts 1-3 in the section above were written as the code/git fact, not the prompt's shorter claim. `web_discovery/__init__.py` was not edited.

### delivery-planner (GOV-006)

Step order is the prompt table: 0, then 1 / 2 / 4a (Warren may reorder those three), 3 after 0 and 1, 3b only after 3 is live and Warren approves writes, 4b after 4a one slice at a time, 5 last. This session stops before merge.

### implementation-reviewer (CR-008)

No product-code blocker. MINOR: auto node ids are stuck at `N-0006`. MINOR: ledger commit may be `CONTROL_PLANE_PROTECTED`. Not an independent verification.

## Resume notes

Session 1 continues until the docs are pushed and N-0120 is at stage `validate` with the lease released. Do not merge from this session. Do not start step 1 in this chat.
