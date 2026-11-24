# CIP rules for the 24 Nov 2026 recovery (verbatim where marked)

This file is the copy later steps must follow. Sections 1 and 2 are copied character for character from the named sources. Later sections are the process this recovery uses. Interpretations are labelled ASSUMPTION. There is no "Decision:" line in this file.

## 1. Warren's standing rules (verbatim from the handoff, section (a))

Source: `C:\Users\warren_eliason\terminals\cursor-handoff-20261124-audit.md` section (a).

- Merge to `feat/integrate-20261103` only, **never main**. Promotion to main is on hold. Never force-push. Commit means push. Explicit-path `git add` only.
- DONE means merged, live restarted, and proven on live with real data. eslint and the production `next build` run before any restart. pg_dump backup before `scripts\cip-deploy.ps1 -Execute`. Each PR updates `docs/BACKLOG.md` and `docs/memory/CURRENT.md`.
- **No hardcoding or seeding.** Warren: "do not fucking hardcode ANY PAGES, do not overdo anything". No fuzzy joins. **Reuse existing code and components**, e.g. `apps/web/src/components/EnterpriseDataGrid.tsx`, `components/masterGrid/MasterDataGridShell.tsx`, `features/workbench-ui/Panel.tsx`, `features/workbench-ui/HeadlineFigure.tsx`, `components/ModuleDataSection.tsx`, `components/PageHeader.tsx`, `features/workbench-ui/DomainHeader.tsx`. No new UI or chart libraries.
- **Products always show the sales model name** (`dim_product.sales_model_name`), not only SKU/part number.
- **Promotions are sell-throughs. Sell-out is distributor (disti) to customer.** They must not be mixed. The promotion planner shows customer promotions, never sell-out.
- **The planner never shows closed, settled or ended cases** (or old years) by default.
- Prove on a small sample, then merge and go live.
- Tests only on `cip_test`, one suite at a time. **Live `cip` is read-only** except writes Warren approves. Don't rerun migrations 0063, 0064 or 0065.
- Never print secrets. The admin password and PG owner credentials are never echoed (`terminals\cip_admin_local_cred_20261119.env` and `apps/api/.env` must not be printed).
- PowerShell-safe syntax only.
- **Never switch, stash, reset or clean the main checkout.**
- **Never edit EIF ledgers, budgets, hooks or policy** (`.eif/`, hook scripts).
- No screenshots to Warren; results are reported in text.
- Coding is done by local Cursor on this PC, one cursor-agent at a time. The coordinator (Grok) only coordinates and verifies.

## 2. t454u verbatim (24 Nov 2026 ~23:30 SAST)

Source: the quoted block in `C:\Users\warren_eliason\terminals\impl-prompts-20261124\00-README.md`.

