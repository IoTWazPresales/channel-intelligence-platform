# GOV-008 review — N-0120 (Step 0: process rules and handoff documents)

- **Verdict:** `VERIFIED_WITH_LIMITATIONS`
- **Mode:** `implementation-verification` plus evidence skeptic
- **Run:** `GOV008_N0120_20261125`, actor `gov-008-n0120-opus`
- **Independence rung:** different session and different model. Session 1 was Grok 4.7 (run `IMPL_step0_20261125`, actor `gov-001`). This review was Claude Opus 5.5 in a fresh chat. N-0120 is R1, which only needs a self-check, so this is above the bar.
- **Scope:** branch `docs/impl-process-rules-20261125`, base `ca8f5f7f` (`origin/feat/integrate-20261103`), tip `b67ba00a` (equal to `origin/docs/impl-process-rules-20261125` at review time). Worktree `.worktrees\impl-step0`.
- **Must not:** edit product or programme source, approve a parent change, or turn missing evidence into a negative fact. Nothing outside this file was edited.
- **Date:** 2026-11-25 (SAST)

## What was checked, and how

Everything below was re-run in this session. Nothing is copied from the Session 1 JOB_DONE.

### Diff and scope

- `git diff --stat ca8f5f7f b67ba00a`: 19 files, +1471 / -10. Paths are `CONTEXT.md`, `docs/**` and the four PNGs under `docs/handoffs/2026-11-23/assets/`. No product source, no `.eif/`, `.cursor/`, `.claude/` or `CLAUDE.md` path.
- `git diff --check ca8f5f7f b67ba00a`: exit 0.
- Main checkout `git status --porcelain`: the same nine untracked entries as the session-start snapshot. Nothing tracked changed.

### Copies are byte-identical (`Get-FileHash` SHA-256)

| Repo file | Source | Result |
|---|---|---|
| `docs/audits/RECOVERY_AUDIT_20261124.md` | `terminals\cursor-audit-20261124-opus.md` | SAME (`B78B199DA31C…`) |
| `dashboard-design-reference-dark.png` | main checkout, same path (untracked) | SAME |
| `dashboard-design-reference-light.png` | same | SAME |
| `targets-design-reference-dark.png` | same | SAME |
| `targets-design-reference-light.png` | same | SAME |
| `docs/audits/LIVE_SCREEN_AUDIT_20261119.md` | `origin/docs/live-screen-audit-20261119` (`d9001421`) | `git diff --quiet` exit 0 |

T7: `git diff --stat origin/feat/integrate-20261103...origin/docs/live-screen-audit-20261119` lists only `docs/audits/LIVE_SCREEN_AUDIT_20261119.md`. A merge was therefore the right choice. `4a076379` has parents `ca8f5f7f d9001421`, and `git diff --stat ca8f5f7f 4a076379` is that one file.

### Verbatim checks (`Compare-Object -CaseSensitive -SyncWindow 0`, ordered)

- `RULES.md` section 1 (14 bullets) against handoff section (a), lines 13-27: MATCH.
- The same 14 bullets against the step prompt's standing-rules block: MATCH.
- `RULES.md` section 2 (13 `>` lines) against the t454u block in `00-README.md`, lines 73-87: MATCH.
- The same 13 lines against handoff section (g): MATCH.

My first pass reported differences in two of these comparisons. Both were caused by my own line ranges: the README's `>` banner on line 3 was included, and one step-prompt line was cut off. With the correct ranges, both comparisons match.

### Citations in CURRENT and BACKLOG (read at the cited lines)

Every citation below resolves, and the content matches the claim:

