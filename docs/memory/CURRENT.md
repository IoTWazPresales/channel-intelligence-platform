# CURRENT state

**Last updated:** 2026-10-05

**Branch:** `feat/ns-2-brief-nav-collapse`

**HEAD:** `08cc5278` (`eif: accept N-0064 charter`), pushed on this branch. The four-node close and its product edits are local and not committed. Do not sweep the rest of the dirty tree. Do not push main.

**Alembic (code):** `20260924_0023` (`cpor_case_line.window_start` / `window_end`; revises `20260906_0022`)

**Alembic on cip:** `20260906_0022`. Column `cpor_case_line.window_start` is absent. Role `cip` is the application login and is not the table owner. The `postgres` owner login rejected the app password, so the approved upgrade was not applied and was not stamped. Do not Apply or Create draft CPOR case on cip until `window_start` exists.

## Programme

N-0061, N-0062, N-0064, N-0066, and N-0067 are complete on the local ledger (programme rev 1488, not committed).

- **N-0061** — complete. Baseline `BLN-N0061`. Observability passes. The evidence-read code is still in the dirty working tree.
- **N-0062** — complete. A failed supply overview read logs and still returns an empty unavailable result. Arrived and plan-unit coverage stay derived. pytest 30 passed on supply coverage and plan-vs-executed. Supply page checked while signed in.
- **N-0064** — complete. Charter was already accepted. Buy-plan bias keeps only lines with 8 closed quarters, and an omitted period is the full history. The Execution vs plan tile shows product-line bias and the 6/8 rule. A single open quarter shows an empty value.
- **N-0066** — complete. Admin and planning headlines, widget formulas, and the vintage line under a widget no longer name tables. Checked on Administration, Planning, and the business dashboard.
- **N-0067** — complete. Charts, tabs, and chips follow the theme. Light was readable on Administration, Planning, Supply, and Execution vs plan. Dark was restored. Login gradients stay paired to the mode. The inbox email frame stays white.

**N-0036 bind is live, node not stamped.** `pnpm dev:api` listens on `127.0.0.1:8001` only (`CIP_API_HOST` unset). `GET /health` and `/health/ready` are 200 on that address. `GET /api/v1/auth/me` is 401 direct and through the web proxy on `:3000`. There is no `/api/v1/health` route (proxy 404). `localhost` resolves to `127.0.0.1` then `::1`; living callers were repointed to `127.0.0.1`. `node --test scripts/api-bind-host.test.cjs` 4 passed. Ledger still says blocked on change scope. Web `tsc` is exit 0 as of the N-0061 check. Quality gates for this node are still not stamped.

**N-0045 scratch list is already gone.** The 105 classified paths are not in the tree. Control-plane paths were not moved. Live dirty product files were not archived.

**N-0046 worktrees are gone.** The 13 `.wt-main-baseline` notes are copied under `.eif/audit/PROGRAMME_20261005/n0046-notes`. Bisect, main-baseline, the broken baseline folder, and the two outside checkouts are removed. Leftover databases were not dropped. The node stays open on that.

**N-0063 is deferred** (ledger rev 1435). No claim-file backfill. On cip: settled 211, ended 74, cancelled 23, draft 3, claim rows 0. Case rows were not changed. Upload customer report stays on the settlement desk. Uplift stays on BACKLOG-185 until at least five settled cases have claim rows.

**Decisions held, not built:** N-0065 — a user sees no Data unless product lines are assigned in permissions. N-0068 — keep multiple catalogs; do not retire `catalog_product`; per-line maps already overlay `column_mapping_memory`. N-0068 stays open on N-0067 and the five-vs-sixteen sellable grain. Do not start N-0069.

**Env:** local Windows. Web `:3000`. API `127.0.0.1:8001` only. Database `cip`. No Docker. The API virtualenv was rebuilt 2026-10-05 with Python 3.12 after the leftover baseline-folder delete removed its library files. `GET /health` and `/health/ready` are 200. The FX poller cannot write `fx_daily_rate` (role `cip` is not the owner). That does not stop the API.
