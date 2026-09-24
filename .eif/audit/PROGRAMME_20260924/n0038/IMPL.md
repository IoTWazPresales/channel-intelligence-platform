# N-0038 IMPL — Stage 3.2: CPOR role checks on the existing roles (BACKLOG-136 / 141)

Implementation run (moment c). Lenses: backend-engineer, test-engineering-specialist, application-security-specialist / identity-access-specialist. R2, facets auth + api.
Commit: `209acf82` on `feat/ns-2-brief-nav-collapse` (not pushed). API not restarted (the running API picks this up on its next restart).

## Summary

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Every CPOR write requires a role from the existing set; viewer read-only; route table | **PASS** (31 write routes gated; 31 reads stay sign-in only; table below) |
| 2 | Shipment steward panels accept STEWARD + ADMIN | **PASS** (all 25 `require_roles(Role.ADMIN)` gates now `require_roles(Role.ADMIN, Role.STEWARD)`) |
| 3 | Role matrix with source; questions for Warren | **PASS** (one deliberate deviation from the brief's default: historical import = admin only, see Q1) |
| 4 | Tests: allowed + denied per group; no cip writes; existing CPOR tests pass | **PASS** (new file 17 tests; 255 passed in the regression run; 3 write-capable/clone modules skipped, reasons below) |
| 5 | Stub mode unaffected (stub user admin) | **PASS** |
| 6 | Web mismatches listed (no web change) | **PASS** (findings W1–W5) |

## What changed

Mechanism reused, nothing new: `app.core.security.require_roles(*allowed)` (security.py:177), which already admits `Role.ADMIN` unconditionally and returns 403 `"Insufficient role"` otherwise. No new roles, no new helper. Each CPOR module gets one module-level dependency instance next to `router = APIRouter()`, and each write view swaps `Depends(get_current_user)` for it (the dependency still resolves the same user dict through `get_current_user`, so actor stamping is unchanged).

| File | Change |
|------|--------|
| `apps/api/app/api/v1/endpoints/cpor_cases.py` | `_require_cpor_planner = require_roles(Role.PLANNER, Role.ADMIN)`; 16 write views |
| `apps/api/app/api/v1/endpoints/cpor_exports.py` | same dependency; 1 write view; dropped the now-unused `get_current_user` import |
| `apps/api/app/api/v1/endpoints/cpor_fx.py` | same dependency; 3 write views |
| `apps/api/app/api/v1/endpoints/cpor_historical_import.py` | `_require_cpor_historical_writer = require_roles(Role.ADMIN)`; 7 write views |
| `apps/api/app/api/v1/endpoints/cpor_payment_evidence.py` | `_require_cpor_steward = require_roles(Role.STEWARD, Role.PLANNER, Role.ADMIN)`; 4 write views |
| `apps/api/app/api/v1/endpoints/shipment_evidence.py` | 25 × `require_roles(Role.ADMIN)` → `require_roles(Role.ADMIN, Role.STEWARD)` (same order as `ops.py:22`, `steward_audit.py:19`) |
| `apps/api/tests/test_rbac_n0038_cpor_roles.py` | new: matrix introspection + behaviour tests (no DB) |

The view swap was done by `.eif/audit/PROGRAMME_20260924/n0038/gate_routes.py` (asserts exactly one `Depends(get_current_user)` per named view signature; output lists all 31 views).

## Role matrix and its source

| Group | Routes | Allowed | Source |
|-------|--------|---------|--------|
| Case lifecycle: create / patch / lines / void / split / recompute / intelligence-exclude / supersede (preview, confirm, restore) / **transition incl. settle** | cpor_cases.py | planner + admin | Brief default (BACKLOG-136 names KAM/PM/Ken/Wayne but leaves the mapping to Warren; Warren 2026-09-21: "enforce on existing admin/steward/planner/viewer") |
| Claim evidence import + settlement rollup | cpor_cases.py | planner + admin | Brief default "settle = planner + admin" (claim evidence feeds the settle amount; Ken "compiles/settles" in BACKLOG-136). See Q2 |
| Promo-plan draft recompute + create-case | cpor_cases.py | planner + admin | Brief default (case lifecycle). Recompute is a read-shaped POST, gated because every CPOR POST must be. See Q4 |
| Export generate | cpor_exports.py | planner + admin | Brief default |
| FX writes: rate fetch, backfill confirm, declare mode | cpor_fx.py | planner + admin | Brief default |
| Payment-evidence steward: map-token, mark-shell-case, re-resolve, apply | cpor_payment_evidence.py | steward + planner + admin | Brief default (data-steward work) |
| Historical import writes: map-token, bulk-map-token, validate, apply, resolution-plan, compute-async, apply-async | cpor_historical_import.py | **admin only** | **BACKLOG-136 regression trap (stated text, overrides the default):** "R1/R1b replaced the forgeable `_require_admin(X-User-Role)` admin gate on the CPOR historical-import router … R2 must restore an equivalent or stronger check on these routes specifically." The pre-R1 gate was admin-only (`git show 5b2a6a44~1:…cpor_historical_import.py` line 84). Planner+steward would be weaker, so I did not apply the default here. See Q1 |
| All CPOR GETs | all five modules | any signed-in user (router-level `get_current_user`) | Criterion 1 "viewer is read-only". Note: the historical-import GETs were also admin-only pre-R1; I kept them read-open (Q1) |
| Shipment-evidence steward panels (25 routes) | shipment_evidence.py | steward + admin | BACKLOG-141 + criterion 2. Bulk-delete (imports.py) and Product Master commit (imports_product_master.py) untouched, as BACKLOG-141 requires |

## Criterion 1 — every CPOR route, method, role now required

Generated from the mounted app by `.eif/audit/PROGRAMME_20260924/n0038/route_table.py` (output `route_table.txt`, read-only introspection). "admin" always passes `require_roles`.

| # | Method | Path | Handler | Role required |
|---|--------|------|---------|---------------|
| 1 | GET | `/api/v1/cpor/cases` | `cpor_cases.list_cases` | any signed-in user (read) |
| 2 | POST | `/api/v1/cpor/cases` | `cpor_cases.create_case` | admin + planner |
| 3 | GET | `/api/v1/cpor/cases/{case_id}` | `cpor_cases.get_case` | any signed-in user (read) |
| 4 | PATCH | `/api/v1/cpor/cases/{case_id}` | `cpor_cases.patch_case` | admin + planner |
| 5 | POST | `/api/v1/cpor/cases/{case_id}/intelligence-exclude` | `cpor_cases.set_intelligence_exclude` | admin + planner |
| 6 | POST | `/api/v1/cpor/cases/{case_id}/supersede/preview` | `cpor_cases.preview_supersede_case` | admin + planner |
| 7 | POST | `/api/v1/cpor/cases/{case_id}/supersede` | `cpor_cases.supersede_case_endpoint` | admin + planner |
| 8 | POST | `/api/v1/cpor/cases/{case_id}/supersede/restore` | `cpor_cases.restore_supersede_case` | admin + planner |
| 9 | POST | `/api/v1/cpor/cases/{case_id}/lines` | `cpor_cases.create_line` | admin + planner |
| 10 | PATCH | `/api/v1/cpor/cases/{case_id}/lines/{line_id}` | `cpor_cases.patch_line` | admin + planner |
| 11 | POST | `/api/v1/cpor/cases/{case_id}/lines/{line_id}/void` | `cpor_cases.void_line` | admin + planner |
| 12 | POST | `/api/v1/cpor/cases/{case_id}/lines/{line_id}/split-layers` | `cpor_cases.split_layers` | admin + planner |
| 13 | POST | `/api/v1/cpor/cases/{case_id}/recompute` | `cpor_cases.recompute` | admin + planner |
| 14 | GET | `/api/v1/cpor/cases/{case_id}/lines/{line_id}/cost-suggest` | `cpor_cases.cost_suggest` | any signed-in user (read) |
| 15 | GET | `/api/v1/cpor/cases/{case_id}/events` | `cpor_cases.list_events` | any signed-in user (read) |
| 16 | GET | `/api/v1/cpor/cases/{case_id}/pivot` | `cpor_cases.case_pivot` | any signed-in user (read) |
| 17 | POST | `/api/v1/cpor/cases/{case_id}/transition` (propose/approve/…/**settle**) | `cpor_cases.transition_case` | admin + planner |
| 18 | GET | `/api/v1/cpor/settlement/book` | `cpor_cases.cpor_settlement_book` | any signed-in user (read) |
| 19 | GET | `/api/v1/cpor/intelligence/portfolio` | `cpor_cases.cpor_portfolio_intelligence` | any signed-in user (read) |
| 20 | GET | `/api/v1/cpor/intelligence/incremental-unit-cost` | `cpor_cases.cpor_incremental_unit_cost` | any signed-in user (read) |
| 21 | GET | `/api/v1/cpor/intelligence/norms` | `cpor_cases.cpor_support_norms` | any signed-in user (read) |
| 22 | GET | `/api/v1/cpor/intelligence/comparable-cases` | `cpor_cases.cpor_comparable_cases` | any signed-in user (read) |
| 23 | GET | `/api/v1/cpor/intelligence/support-bias` | `cpor_cases.cpor_support_bias` | any signed-in user (read) |
| 24 | GET | `/api/v1/cpor/cases/{case_id}/promo-load-recon` | `cpor_cases.cpor_promo_load_recon` | any signed-in user (read) |
| 25 | GET | `/api/v1/cpor/cases/{case_id}/payment-recon` | `cpor_cases.cpor_payment_recon` | any signed-in user (read) |
| 26 | GET | `/api/v1/cpor/intelligence/promo-plan-draft` | `cpor_cases.cpor_promo_plan_draft` | any signed-in user (read) |
| 27 | POST | `/api/v1/cpor/intelligence/promo-plan-draft/recompute` | `cpor_cases.cpor_promo_plan_recompute` | admin + planner |
| 28 | POST | `/api/v1/cpor/intelligence/promo-plan-draft/create-case` | `cpor_cases.cpor_promo_plan_create_case` | admin + planner |
| 29 | GET | `/api/v1/cpor/meta/promotion-types` | `cpor_cases.promotion_types` | any signed-in user (read) |
| 30 | GET | `/api/v1/cpor/cases/{case_id}/settlement` | `cpor_cases.get_settlement` | any signed-in user (read) |
| 31 | POST | `/api/v1/cpor/cases/{case_id}/claim-evidence/import` | `cpor_cases.import_claim_evidence` | admin + planner |
| 32 | POST | `/api/v1/cpor/cases/{case_id}/settlement/rollup` | `cpor_cases.post_settlement_rollup` | admin + planner |
| 33 | GET | `/api/v1/cpor/meta/lifecycle` | `cpor_cases.lifecycle_meta` | any signed-in user (read) |
| 34 | GET | `/api/v1/cpor/fx/rates/today` | `cpor_fx.fx_rate_today` | any signed-in user (read) |
| 35 | POST | `/api/v1/cpor/fx/rates/fetch` | `cpor_fx.fx_rate_fetch` | admin + planner |
| 36 | GET | `/api/v1/cpor/fx/backfill-suggestions` | `cpor_fx.fx_backfill_suggestions` | any signed-in user (read) |
| 37 | POST | `/api/v1/cpor/fx/backfill-confirm` | `cpor_fx.fx_backfill_confirm` | admin + planner |
| 38 | POST | `/api/v1/cpor/fx/declare-mode` | `cpor_fx.fx_declare_mode` | admin + planner |
| 39 | POST | `/api/v1/cpor/cases/{case_id}/export` | `cpor_exports.generate_export` | admin + planner |
| 40 | GET | `/api/v1/cpor/cases/{case_id}/exports` | `cpor_exports.list_exports` | any signed-in user (read) |
| 41 | GET | `/api/v1/cpor/cases/{case_id}/exports/{version}/file` | `cpor_exports.download_export` | any signed-in user (read) |
| 42 | GET | `/api/v1/cpor/historical-import/profiles` | `cpor_historical_import.list_mapping_profiles` | any signed-in user (read) |
| 43 | GET | `/api/v1/cpor/historical-import/jobs/{job_id}/summary` | `cpor_historical_import.historical_job_summary` | any signed-in user (read) |
| 44 | GET | `/api/v1/cpor/historical-import/jobs/{job_id}/candidates` | `cpor_historical_import.historical_candidates` | any signed-in user (read) |
| 45 | POST | `/api/v1/cpor/historical-import/jobs/{job_id}/map-token` | `cpor_historical_import.historical_map_token` | admin |
| 46 | POST | `/api/v1/cpor/historical-import/jobs/{job_id}/bulk-map-token` | `cpor_historical_import.historical_bulk_map_token` | admin |
| 47 | POST | `/api/v1/cpor/historical-import/jobs/{job_id}/validate` | `cpor_historical_import.historical_validate` | admin |
| 48 | POST | `/api/v1/cpor/historical-import/jobs/{job_id}/apply` | `cpor_historical_import.historical_apply` | admin |
| 49 | GET | `/api/v1/cpor/historical-import/jobs/{job_id}/progress` | `cpor_historical_import.historical_progress` | any signed-in user (read) |
| 50 | POST | `/api/v1/cpor/historical-import/jobs/{job_id}/resolution-plan` | `cpor_historical_import.historical_resolution_plan_generate` | admin |
| 51 | POST | `/api/v1/cpor/historical-import/jobs/{job_id}/resolution-plan/compute-async` | `cpor_historical_import.historical_resolution_plan_compute_async` | admin |
| 52 | POST | `/api/v1/cpor/historical-import/jobs/{job_id}/resolution-plan/apply-async` | `cpor_historical_import.historical_resolution_plan_apply_async` | admin |
| 53 | GET | `/api/v1/cpor/historical-import/jobs/{job_id}/resolution-plan-task/{task_id}` | `cpor_historical_import.historical_resolution_plan_task_status` | any signed-in user (read) |
| 54 | GET | `/api/v1/cpor/payment-evidence/profiles` | `cpor_payment_evidence.list_profiles` | any signed-in user (read) |
| 55 | GET | `/api/v1/cpor/payment-evidence/overlay` | `cpor_payment_evidence.payment_evidence_overlay` | any signed-in user (read) |
| 56 | GET | `/api/v1/cpor/payment-evidence/jobs/{job_id}/summary` | `cpor_payment_evidence.job_summary` | any signed-in user (read) |
| 57 | GET | `/api/v1/cpor/payment-evidence/jobs/{job_id}/candidates` | `cpor_payment_evidence.candidates` | any signed-in user (read) |
| 58 | POST | `/api/v1/cpor/payment-evidence/jobs/{job_id}/map-token` | `cpor_payment_evidence.map_token` | admin + steward + planner |
| 59 | POST | `/api/v1/cpor/payment-evidence/jobs/{job_id}/mark-shell-case` | `cpor_payment_evidence.mark_shell` | admin + steward + planner |
| 60 | POST | `/api/v1/cpor/payment-evidence/jobs/{job_id}/re-resolve` | `cpor_payment_evidence.re_resolve` | admin + steward + planner |
| 61 | POST | `/api/v1/cpor/payment-evidence/jobs/{job_id}/apply` | `cpor_payment_evidence.apply_job` | admin + steward + planner |
| 62 | GET | `/api/v1/cpor/cases/{case_id}/payment-evidence` | `cpor_payment_evidence.list_case_payment_evidence` | any signed-in user (read) |

62 CPOR routes: 31 writes (all gated, none admit viewer), 31 GETs (sign-in only). There are no PUT or DELETE routes under `/cpor`. `test_every_cpor_write_route_matches_the_role_matrix` fails if a new CPOR write route is added without a matrix entry, or if any gate drifts.

Out-of-router CPOR writes (not in the five modules): the file upload that *creates* a historical-import or payment-evidence job goes through the generic `POST /api/v1/imports/…` upload (`imports.py:531-536`, template slugs `cpor_historical_cases`, `cpor_payment_evidence`) — not gated by this node (finding F2).

## Criterion 2 — shipment steward panels

`grep -c "require_roles(Role.ADMIN, Role.STEWARD)" shipment_evidence.py` = 25; `grep -c "require_roles(Role.ADMIN))"` = 0. Route table: `route_table.txt` second section (rows 1–21, 26–29 = admin + steward). Planner and viewer get 403 (tested). `test_rbac_r1c_admin_gates.py` (41 swept routes still carry `require_roles`) passes unchanged. Not widened, per BACKLOG-141: `imports.py` bulk-delete preview/confirm and `imports_product_master.py` (incl. commit) remain `require_roles(Role.ADMIN)`.

## Criterion 4 — tests

New: `apps/api/tests/test_rbac_n0038_cpor_roles.py` (not in `_WRITE_CAPABLE_TEST_MODULES`; no DB: `get_current_user`, `get_db` and payment-evidence `_sync_db` are overridden; allowed-role calls use a non-integer path id or invalid body so they stop at 422 **after** the role dependency has passed, before any handler/SessionLocal).

- `test_every_cpor_write_route_matches_the_role_matrix` — exact allowed set per write route (read from the `require_roles` closure).
- `test_no_cpor_write_admits_viewer`, `test_cpor_reads_stay_authentication_only`, `test_shipment_evidence_gates_admit_steward_and_admin` (25 gates = {admin, steward}).
- Behaviour (allowed → 422, denied → 403 "Insufficient role"), one case per guarded group:

| Group | Request | Allowed | Denied (403) |
|-------|---------|---------|--------------|
| Lifecycle / settle | POST `/cpor/cases/x/transition` | planner | viewer, steward |
| Case patch | PATCH `/cpor/cases/x` | planner | viewer |
| Export | POST `/cpor/cases/x/export` | planner | viewer, steward |
| Settlement rollup | POST `/cpor/cases/x/settlement/rollup` | planner | viewer |
| FX | POST `/cpor/fx/backfill-confirm`, `/cpor/fx/declare-mode` | planner | viewer, steward |
| Historical import | POST `/cpor/historical-import/jobs/x/apply` | admin | viewer, planner, steward |
| Payment evidence | POST `/cpor/payment-evidence/jobs/x/apply`, `/map-token` | steward, planner | viewer |
| Shipment steward | POST `/shipment-evidence/jobs/x/apply`, GET `/shipment-evidence/x` | steward | viewer, planner |
| Admin | transition + payment apply | admin | — |
| Viewer read | GET `/cpor/cases/x` | viewer → 422 (not 403) | — |

Commands and results:
```
apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_rbac_n0038_cpor_roles.py apps/api/tests/test_cpor_rbac_r1_auth.py apps/api/tests/test_rbac_r1c_admin_gates.py -q
27 passed in 9.91s

apps/api/.venv/Scripts/python.exe -m pytest <all tests/test_cpor*.py + tests/test_shipment_evidence_*.py minus the 5 skipped below> tests/test_rbac_n0038_cpor_roles.py tests/test_rbac_r1c_admin_gates.py tests/test_auth_password_roles.py -q
255 passed in 26.77s

apps/api/.venv/Scripts/python.exe -m pytest apps/api/tests/test_session_gate.py apps/api/tests/test_promo_plan_builder.py -q
11 passed in 15.21s
```

Skipped (and why):
- `test_cpor_cases_api.py`, `test_cpor_historical_unit_c.py`, `test_shipment_evidence_observations.py`, `test_shipment_evidence_orphan_purge.py` — in conftest `_WRITE_CAPABLE_TEST_MODULES`; settings resolve to `cip`, so the guard would refuse them and they must not run against cip. Static check: they send only `X-User-Id` (no role) → stub forges ADMIN → unaffected by the new gates.
- `test_cpor_settle_confirm_clone.py` — writes to a clone DB (`cip_ns4_settle_clone`) and runs Alembic; the node does not authorise clone writes. It was collected once in the first run and **errored in setup** (`alembic.ini` not found from repo root) before any write; excluded from the recorded run. Uses `X-User-Id` only → ADMIN → unaffected.
- `test_rbac_r1d_session_e2e.py` — write-capable (creates app_user rows); not run. Its assertions (viewer 403 on shipment-evidence, admin 200) still hold under the new sets by construction.

No ruff in the API venv (`No module named ruff`); modules import cleanly under pytest. The only unused import introduced (`get_current_user` in cpor_exports.py) was removed.

## Criterion 5 — stub mode

`cip_auth_mode` defaults to `"stub"` (`app/core/config.py:106`). In stub mode with no header, `get_current_user` resolves `admin@local` (security.py:73-76), otherwise forges `normalize_role(x_user_role or "admin")` (security.py:137-143). Read-only on cip:
```
current_database() = cip
admin@local | admin | True
viewer@local | viewer | True
```
`require_roles` admits ADMIN unconditionally (security.py:182), so local dev in stub mode is unaffected. (A stub request that sends `X-User-Id: viewer@local` now gets 403 on writes — intended.)

## Criterion 6 — web findings (no web change made)

Searched `apps/web/src` for `useCurrentUser` / `roleMayAccess` / `.role`. Role gating in the web is **navigation only** (`features/shell/navConfig.ts` leaf `roles`, `roleMayAccess`); none of the CPOR / settlement / funding components (`features/cpor/*`, `features/settlement/*`, `features/promotions-funding/*`, `app/(app)/commercial-planner/cpor-cases/**`, `app/(app)/promotions/*`) read the user's role, and `src/middleware.ts` has no role logic. So any role that reaches a page by URL sees every write control.

- **W1 (mismatch, planner):** "Plan templates" leaf → `/commercial-planner/cpor-cases/historical-import` is `PLANNER_PLUS` (navConfig.ts ~l.239). The API now refuses planner on all historical-import writes (admin only). A planner sees map / validate / apply / resolution-plan controls and gets 403. Resolves with Q1.
- **W2 (mismatch, viewer/steward by URL):** Case book, settlement desk (`SettlementDesk*`, `SettlementConfirmDialog`), `CporCaseWorkspace`, `CporCaseSupersedeDialog`, `CporExportsPanel`, `CporFxAnchorPanel`, promotion planner (`PromoPlanBuilderPanel`) render transition / settle / supersede / export / FX / line-edit / create-case controls with no role check. Nav hides these leaves from viewer and steward (`PLANNER_PLUS`), but a direct URL or the "settle-case" start verb (`features/overview/startWork.ts:75`, filtered by role) shows controls the API refuses for viewer and steward.
- **W3 (mismatch, viewer/steward by URL):** Payment-evidence import page (`payment-evidence-import/page.tsx`) and `CporPaymentEvidencePanel` — viewer sees map/mark-shell/re-resolve/apply controls; API refuses viewer.
- **W4 (inverse, not a refusal):** "Payments" leaf is `PLANNER_PLUS`, so stewards do not see it in nav although the API now allows steward on payment-evidence writes. "Case book" etc. are hidden from viewer although the API lets viewer read. Nav is narrower than the API.
- **W5 (now aligned):** "Receipts & POD" → `/admin/shipment-evidence` is `STEWARD_PLUS` in nav; before this change stewards saw it and got 403; now the API admits steward. Planner/viewer neither see it nor pass the API.

Suggested follow-up (web node): a small `useRoleMay(['planner'])` guard around CPOR write controls using the existing `useCurrentUser` + `roleMayAccess`, mirroring this matrix.

## Other findings (not changed — outside this node's scope)

- **F1 (security, high):** three shipment-evidence steward **writes** have no role gate at all, only the router-level sign-in: `POST …/import-jobs/{job_id}/shipment-steward-bulk-preview`, `…/shipment-steward-bulk-apply`, `…/shipment-steward-bulk-ignore/apply-async` (shipment_evidence.py ~l.1045, 1112, 1230). Any signed-in viewer can bulk-apply / bulk-ignore steward mappings. They were never in the R1c ADMIN set, and BACKLOG-141 says change the allowed set "on those routes only", so I left them. Recommend `require_roles(Role.ADMIN, Role.STEWARD)` in a follow-up (one line each; BACKLOG-136 R3 sweep).
- **F2:** the upload that creates CPOR historical-import / payment-evidence jobs is the generic `imports.py` upload (not a CPOR route), which is sign-in only. A viewer can upload a job but cannot validate/apply it.
- **F3:** BACKLOG-136 KAM / PM / Ken / Wayne separation (PM pre-approval only, Ken must not touch MAC/terms, Wayne re-approves) is **not** expressible on four roles: planner can now do all lifecycle actions including approve and settle. Recorded as Q3.
- **F4:** `test_rbac_r1c_admin_gates.py` docstring/constant name (`_SWEPT_REQUIRE_ADMIN`) still says "admin"; the test checks presence of `require_roles`, not the set, so it passes. The exact set is now asserted in the N-0038 test. Cosmetic, not changed.
- BACKLOG-136 / BACKLOG-141 rows in `docs/BACKLOG.md` not updated (the orchestrator owns status changes).

## Questions for Warren (plain language; each is gated with a default so nothing is left open)

- **Q1 — Who may run the historical plan import (“Plan templates”)?** Before sign-in was added, only admins could. The backlog says the new check must be at least as strict, so today **only admins** can map / validate / apply historical plan files; everyone signed in can still view them. The menu shows this page to planners, so planners will now get "not allowed". Options: (a) keep admin only; (b) admin + steward; (c) admin + steward + planner (the default I was given). Changing it is one line in `cpor_historical_import.py`.
- **Q2 — Who may upload claim evidence and re-run the settlement roll-up on a case?** Default used: planner + admin (treated as settlement work). Options: add steward (it is a file import), or keep.
- **Q3 — KAM / PM / Ken / Wayne.** With only four roles, a planner can now propose, approve, settle and export. Do you want (a) that for now, (b) approve/settle limited to admin until finer roles exist, or (c) new roles later (a separate decision)? Default used: (a).
- **Q4 — Promo-plan "recompute" only calculates a draft (it saves nothing).** It is gated planner + admin with the other CPOR posts. Should viewers be allowed to use the planning calculator? Default: no.

## Blocked / grants

None. No cip writes (only one read-only SELECT via `ro_sql.py`). No merge, mint or bulk-promote. API not restarted.

## Evidence files

- `.eif/audit/PROGRAMME_20260924/n0038/IMPL.md` (this file)
- `.eif/audit/PROGRAMME_20260924/n0038/gate_routes.py` (edit helper, run once)
- `.eif/audit/PROGRAMME_20260924/n0038/route_table.py` + `route_table.txt` (route/role table from the mounted app)