- `cipTheme.ts` 36 (`h5` `0.9375rem`), 65 (colour inside `backgroundImage`), 69-73 (`MuiPaper` `overflow: 'hidden'`, which supports BACKLOG-280's "Paper clipping" even though that entry gives no line number).
- `PageHeader.tsx` 29 and `DomainHeader.tsx` 43 (`variant="h5"`); `AppShell.tsx` 129 (`bgcolor: 'background.default'`); `dashboard-v2/index.html` 62 (`h1 { font-size:27px`).
- `MarketSurface.tsx` 918 (`PriceMatrixLens`); `MarketSurface.test.tsx` 135 and 138.
- `plannerCalendarScope.ts` 2-10; `promotion_type_vocab.py` 9-13 (three types, including `Sell out PP`); `cpor_cases.py` 653.
- `PromotionPlannerSurface.tsx` 170-179, 194-202 (`status: 'ended'` query), 270-271, 518, 991 (`useState('Sell out PP')`).
- `DiscoveryLens.tsx` 39-45; `discoveryApi.ts` 290 and 316 (`previewAllowed` is `previewBlockReason(...) === null`, so CURRENT's "buttons stay off only while `previewBlockReason` is set" is correct).
- `listing_discovery.py` 69-84; `observation.py` 230-243 (env var or Settings; D-0061 note at 235).
- `tasks.py` 885-895 (`discovery_schedule_off`); `web_discovery/__init__.py` 9-10; `apply.py` 283-298 (user domains confirmed), 300-313 (`auto_accept` and `queue` saved as `WEB_SITE_PROPOSED`), 329, 376-384; `scheduled.py` 85-86 (`sites_only=True`); `scoring.py` 230-232.
- `scripts/cip-deploy.ps1` 13-14 and 130-135; `scripts/ops/backup_cip.ps1` line 24 is a `Write-Host` of `$DatabaseUrl` (the pattern was matched without printing the line).
- `terminals\audit-20261124-recovery-sql.txt`: `cpor_superseded` row `0 | 310` (lines 133-134); `listing_site` Evetech `html_page` (line 31).
- `LIVE_SCREEN_AUDIT_20261119.md` lines 31 (`3ea6cce4`, 3 Nov) and 146 (Warren stopped the 19 Nov restore).
- Commits: `0bd7ed1b` is one file, +4/-1 (`MarketSurface.test.tsx`), so Session 1's correction of the prompt's "rewrote 6 tests" is right. `f1a561cb` changes `MarketSurface.tsx` +11 and `MarketSurface.test.tsx` +30. `3ea6cce4` is dated 2026-11-03. `b79b1d33` is an ancestor of `ca8f5f7f`.

Both BACKLOG corrections (272 changed from Done to Partial, 274 rewritten to what `apply.py` and `scheduled.py` actually do) match the code.

### Gates re-run in the worktree

| Command (cwd `<worktree>\apps\web` unless noted) | Result |
|---|---|
| `node node_modules\next\dist\bin\next build` | exit 0, 177 s. Route table printed. `next.config` has no `ignoreBuildErrors` / `ignoreDuringBuilds`, so the build type-checked. |
| `node node_modules\vitest\vitest.mjs run src/theme/cipTheme.test.ts` | exit 0, 1 file, 4 passed, 21.84 s |
| `node node_modules\eslint\bin\eslint.js src/theme/cipTheme.ts` | exit 0 (flat config) |
| DB path after `disc_test_env.ps1`, in a child process, path only | `/cip_test` |

No DB test applies: this step changes docs only, and no connection was opened. `tsc --noEmit` was not re-run separately; the build's type-check covers it. Neither the full `pnpm lint` nor the full vitest suite was run.

### Warren's rules and forbidden items

| Check | Result |
|---|---|
| Hardcoding or seeding | None (docs only) |
| New libraries; lockfile | None; `pnpm-lock.yaml` not in the diff |
| Removed screens; rewritten, deleted or weakened tests | None |
| Fuzzy joins | None (no code) |
| Secrets | Regex scan of all 1,471 added lines (DB URLs with credentials, password/secret/api-key assignments, private keys, `sk-`/`ghp_`/JWT tokens): 0 hits. 0 email addresses. `.env` was not read in this session. |
| "Decision:" lines | 7 added lines contain the word. All of them describe the anti-pattern (audit copy and RULES). None records a decision. |
| `.eif/` / `.cursor/` / `.claude/` / `CLAUDE.md` edits on the branch | None |
| Merge to main, force-push, `add -A` | None found in the commits |

### Acceptance criteria (node N-0120)

| Criterion | Result |
|---|---|
| t454u: implementer updates documents as it goes so a switch to Claude/Codex is easy | PASS. RULES, the index, eight step logs with all 11 template fields each, CURRENT "Next" rewritten to the step order. |
| RULES.md contains the standing rules verbatim | PASS (four Compare-Object checks above) |
| IMPLEMENTATION_LOG and eight step logs exist | PASS |
| CURRENT and BACKLOG corrections cite a file:line or commit | PASS (all re-read above). BACKLOG-280 "Paper clipping" has no line number; the claim is true at `cipTheme.ts` 69-73. |
| No product source outside docs and the reference images | PASS. `CONTEXT.md` also changed; see L4. |
| Step prompt: RULES.md on `origin/feat/integrate-20261103` | NOT YET. This waits for the coordinator merge (`00-EIF-FLOW.md` override 1). It is not a Session 1 failure. |

## Limitations (why not `VERIFIED`)

- **L1. Ledger not reproducible from the branch.** N-0120's events (seq 2929-2935) and this review's events exist only in the dirty worktree files `.eif/PROGRAM.md`, `.eif/ROADMAP.md`, `.eif/program/PROGRAM.yaml`, `.eif/program/PROGRAM_LOG.ndjson` and `.eif/runs/`. The guard denies `git add` on them (`CONTROL_PLANE_PROTECTED`). A fresh checkout of the tip has no N-0120. Warren (operator) has to commit them.
- **L2. Guard state.** During this session the guard denied one read-only shell call, run with the worktree as cwd, with `SESSION_COMMIT_REQUIRED` ("Commit the programme ledger with explicit paths before closing or starting unrelated work"). It was not retried. Session 1 also recorded a failed auto-id `add-node` (`NODE_EXISTS N-0006`) that may leave `SESSION_RETRY_REQUIRED` debt. Only the operator can clear either.
- **L3. Merge-dependent acceptance.** "RULES.md on integrate" and "PNGs on integrate" are not met until the coordinator merges. This is docs only, so there is no deploy or restart, and a rendered (Session 3) check has nothing to look at beyond the merge itself.
- **L4. Prompt self-conflict.** T11 says the diff may contain only `docs/` paths and the PNGs, and the acceptance list says no file outside `docs/` may change. T8 and the memory-palace rule require a `CONTEXT.md` changelog line. Session 1 followed T8. I treat that as correct and record the conflict.
- **L5. Not re-run here:** full `pnpm lint`, the full vitest suite, and standalone `tsc --noEmit`. None of them is affected by a docs-only diff.
- **L6. Claude Code and Codex reviews are pending** (`00-EIF-FLOW.md` override 5).

## Findings (non-blocking; for the coordinator or a later docs touch)

1. **CURRENT header contradicts the new Next list.** The unchanged header paragraph (line 3) still ends "Next agent: … Next: BACKLOG-266 audit, then price fixes R-04/R-05." The new `## Next` section gives the step 0-5 order. Trim the header's "Next" sentence.
2. **CURRENT `Branch:` names the docs branch.** That was correct at commit time. After the merge into `feat/integrate-20261103` it will be stale. Fix it in the merge or in the Step 1 commit.
3. **Paraphrase attributed to Warren in BACKLOG Source fields.** BACKLOG-276, 277, 278 and 281 say "Warren t454u: …" and then give a paraphrase without quote marks. That is the pattern the recovery audit criticised. RULES.md holds the verbatim text, which limits the risk. Quote the item verbatim, or label it "paraphrase of t454u item N".
4. **BACKLOG-284 attribution.** It says "Handoff section (g): Warren will re-send the planner mock-up." That sentence (handoff line 151) is in the "Coordinator's reading" subsection under (g), not in Warren's own words.
5. **Step 0 log is behind its own branch.** `steps/01-step0-process-rules.md` lists commits `4a076379` and `6ab1ce71` only (not `7406e1b7` or `b67ba00a`), and its Resume notes still describe Session 1 as in progress.
6. **BACKLOG-279 says "Deferred tonight"**, which is relative wording in a durable file.
7. **Product observation (Step 3 input, not a step 0 defect):** `DiscoveryLens.tsx` line 44 hides the block reason when `live_fetch` is false, so the Discover buttons are disabled with no visible reason in that state.

None of these blocks the merge. Every one of them is a wording or bookkeeping issue in docs that are otherwise correct.

## Docs-vs-code conflicts (confirmed independently)

- The prompt says `0bd7ed1b` rewrote six tests. Git shows a one-file +4/-1 change. The matrix swap is `f1a561cb`.
- The prompt says the readers were removed on 19 Nov. The code deletion is `3ea6cce4` (3 Nov). 19 Nov is when Warren stopped the restore.
- `web_discovery/__init__.py` lines 9-10 say the schedule "applies auto-linked sites". `apply.py` 300-313 saves them as proposed and `scheduled.py` 86 passes `sites_only=True`. The comment is wrong. It was not edited, because product code is out of scope.
- `engineering-rules.mdc` is named by the memory palace and AGENTS.md but is absent from `.cursor/rules/`.

## Programme events recorded by this review

Through `python -B .eif/runtime/programme/program.py --project <worktree> --run GOV008_N0120_20261125 --actor gov-008-n0120-opus event …` only:

- `node.quality` on `docs_surface`, state `pass`
- `node.verification` kind `referent`, state `pass`, verdict `VERIFIED_WITH_LIMITATIONS`

The node was not set to complete. Its stage was not changed.
