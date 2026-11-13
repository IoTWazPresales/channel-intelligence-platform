# CURRENT state

**Last updated:** 2026-11-13 (memory refresh only; no product change)

**Branch:** `docs/stage1-memory-refresh`

**Cut from:** `origin/main` @ `46368f6c` (2026-08-31, `docs: NS-2 readiness report`). Local `main` matched `origin/main` at that sha. Confirm HEAD with `git rev-parse`. This file does not store its own commit hash.

## Unresolved — do not pick a winner

1. **Trunk.** `origin/main` (`46368f6c`) is the merge-base of `origin/feat/integrate-20261103` and is **882 commits behind** it (0 commits the other way). Integrate tip read 2026-11-13: `267ee883` (`EIF ledger: N-0102 re-chartered...`). That branch's `docs/memory/CURRENT.md` still opens on a 2026-11-12 note (`4fce3b40`, lanes #88 #85 #86 #87 #84 merged) and says **next is repair the EIF guard**. This checkout does not contain that code. Nothing here was merged to `main`.
2. **Alembic.** **This tree's** code head is `20260818_0019` (`20260818_0019_shipping_mailer_recipient.py`, revises `20260818_0018`). Integrate's tree has revisions through `20261110_0061`. Integrate's CURRENT **claims** `cip` was at `20261110_0061` on 2026-11-12. This session did not run `alembic current`: no Postgres client, `docker info` failed, `CURSOR_CLOUD` unset. Live stamp: **unknown**.
3. **EIF files.** `docs/design/EIF_UNIT_DECLARATION.md` on this tree says `.eif/WORK_ITEM.md`, `DESIGN_EXPERIENCE_RECORD.md`, `programme-brownfield.md`, and `JOURNEYS.yaml` are present. `.eif/` is absent here and has never been on `origin/main` history. Those four paths **exist** on `origin/feat/integrate-20261103`. Still absent on that tip: `.eif/program/SCHEMA.md`, `tools/program.py`, and `.cursor/rules/eif-core.mdc` (the declaration quotes the rule). Programme mutator on that tip is `.eif/runtime/programme/program.py` (generated `.eif/CURRENT.md`). Not reconciled.
4. **VERIFY register text.** This tree's `docs/BACKLOG.md` says the register is **Cleared** (empty) at `12404bc`. Integrate's backlog says the 6f–B4 clearance **stands** and **BACKLOG-209** (N-0034 ScopeBar) is **open**. This refresh does not copy that row in.

## What this tree contains (`origin/main` @ `46368f6c`)

- VERIFY register text cleared for **6f, 7, 8, 11, 12, 15B, B4** (`12404bc`). Doc claim. Not re-run.
- NS-2 on **this** tree is discovery only: `docs/design/NS2_READINESS.md`. `navConfig.ts` is still seven groups (`overview`, `channel-intelligence`, `commercial-planning`, `master-data`, `data-imports`, `admin`). No `/brief` page here.
- Integrate **does** contain `apps/web/src/app/(app)/brief/page.tsx`. `origin/feat/ns-2-brief-nav-collapse` (`59033481`) is an ancestor of integrate (integrate is 202 commits ahead of it). Spine completeness was not audited.
- NS-1a files exist here: `apps/api/app/services/cpor/settle_readiness.py` (`case_missing_roe`). BACKLOG-148 is still **Parked**. Not a VERIFY close.
- Design language FROZEN v1.1 and charter v1.3 are on this tree (CONTEXT: promoted `83b4290`). Not re-audited.
- Operator topology in the memory palace remains Mode B (Windows, local `cip`, web `:3000`, API `:8001`). Not re-proven from this VM.

## In progress

- None on this branch. Convergence was not started.

## Next

- Wait for Warren's convergence prompt. Do not implement NS-2, EIF, or product work from this checkout.
- Name the trunk before coding. This file does not select `main` or `feat/integrate-20261103`.
- Live `alembic current` only after `current_database()` is `cip`. Do not upgrade.

## Blockers requiring Warren

- Which branch is the Stage 1 trunk.
- Live `cip` Alembic stamp (`20260818_0019` vs `20261110_0061` or later). Not measured here.