> 1. No, monitored listings needs to contain the matrix, everyhting else on the page works around it or above it, we can move or remove once its done.
> 2. Fine, keep original page, include promotion calendar AS PER THE FUCKING MOCKUP SPEC (Other content on the page can be worked around, or removed when we finish
> 3. NO FFS, Discovery has 4 different fucking libraries, they need to work properly, and auto discover when the fucking services are up, and if needed websites are conFIRMED by a user.....NO HARD CODING....it would possibly be on the monitored listings page on the side bar or something if needed  or there could be a banner or bar or something stating to confirm the weblinks....
> 4. Fine, BE SURE CURRENT COMPONENTS ARE SHARED WERE NECESSARY SO THE CHANGES ARE SMALL GOING FORWARD IF NEEDED
> 5. Yes fine
>
> Answers
> Yes?
> Suggested Retail price
> Correct, Sell through, sell out is disti to reseller and is still valuable but not here.
> YES i did because they need to be redisocvered so we can ensure they work
>
> Fresh cursor chat, BUT OPUS audit writes the prompt/prompts for us, and Grok 4.7 extra high NOT fast implements, and updates documents as it goes through so that we can switch over easily to Claude/Codex when cursor usage runs out. UNDERSTNAD?

## 3. Process rules

- Warren's words are quoted verbatim in every brief. Every interpretation is labelled **ASSUMPTION** and listed in the hand-back.
- No "Decision:" line unless Warren made that decision.
- Removing an existing screen or section, or rewriting a failing regression test to fit a new layout, needs Warren's explicit yes.
- Proof is a browser check on live against a written acceptance list taken from Warren's words and the mock-ups (`docs/design/dashboard-v2/index.html`, `targets-builder.html`, and the reference PNGs under `docs/handoffs/2026-11-23/assets/`), dark and light, reported as text.
- API JSON is not proof. DOM counts alone are not proof.
- Any recorded mismatch blocks the deploy.
- Every live database write is a STOP, with a pg_dump first.
- Merge and deploy are one STOP point in the step prompts. Overnight override (t455u, recorded in `00-EIF-FLOW.md`, which wins where the prompts differ): the coordinator merges into `feat/integrate-20261103` only after independent EIF verification passes. Never `main`. Live database writes stay a STOP and are skipped until Warren approves.
- Session 1 of a step implements, commits and pushes. It does not merge, deploy or restart. Session 2 is GOV-008 on another model. Session 3 is rendered verification after deploy.

## 4. Shared components to reuse

Checked present on `origin/feat/integrate-20261103` at `ca8f5f7f` unless noted.

| Use | Path |
|---|---|
| Data grid | `apps/web/src/components/EnterpriseDataGrid.tsx` |
| Master grid shell | `apps/web/src/components/masterGrid/MasterDataGridShell.tsx` |
| Panel | `apps/web/src/features/workbench-ui/Panel.tsx` |
| Headline figure and strip | `apps/web/src/features/workbench-ui/HeadlineFigure.tsx` (`HeadlineFigure`, `HeadlineStrip`) |
| Module loading / empty / error | `apps/web/src/components/ModuleDataSection.tsx` |
| Page header | `apps/web/src/components/PageHeader.tsx` |
| Domain header | `apps/web/src/features/workbench-ui/DomainHeader.tsx` |
| Status chip | `StatusChip` in `apps/web/src/features/workbench-ui/controls.tsx` (the file is `controls.tsx`, not a `controls/` directory) |
| Listing customer scope | `apps/web/src/features/market-listings/ListingCustomerScopePicker.tsx` |
| Site candidate queue | `apps/web/src/features/market-listings/SiteCandidatesQueue.tsx` |
| Column mapping | `apps/web/src/features/import-mapping/CanonicalColumnMappingPanel.tsx` |
| App theme | `apps/web/src/theme/cipTheme.ts` |
| Theme tokens | `apps/web/src/theme/cipTokens.ts` |
| Grid density | `apps/web/src/theme/gridDensity.ts` |
| AG Grid MUI theme | `packages/ui/src/agGridMuiTheme.ts` |

No new UI or chart libraries.

## 5. Environment recipe (measured 2026-11-25 on this worktree)

Worktree: `C:\Users\warren_eliason\channel-intelligence-platform\.worktrees\impl-step0`.
Branch at measurement start: `docs/impl-process-rules-20261125` from `origin/feat/integrate-20261103` at `ca8f5f7f`.
Shell cwd for install was the main repo folder. Test commands ran with cwd `<worktree>\apps\web`.

1. Install (do not change the lockfile; do not commit `node_modules`):

```
pnpm --dir C:\Users\warren_eliason\channel-intelligence-platform\.worktrees\impl-step0 install --frozen-lockfile --prefer-offline
```

Result: exit 0. "Lockfile is up to date, resolution step is skipped." Packages +587, reused 587, downloaded 0. "Done in 3m 0.2s using pnpm v9.15.9."

2. From `<worktree>\apps\web`:

```
node node_modules\vitest\vitest.mjs run src/theme/cipTheme.test.ts
```

Result: exit 0. Vitest v2.1.9. Test files 1 passed. Tests 4 passed. Vitest reported duration 23.72s. Stopwatch including process start: 27016 ms. Vite printed a CJS Node API deprecation warning.

```
node_modules\.bin\tsc.cmd --noEmit -p .
```

Result: exit 0. Stopwatch 53826 ms.

```
node node_modules\eslint\bin\eslint.js src/theme/cipTheme.ts
```

Result: exit 0. Stopwatch 14408 ms. ESLint 9.39.4. This run did **not** set `ESLINT_USE_FLAT_CONFIG`.

A run with `$env:ESLINT_USE_FLAT_CONFIG='false'` exited 2: "ESLint couldn't find a configuration file" (it looked for an eslintrc). The worktree's passing command is the one without that variable. Set it only when a later step's own config asks for it.

3. Database name check (prints the URL path only; do not print the URL):

```
. C:\Users\warren_eliason\terminals\disc_test_env.ps1
& C:\Users\warren_eliason\channel-intelligence-platform\apps\api\.venv\Scripts\python.exe -c "import os,urllib.parse as u;print(u.urlparse(os.environ.get('DATABASE_URL_SYNC') or os.environ.get('DATABASE_URL') or '').path)"
```

Result on 2026-11-25: `/cip_test`. If this prints empty or `/cip`, stop every database test and tell Warren. Do not edit `apps/api/.env` to force it.

Python for API tests, when a later step needs them: `C:\Users\warren_eliason\channel-intelligence-platform\apps\api\.venv\Scripts\python.exe`. One suite at a time. Never `ALLOW_TESTS_ON_DEV_DB` against live `cip`.

## 6. Live-write STOP list and deploy

STOP (pg_dump first, Warren runs the backup, live `cip` stays read-only until he says otherwise):

- Turning on `discovery.schedule_enabled`
- Confirming websites or any other tenant setting write
- Linking listings
- Restoring Takealot or Amazon readers
- Any other write to database `cip`
- Migrations, including 0063, 0064 and 0065 (do not rerun them)

Deploy, when a later step is allowed to deploy (not this docs step):

1. eslint and the production `next build` before any restart.
2. Warren runs the backup himself. `scripts\ops\backup_cip.ps1` line 24 is `Write-Host "Dumping $DatabaseUrl -> $out"`, which prints the full database URL. Do not run that script in an agent transcript.
3. `scripts\cip-deploy.ps1` with no `-Execute` is the plan. `-Execute` pulls `--ff-only` in the main checkout, then installs and builds.
4. The script refuses a linked worktree, a dirty tracked tree, or a detached HEAD (`scripts\cip-deploy.ps1` lines 13-14 and 130-143). It does not run from this worktree.

## 7. Secrets

Never print the admin@local password, PG_OWNER credentials, any `apps/api/.env` value, `terminals\cip_admin_local_cred_20261119.env`, or `apps/api/.env.bak-20261117`. Do not open `.env.bak-20261117`.

## 8. Code is evidence; docs are claims

From `AGENTS.md`: `CURRENT.md`, BACKLOG, ROADMAP, and commit messages that say "done" or "parity" are claims until the running tree shows them. Read the section or the commit before repeating a claim. If docs conflict with code or with each other, record the conflict and skip that item (overnight rule in `00-EIF-FLOW.md`) rather than picking a side in silence.

## Planner mock-up

`docs/design/planner-mockup.png` was not in the main checkout on 2026-11-25 (`Test-Path` false). Planner mock-up pending from Warren. Step 2 stops before final layout sign-off until that image is saved.

## ASSUMPTIONS carried from step 0

- A0-1: the Opus audit is copied to `docs/audits/RECOVERY_AUDIT_20261124.md` so BACKLOG Source fields can point at a repo path.
- A0-2: the four reference PNGs are committed so other worktrees can see them. Warren can refuse in the PR.
- A0-3: the handoff log lives at `docs/handoffs/2026-11-24/`, the dated-folder convention. `docs/handoff/` does not exist.
