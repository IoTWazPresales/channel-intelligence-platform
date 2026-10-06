# CURRENT state

**Last updated:** 2026-10-06

**Branch:** `feat/ns-2-brief-nav-collapse`

**HEAD:** `bfbf01c0` (`eif: complete N-0046 leftover database hygiene`). Pushed. Do not sweep the dirty product tree. Do not push main.

**Alembic (code):** `20260924_0023` (`cpor_case_line.window_start` / `window_end`; revises `20260906_0022`)

**Alembic on cip:** `20260906_0022`. Column `cpor_case_line.window_start` is absent. Role `cip` is the application login and is not the table owner. The owner login works. The approved upgrade was not applied and was not stamped. Do not Apply or Create draft CPOR case on cip until `window_start` exists.

## Programme

Programme rev 1499. N-0036 and N-0046 are complete and pushed (`621a4a98`, `bfbf01c0`). N-0061, N-0062, N-0064, N-0066, and N-0067 are complete. Product `275da96f` excludes a strict open-and-shipped pair from the supply overview read and defaults shipment sheet load to Shipped and Unship. Fact rows were not rewritten. The sheet picker dialog and POST are still uncommitted inside already-dirty files.

- **N-0061** — complete. Baseline `BLN-N0061`. Observability passes. The evidence-read code is still in the dirty working tree.
- **N-0062** — complete. A failed supply overview read logs and still returns an empty unavailable result. Arrived and plan-unit coverage stay derived. pytest 30 passed on supply coverage and plan-vs-executed. Supply page checked while signed in.
- **N-0064** — complete. Charter was already accepted. Buy-plan bias keeps only lines with 8 closed quarters, and an omitted period is the full history. The Execution vs plan tile shows product-line bias and the 6/8 rule. A single open quarter shows an empty value.
- **N-0066** — complete. Admin and planning headlines, widget formulas, and the vintage line under a widget no longer name tables. Checked on Administration, Planning, and the business dashboard.
- **N-0067** — complete. Charts, tabs, and chips follow the theme. Light was readable on Administration, Planning, Supply, and Execution vs plan. Dark was restored. Login gradients stay paired to the mode. The inbox email frame stays white.

**N-0036 is complete.** `pnpm dev:api` listens on `127.0.0.1:8001` only (`CIP_API_HOST` unset). There is no `/api/v1/health` route. `node --test scripts/api-bind-host.test.cjs` passed 4. Ledger commit `621a4a98`.

**N-0045 scratch list is already gone.** The 105 classified paths are not in the tree. Control-plane paths were not moved. The node is still blocked until the current untracked set is classified. Live dirty product files were not archived.

**N-0046 is complete.** Worktrees are gone. The 16 leftover databases are dropped. `cip` and `cip_test` remain. Ledger commit `bfbf01c0`, pushed. `window_start` was not added.

**N-0063 is deferred** (ledger rev 1435). No claim-file backfill. On cip: settled 211, ended 74, cancelled 23, draft 3, claim rows 0. Case rows were not changed. Upload customer report stays on the settlement desk. Uplift stays on BACKLOG-185 until at least five settled cases have claim rows.

**Decisions held:** N-0065 — every screen filters to assigned product lines; no assignment means no Data; each assignment is read-only or read-and-edit. Not built. N-0068 — grain is every product line, set per business by an admin; keep `catalog_product`; do not unique-index EAN. Not built. N-0060 stays open: scoring must read whatever lineup history is stored and pick up older quarters when the archive is loaded. Do not start N-0069 or N-0070.

**Env:** local Windows. Web `:3000`. API `127.0.0.1:8001` only. Database `cip`. No Docker. The API virtualenv was rebuilt 2026-10-05 with Python 3.12 after the leftover baseline-folder delete removed its library files. `GET /health` and `/health/ready` are 200. The FX poller cannot write `fx_daily_rate` (role `cip` is not the owner). That does not stop the API.
