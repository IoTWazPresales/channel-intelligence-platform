# N-0065 GOV-008 verification, run RUN-20261007-N0065-VER (2026-10-07)

Node N-0065 (product-line access), class feature, R2, facets api and auth. The implementation run was RUN-20261007-N0065-IMPL.
Lenses: verification-controller (GOV-008), identity-access-specialist, security-skeptic.
Rule D-0056: every signed-in screen filters to the user's assigned product lines. Each line is Read or Read-and-edit. A non-admin with no assignment sees no product data. An admin sees all lines.

**Independence: R2.** A fresh-context subagent under a different `--run`, same model family (not a different model). I re-ran every claim below myself. I relied on the implementer's report only where this file says so.

## Verdict: FAILED

The admin bypass, the non-admin helper and the database functions work as claimed. The `*` and comma plant-false is closed. Admin status cannot be spoofed in session mode.

One finding blocks a pass. Many request handlers open their own sync `SessionLocal()` session. Nothing sets `cip.product_lines` on those sessions, so row security reads them as unset, which means open. I measured this on cip with a non-admin, no-assignment scope bound exactly as the router binds it. The async `get_db` session saw **0** products and **0** forecasts. A sync `SessionLocal()` in the same request context saw **18,177** products and **38,625** forecasts. So on those screens, a non-admin with no assignment sees all product data, and a read-only line can be written. This gap existed before this run (N-0065 did not create it). It still breaks D-0056 "every signed-in screen", which is criterion 1.

| # | Criterion / check | Verdict |
|---|---|---|
| C1 | User mapped to any subset of `dim_product.product_line`; enforcement per D-0056 (unmapped default, read vs write, which surfaces) | **FAILED**: correct on the async `get_db` path, fails open on sync `SessionLocal()` request paths |
| C2 | Nothing writes to cip; read-only SQL prints `current_database()` first | **VERIFIED_WITH_LIMITATIONS** |
| C3 | Tests green on touched areas, tsc exit 0, eslint clean on changed files | **VERIFIED_WITH_LIMITATIONS** |
| K1 | Admin detection uses the real role source and cannot be spoofed by a header or forged identity in session mode | **VERIFIED** |
| K2 | Unset scope only for workers | **FAILED**: same root cause as C1 |
| K3 | Plant-false: non-admin `*` or `A,B` grant row does not widen | **VERIFIED** |
| K4 | cip_test database test | **VERIFIED** (ran, 5 passed, cip_test unchanged afterwards) |
| K5 | Live: API healthy, unauthenticated `/auth/me` 401; cip `*` / `''` / one-line counts | **VERIFIED** |
| K6 | Administration users copy matches the rule | **VERIFIED_WITH_LIMITATIONS** (wording nit) |

## Evidence (re-executed by this run)

### K1: admin detection and spoofing (code review)
- `apps/api/app/api/v1/router.py:33-50`: `is_admin = user.get("role") == Role.ADMIN`. When true, the router skips the row lookup and `product_line_scope_for` returns `*` for read and edit. Non-admins get a row lookup and the helper. A non-numeric id leaves the scope unset.
- `apps/api/app/core/security.py:101-124`: with a bearer, the role comes only from the `app_user.role` row of the `AuthSession` (`normalize_role`). Lines 126-130: in session mode with no bearer the request gets 401 before the stub branch. The `X-User-Role` and `X-User-Id` headers are read only in the stub branch (lines 134-143), which cannot be reached in session mode. `Role` is a `str` enum, so a plain `"admin"` string also matches. `normalize_role` maps only `admin` to ADMIN.
- Live settings on this machine: `settings.cip_auth_mode = session` (printed by the probe). Session mode therefore offers no header or forged-identity route to `*`.
- Stub mode (local and pytest only): a forged numeric `X-User-Id` that matches no user, sent with `X-User-Role: admin`, gets `*`. A forged non-numeric id gets an unset scope, which is open. Stub mode is not a boundary, and that was already true before this run.
- `sql_viewer` (`/admin/sql-viewer/execute`) is `require_roles(Role.ADMIN)`. A user who can run SQL could call `set_config('cip.product_lines','*')`, or (as the table owner) disable RLS. Only admins can run SQL there, and admins see all lines anyway. Note: role `cip` owns `dim_product` (measured), so FORCE RLS is the only thing that applies the policies to it.
- `apps/api/app/core/product_line_scope.py:30-51`: an admin gets `ALL_PRODUCT_LINES`. For a non-admin, a blank, `*` or comma-holding line is skipped, and the edit set is a subset of the read set.
- Migration `20261006_0024`, lines 57-120: `cip_product_line_visible/editable` return true when the setting is NULL (unset) or exactly `*`. Otherwise the line must be in the comma list. A `*` inside a list is a literal name, not a wildcard. `cip_product_id_visible/editable` are `SECURITY DEFINER` with `SET search_path = public` (no search-path hijack), and a NULL product id is visible. Lines 132-196: policies on `dim_product` and on every base table that has an integer `product_id` or `canonical_product_id` column. Live count: 45 tables with `cip_pl_select`.
- All 395 dependency uses are `Depends(get_db)`, so FastAPI's per-request cache gives the endpoint the same session the router scoped. The settings are transaction-local (`set_config(..., true)`), so they cannot leak through the pooled sync engine to another request.

### C1 / K2: blocking finding, sync request-path sessions fail open
- Code: `apps/api/app/db/session_sync.py:53`: `SessionLocal = sessionmaker(...)`. There is no event hook, and nothing in `apps/api/app` calls `set_config` except `product_line_scope.py`. A grep found that `get_db` is the only place the scope is applied.
- Request handlers that open `SessionLocal()` directly (count of call sites per file): imports 38, cpor_cases 31, shipment_evidence 24, cst_steward 15, cpor_historical_import 15, listing_capture 12, promo_exports 9, imports_product_master 8, cpor_fx 5, mappings 4, forecasts 4, product_master_gaps 3, customers 3, cpor_exports 3, commercial_planner_lineup_routes 3, distributors 2, cpor_payment_evidence 1, channel_intelligence 1. Also `app/query/handlers/a2_cpor.py`.
- Concrete screen: `GET /api/v1/forecasts/rollups?group_by=product` (`apps/api/app/api/v1/endpoints/forecasts.py:283-314`) has no role gate beyond sign-in and reads `fact_demand_forecast` through `SessionLocal()`.
- Behavioural proof, live on cip, read-only. Script: `.eif/audit/PROGRAMME_20261007/N0065_ver_sync_path_probe.py`. It binds `request_product_lines` and `request_editable_product_lines` the way the router does for a non-admin with no rows, then opens both sessions in that context:
  ```
  [async get_db] current_database() = cip   cip.product_lines = ''    dim_product = 0      fact_demand_forecast = 0
  [sync SessionLocal] current_database() = cip   cip.product_lines = None  dim_product = 18177  fact_demand_forecast = 38625
  ```
- Effect: on the sync screens, a viewer, planner or steward with no assignment sees every product line, and a read-only line is writable (the edit gate is also unset). D-0056 is not met on those screens.
- Recommendation (not implemented; for a follow-up node): apply the scope at transaction start for every ORM session, not only in `get_db`. One option is a SQLAlchemy `Session` `after_begin` listener that reads the two contextvars and calls `set_config(..., true)` when they are set. That would cover the sync `SessionLocal()` paths, and it would also fix implementer open item 2 (after a commit the scope reads `''`, so an admin who reads after committing sees nothing). Workers keep an unset scope because their contextvars are None. Add a regression test that opens `SessionLocal()` under a bound empty scope and expects 0 rows.

### K3: plant-false
- Unit test `test_non_admin_star_or_comma_row_never_widens_scope` passes.
- **My mutation 1** (`N0065_ver_mutate.py apply star`): changed the helper guard to `if not line:`, so `*` and comma rows are accepted again. Result: **1 failed** (`test_non_admin_star_or_comma_row_never_widens_scope`), 10 passed. Restored.
- **My mutation 2** (`apply alladmin`): changed `is_admin = True` in the router, so every numeric user is treated as admin. Result: **2 failed** (`test_dependency_non_admin_without_rows_binds_empty`, `test_dependency_non_admin_read_only_line_is_not_editable`). Restored.
- Restore proof: `product_line_scope.py` (untracked, so `git diff` shows nothing for it) sha256 `6a8a104f...` before and after. `router.py` sha256 `0c5622bb...` before and after. The `git diff` of both files hashes to `a3b3ac24...` before and after, and `git status` is unchanged (`M router.py`, `?? product_line_scope.py`). The API does not run with `--reload` (`scripts/cip-supervisor.ps1:581`), so the running API never loaded the mutations.
- Live, through the real helper, on cip (`N0065_ver_live_probe.py`):
  - non-admin row `*`: bound read `''`, edit `''`: count 0, editable 0
  - non-admin row `AZ,AX`: bound `''` / `''`: count 0, editable 0
  - non-admin rows `*` + `AZ` (read only): bound `'AZ'` / `''`: count 1, editable 0
  - contrast: a raw setting of `AZ,AX` (what an unfiltered row would bind) gives count 4 = 1 + 3. The filter is what stops the split.
- Grant table on cip: 0 rows, and 0 rows that are `*` or hold a comma. The PUT route still accepts such strings (implementer open item 3, still open). It is admin-only.

### K4: cip_test database test
- `tests/test_product_line_rls_n0065_db.py` **ran: 5 passed**. I ran it through `N0065_run_db_tests.py`, which swaps in the cip_test URL in-process and asserts the name. It printed `current_database() = cip_test` and `role = cip super = False bypassrls = False`. I read the helper first: it asserts cip_test and prints no credentials.
- The test applies migration 0024 and inserts fixtures inside a single transaction that is always rolled back. Read-only check afterwards (`N0065_ver_cip_test_state.py`): cip_test alembic `20260924_0023`, 0 `cip_product_%` functions, `dim_product` RLS off, 15 products, 0 `N0065-%` SKUs. cip_test is unchanged.
- In the default configuration (settings name cip), conftest lists the module in `_WRITE_CAPABLE_TEST_MODULES` (`apps/api/tests/conftest.py:97`), so it is refused there. I did not re-run that refusal. I relied on the implementer for the "5 errors" result.

### K5: live, read-only
- `scripts/cip-supervisor-status.ps1 -Local` at 16:19:48: api `healthy` pid 40976 `/health 200`; `local api /auth/me=401`, `web proxy /auth/me=401`; tunnel public `/login 200`, `/auth/me 401`. No restart was done by this run.
- cip probe (`N0065_ver_live_probe.py`, run from `apps/api` with the venv, psycopg driver, a single `READ ONLY` transaction rolled back, `current_database() = cip` printed first and asserted, `transaction_read_only = on`):
  - role `cip`, super False, bypassrls False; alembic `20261006_0024`; `dim_product` RLS True, FORCE True; 4 functions; 45 policy tables
  - setting before any set: None. Unset: **18,177** products. `*`: **18,177**. `''`: **0**
  - one real line `AZ` (1 product under `*`): count **1**, rows of any other line **0**, editable under read-only **0**
  - admin through the helper (`*`/`*`): 18,177
  - product-keyed table `catalog_product`: `*` gives 18,157, `''` gives 0
  - 14 non-null lines and 10 products with a NULL line (those are visible only to `*` and unset). app_user roles: 1 admin, 1 viewer. No identities printed.
- Not done: a signed-in browse as admin or non-admin, which would need a credential. I could not confirm that the live API process loaded the N-0065 code. The file mtimes were overwritten by my mutate/restore, and the API log directory is outside the repo, so the hook blocked it. I rely on the implementer's 15:47 restart record for that point.

### C3: tests and builds (re-run by me)
- `tests/test_product_line_scope_n0065.py`: **11 passed**.
- That file plus shipment_sheet_selection, inbound_lineup_quarter, bu_code_literal_guard and the 8 auth/RBAC neighbours (admin_overview, auth_login_throttle, auth_password_roles, auth_tenant_commercial_profile_api, cpor_rbac_r1_auth, rbac_n0038_cpor_roles, rbac_r1c_admin_gates, tenant_scope): **81 passed** (= implementer's 29 + 52, with the 11 counted once).
- cip_test database tests: 5 passed (K4).
- `pnpm --filter @cip/web exec tsc --noEmit`: **exit 0**.
- `ESLINT_USE_FLAT_CONFIG=false pnpm --filter @cip/web exec eslint <abs>/apps/web/src/features/administration/UsersWorkspace.tsx`: **exit 0** (only the eslintrc deprecation warning).
- vitest `apps/web/src/app/(app)/admin/users/list/page.test.tsx`: **1 passed**.
- Limitations: `tests/test_cpor_line_window_n0050.py::test_migration_follows_0022_single_head` **fails**, because it asserts the head is 0023 and migration 0024 now exists (implementer open item 1). It was not caused by this run's diff, but it sits in the product-line migration area. ruff is not installed in the venv. `test_rbac_r1d_session_e2e.py` did not run, because cip_test is not at 0024.

### C2: no cip writes
- Every SQL this run sent to cip was in a `READ ONLY` transaction, printed `current_database()` first and asserted the name. I did no restart and no git add or commit. The temporary source mutations were restored byte-for-byte (K3).
- For the implementation run I checked only that the cip state is consistent with no writes (0 grant rows; RLS state matches what migration 0024 creates). I cannot independently prove from here that the implementation run issued no writes, so I rely on its report.

### K6: Administration users copy
- `apps/web/src/features/administration/UsersWorkspace.tsx:322`: "Each person sees only the product lines assigned here. Read shows the data. Edit allows changes. Someone with no lines sees no product data. Admins see and edit every product line without an assignment." Lines 341-345: when the selected user's role is `admin` (lines 83-89), the page adds "This person is an admin and sees every product line. Lines saved here apply only if their role changes." The old copy saying an admin with no lines sees no product data is gone (grep across `apps` found 0 hits). Still four roles; options are No access / Read / Read and edit.
- Nit: "Someone with no lines sees no product data" is true only for non-admins. The next sentence clears that up, but "Anyone other than an admin with no lines..." would be exact. Because of the C1 finding, "Each person sees only the product lines assigned here" is currently not true on the sync screens.

## Residual risks and open items
1. **Blocking:** the scope fails open on sync `SessionLocal()` request paths (C1/K2). Needs a fix node, plus a regression test.
2. After a commit, the scope reads `''` within the same request, so it fails closed: an admin who reads after committing sees nothing (implementer item 2, still open). The same fix as item 1 would address it.
3. The PUT product-lines route accepts `*` and comma strings. They are harmless because the helper ignores them, but the route should return 400 (implementer item 3).
4. The single-head migration test fails with 0024 present. cip_test is not at 0024 (implementer item 1).
5. Products with a NULL `product_line` (10 on cip) are hidden from every non-admin. That is consistent with "only assigned lines", but nobody can assign them. Worth a domain note.
6. Admin is now the high-value role, so compromising one admin session exposes every line. This is the residual D-0056 accepts.

## Files written by this run (audit only, no product source)
- `.eif/audit/PROGRAMME_20261007/N0065_VERIFY.md` (this file)
- `.eif/audit/PROGRAMME_20261007/N0065_ver_mutate.py` (temporary-mutation tool; its backups were removed on restore)
- `.eif/audit/PROGRAMME_20261007/N0065_ver_live_probe.py`, `N0065_ver_sync_path_probe.py`, `N0065_ver_cip_test_state.py` (read-only probes)
- Ledger payloads `N0065_ver_*.json`

## Ledger (run RUN-20261007-N0065-VER)

| Event | Payload | Node rev | Programme rev |
|---|---|---|---|
| node.verification behavioral, state **fail** | `N0065_ver_behavioral.json` | 15 -> 16 | 1652 |
| node.verification referent, state pass, path `apps/api/app/api/v1/router.py` | `N0065_ver_referent.json` | 16 -> 17 | 1655 (the first send got `RUNTIME_INTEGRITY: Permission denied`, probably a concurrent writer; the retry was accepted) |
| node.stage -> verify, stage_note gives the FAILED verdict | `N0065_ver_stage_verify.json` | 17 -> 18 | 1656 |

No lease was needed (the node had none). No completion was set. The behavioral fail should route N-0065 back for the sync-session fix, or to a new node that the orchestrator decides on.

---

# Re-verification on cip (rounds 2-3, 0025)

Run RUN-20261008-N0065-VER2, 2026-10-08, about 21:30 to 22:10. Implementation run: RUN-20261007-N0065-IMPL (rounds 2 and 3). Migration 20261007_0025 was applied to cip at 21:17 (`N0065_r3_apply_cip_output.txt`).
Lenses: verification-controller (GOV-008), security-skeptic, identity-access-specialist, performance-engineer.

**Independence: R2.** This is a fresh-context subagent under a different `--run`, from the same model family (not a different model). I re-ran every number below myself. I quote the apply output only where I say so.

**Safety.** Every cip statement ran in a READ ONLY transaction, with `transaction_read_only = on` asserted or set through `default_transaction_read_only=on`, and with `statement_timeout` at 60 s. Each script printed `current_database() = cip` first. The only COMMITs were of read-only transactions; they leave a pooled backend in its after-commit state for check S2. I ran no ANALYZE and no DDL. I did no restart and no git add or commit. The one temporary source mutation was restored byte-for-byte.

## Verdict: FAILED (narrow). The D-0056 core passes on both session paths. The view does not.

The blocking finding from the first verification (C1/K2: sync `SessionLocal()` sessions failing open) is **closed** on cip. One new finding blocks a pass. Through `shipment_evidence_current`, a user with no lines or one line still sees evidence rows of other lines' shipments (S3/F1). Exposure is much smaller than before 0025: a user with no lines saw 15,807 rows, and now sees 2,532. It is still not D-0056.

### Security correctness

| # | Check | Verdict |
|---|---|---|
| S1 | D-0056 on cip under 0025, async `get_db` and sync `SessionLocal`: no lines gives 0; admin `*` gives all; one line gives only that line; a read-only line is not editable | **VERIFIED** |
| S2 | Leftover `''` on a pooled backend is open only for unscoped workers, and a scoped request always sets its own value | **VERIFIED** (one stated residual) |
| S3 | `shipment_evidence_current` respects row security (counts per scope) | **FAILED**: row security applies, but the per-scope counts are not "NULL product + own lines" (F1) |
| S4 | N-0065 suites and cip_test DB tests re-run; own mutation caught and reverted | **VERIFIED** |
| S5 | Live API runs the round-3 code | **VERIFIED_WITH_LIMITATIONS** |

### Performance (reported separately)

| # | Check | Verdict |
|---|---|---|
| P1 | 0025 inline predicate used (hashed subplan, short-circuit) | **VERIFIED** |
| P2 | Brief signals and cover distribution are faster after 0025 | **VERIFIED_WITH_LIMITATIONS**: about 2x faster than before 0025 when re-measured. The apply-time timings do not reproduce. The predicted ~0.2 s was not reached, because the time left is in the query, not in row security. |
| P3 | Stale planner statistics as the cause | **NOT the cause for these two paths**. Some tables do lack statistics (see P3). |

## S1: D-0056 on both session paths (`N0065_ver2_scope_probe.py`, output `N0065_ver2_scope_probe_output.txt`)

**Catalogue state on cip:**
- alembic `20261007_0025`; role `cip`, super False, bypassrls False; settings `cip_auth_mode = session`.
- `cip_product_line_visible/editable` are STABLE with no SECURITY DEFINER.
- The view has `security_invoker=true`.
- Policies: the inline 0025 form on 44 tables for SELECT, UPDATE and DELETE. `dim_product` keeps the line-function form. INSERT uses the line-function check on all 45 tables.
- Grant rows: 0.

**How the probe ran.** It drove the real router dependency `_bind_request_tenant` with the real `get_db` session:
- a non-admin viewer with a numeric id and no grant rows;
- an admin;
- a non-numeric id.

It then opened a real `SessionLocal()` through `asyncio.to_thread`, the same context hand-off FastAPI uses for sync handlers. That session ran one transaction, a read-only COMMIT, then a second transaction. One-line scopes went through `product_line_scope_for`, because there is no grant row to drive the lookup and I may not write one.

| Scope | Settings in the transaction | async get_db: dim_product / forecast | sync SessionLocal: dim_product / forecast | after commit | rows of other lines (NULL line included) | editable (function) |
|---|---|---|---|---|---|---|
| non-admin, no rows (router) | `'!'` / `'!'` | **0 / 0** | **0 / 0** | 0 | 0 | 0 |
| admin (router) | `'*'` / `'*'` | 18,177 / 38,625 | 18,177 / 38,625 | 18,177 | n/a | 18,177 |
| non-numeric id (router, unset) | None (async); `'*'` (sync, pooled rebind) | 18,177 | 18,177 | 18,177 | n/a | 18,177 |
| non-admin NB read-only (helper) | `'NB'` / `'!'` | n/a | 6,848 / 29,187 | 6,848 | **0** | **0** |
| non-admin NB read+edit (helper) | `'NB'` / `'NB'` | n/a | 6,848 / 29,187 | 6,848 | 0 | 6,848 |
| unscoped worker | `'*'` (pooled rebind) | n/a | 18,177 / 38,625 | 18,177 | n/a | 18,177 |

- 6,848 equals the owner-computed NB count in the apply output.
- The contextvars read None after the request in every case, so nothing leaks into the caller.

**Edit policy check on cip, EXPLAIN only (nothing executes), NB read-only:**
- `UPDATE dim_product` shows the read filter AND a second filter on `cip.editable_product_lines`.
- `UPDATE fact_sales_sellout` shows `product_id IS NULL OR coalesce(editable setting) IN ('','*') OR ANY(product_id = hashed SubPlan)` for the edit setting, and the read predicate on top.
- With the edit setting `'!'`, the line function returns false, so no row qualifies. The rolled-back UPDATE attempts ran only on cip_test (S4: the DB suite UPDATE changes 0 rows on the read-only line).

## S2: leftover `''` on a pooled backend (same probe; one pooled backend, pid 49756 throughout)

| Step on the same backend | Settings seen | dim_product |
|---|---|---|
| scoped NB request, then read-only COMMIT | `'NB'` / `'!'` | 6,848 |
| raw Core `sync_engine.connect()`, unscoped, no ORM listener | `''` / `''` | 18,177 (open) |
| unscoped worker `SessionLocal()` | `'*'` / `'*'` (listener rebind) | 18,177 |
| scoped non-admin, no rows | `'!'` / `'!'` | 0 |
| scoped NB again | `'NB'` / `'!'` | 6,848 |
| scoped admin | `'*'` / `'*'` | 18,177 |
| unscoped worker again | `'*'` / `'*'` | 18,177 |

So a leftover `''` is open only to unscoped code. Every scoped ORM transaction writes both settings, using `'!'` for "no lines".

**Residual:** a raw Core connection opened on a request path would also read the leftover `''` as open. A grep of `apps/api/app` finds only three such uses, and none is a non-admin data read:
- `sql_viewer` (`bind.connect()`, `require_roles(Role.ADMIN)`, so `*` anyway);
- the DDL-only view refresh (`admin_engine.connect()`);
- `sa_inspect(...).has_table` (catalogue only).

`widen_product_line_catalog` is reachable only from `GET /auth/product-lines` under `require_roles(Role.ADMIN)`.

## S3 / F1: `shipment_evidence_current` (`N0065_ver2_view_probe.py`, `_probe2.py`, `_probe3.py`, outputs `*_output.txt`)

- **Row security does apply.** Owner `postgres`, `security_invoker=true`. It reads `shipment_evidence_observation` and `shipment_evidence_line`, both under the inline policy. Under any line scope there are **0** rows with a non-null product id outside the scope. Unset, `''` and `'*'` all give 15,807, which is the total.
- **The per-scope counts are wrong.** Under `'*'` the view has 496 rows with a NULL product id. By line: NB 8,757, NR 3,258, NX 1,711, PF 608, PT 564, XB 265, NV 144, AI 4. The "NULL product + own lines" rule therefore expects the counts below.

| Scope | View rows | Expected (NULL + own lines) | Extra rows (not current under `'*'`, all with NULL product) | Line of the `'*'`-current row for those identities |
|---|---|---|---|---|
| `'!'` (no lines) | 2,532 | 496 | **2,036** | NB 1,064, NX 469, NR 291, PT 102, PF 83, NV 22, XB 5 |
| `'NB'` | 10,225 | 9,253 | **972** | NX 469, NR 291, PT 102, PF 83, NV 22, XB 5 |
| `'NB,NR'` | 13,192 | 12,511 | 681 | (not broken down) |
| `'AZ'` (no evidence) | 2,532 | 496 | 2,036 | as for `'!'` |

**Cause.** The view is `SELECT DISTINCT ON (o.line_identity_key) ... WHERE o.superseded_by_id IS NULL ORDER BY o.line_identity_key, o.valid_from DESC, o.id DESC`. There are 85,544 unsuperseded observations for 15,807 identities, so the supersession chain is not kept up. Under a narrow scope, row security hides an identity's newest observation, which resolves to another line's product. DISTINCT ON then picks an older observation of the same identity that has a NULL product id and is still visible. That stale row is returned as "current".

**What a no-lines user can read on those rows:** item_code, sales_model_name, quantity, amount, customer and distributor.

**Base tables, same root.** The "NULL product id is visible" rule has applied since 0024, so a no-lines user can also read the base tables directly:
- 5,876 NULL-product rows in `shipment_evidence_observation`, 4,133 of them for identities that resolve to a product elsewhere;
- 5,896 NULL-product rows in `shipment_evidence_line`.

**Reach.** `CIP_SHIPMENT_BITEMPORAL_READ` is on (default True, checked in-process). The shipment-evidence, channel-ops, plan-vs-executed, customer/distributor usage and lineup readers therefore read this view. I did not drive a signed-in screen, so whether a given screen drops NULL-product rows is UNKNOWN per screen.

**Not a regression in exposure.** Under 0024 the view returned all 15,807 rows under every scope, `'!'` included (the smoke output). 0025 closes the non-null-product part, but finding 3b is only partly closed.

**The parity test did not catch it.** Its fixture has no identity with several unsuperseded observations: view counts were 3 under `'*'` and 2 under `'!'`.

**Recommended fix (not implemented):**
1. Choose the current row before row security applies. For example, the invoker view filters `o.id IN (SELECT id FROM <a SECURITY DEFINER, search_path-pinned function or owner view that returns the DISTINCT ON ids over all rows>)`. A narrow scope then hides another line's current row and never shows its stale predecessor. Alternatively, keep `superseded_by_id` up to date so there is one unsuperseded observation per identity.
2. **Decision for Warren** (domain): is an unresolved evidence row (NULL product id, with an item code) "product data" under D-0056? If so, it should be visible only to `'*'` or to stewards, or it should inherit the line of its identity's resolved observation.
3. Add an identity with an older NULL-product observation to the parity fixture.

## S4: tests and own mutation

- **Round-3 file set on cip_test:** `N0065_ver2_run_cip_test.py`, the same 53 files as `N0065_r3_final_run.py` plus the DB module. Parity JSON went to my own `N0065_ver2_parity.json`. The runner printed `current_database() = cip_test` and `role = cip super = False bypassrls = False`.
  - Result: **466 passed** in 128 s (`N0065_ver2_cip_test_output.txt`).
  - Parity: 45 tables; 720 cells per version; mismatches 0 (0024) and 0 (0025). View counts: `'*'` 3, `'!'` 2.
- **My mutation** (`N0065_ver2_mutate.py`): `scope_csv(empty)` returns `''` instead of `'!'`, which is open under 0025. The N-0065 scope, listener and DB modules on cip_test gave **2 failed**, 31 passed:
  - `test_db_non_admin_with_no_rows_sees_no_products` failed with `assert 18 == 0`, which is the fail-open;
  - `test_non_admin_with_no_rows_sees_nothing` failed with `'' == '!'`.
  - Restored: sha256 `e62275a5...` before and after, byte-identical. `git status` for the file is unchanged (`??`).
  - Note: on the live listener path this mutation is partly masked, because `_scope_params` adds `or NO_PRODUCT_LINES`. That second guard is defence in depth. The tests that catch the mutation call `scope_csv` directly.
  - The API runs without `--reload`, so the running process never loaded the mutation.

## S5: live process

- Supervisor status at 21:47 (read only): api healthy pid 28016, the process the apply started at 21:16; worker pid 47680; tunnel healthy. `/auth/me` returns 401 on the local API, the web proxy and public.
- At 21:15:34, before the restart, the apply preflight asserted that the code on disk writes `'!'`.
- Limitations:
  - The mtime of `product_line_scope.py` is now 21:38, from my mutate/restore, which restored the same bytes. I could not hash the file as it was at 21:16.
  - No signed-in browse was done (no credential).

## P1-P3: performance (`N0065_ver2_explain.py`, `_capture.py`, `_stats.py`, `_rewrite.py`; outputs `N0065_ver2_explain_*.txt`, `N0065_ver2_cap_{a,b}.json`, `N0065_ver2_stats_output.txt`, `N0065_ver2_rewrite_output.txt`)

**P1: the inline predicate is used.**
- Every heavy statement's plan shows `product_id IS NULL OR coalesce(setting) = ANY('{"",*}') OR ANY(product_id = hashed SubPlan)`.
- Under unset and `'*'` the subplan reads **never executed** (short-circuit). Under NB it runs once: a seq scan of `dim_product`, 6,848 rows in 26 ms.
- No `cip_product_id_visible` appears in any plan.

**How much is row security.** I measured the predicate cost per row over the 194,349 product ids of `weeks_of_cover_observation`, best of 3:

| Setting | 0025 inline predicate | 0024 definer function (still installed, called directly) |
|---|---|---|
| `'*'` | +70 ms (0.36 µs/row) | +1,942 ms (9.99 µs/row) |
| NB | +166 ms (1.89 µs/row) | +1,927 ms (21.9 µs/row) |

So row security now costs 0.07-0.17 s of the cover scan, against about 1.9 s under 0024.

**P2: timings.**
- **Top statement** (the same one on both paths): `SELECT DISTINCT ON (distributor_id, product_id) <all 23 columns> FROM weeks_of_cover_observation WHERE tenant_id=... ORDER BY ..., cover_as_of_date DESC, CASE trigger, observed_at DESC`.
  - EXPLAIN (ANALYZE, BUFFERS) gives **1.59-1.92 s unset, 1.62 s `'*'`, 0.62 s NB**.
  - Inside that, the seq scan with the filter takes 0.25-0.33 s, and the external merge sort **spills 119 MB to disk** (work_mem 4 MB; 194,349 rows x 608 bytes) and takes about 1.1-1.3 s.
  - Under NB the sort spills 54 MB.
  - Estimates: rows=97,159 against 194,349 actual. That 2x is the default selectivity of the row-security OR; it does not change the plan.
  - JIT is not involved (cost 72k is below `jit_above_cost` 100k).
- **Second statements:** the inbound count is 0.28/0.36/0.14 s; the cover CTE statement is 0.27/0.18/0.19 s. Both show 1-row estimates on DISTINCT ON subqueries, but they run as hashed subplans or CTEs, so the cost is small.
- **Endpoint re-capture**, READ ONLY, `n0065_capture.py` unchanged, run twice (ms, unset / `'*'` / NB):

| Path | PERF (0024) | r3 at 0024 + fix 4 | Apply-time capture (0025, 21:17) | **VER2 capture a** | **VER2 capture b** |
|---|---|---|---|---|---|
| brief/signals | 5.0k / 5.7k / 2.4k | 4.8k / 3.5k / 3.3k | 8.3k / 7.4k / 4.6k | **2.5k / 2.6k / 1.2k** | **2.9k / 1.8k / 1.2k** |
| channel-ops/cover-distribution | 5.6k / 8.8k / 4.1k | 4.3k / 4.9k / 3.4k | 7.7k / 8.1k / 5.3k | **2.0k / 2.5k / 1.5k** | **2.1k / 2.4k / 1.4k** |
| top statement in capture | 3.5k / 5.2k / 2.9k (PERF stmt) | n/a | 4.7k / 5.0k / 2.3k | 1.4k / 1.9k / 0.5k | 1.2k / 1.2k / 0.6k |

- **Reading the table:** after 0025 both paths are about 2x faster than before 0025.
- **The apply-time slowdown does not reproduce.** The same statement, same plan, took 4.7 s at 21:17 and 1.2-1.9 s now. Cause UNKNOWN. The capture began 4 s after the API restart, while the pre-restart worker (pid 44720) was still running. Shared buffers are 128 MB, and the table is 244 MB, read from the OS cache. I have no evidence for which factor it was. It is not row security: P1 measures 0.07-0.17 s.
- **Why the expected gain was not reached:** the PERF study's "~80% RLS" overstated the share. Measured directly, 0024's row security on this scan was about 1.9 s of about 3.5 s. The remaining ~1.6 s is the wide sort, which N-0065 does not touch.

**P3: planner statistics** (pg_stat_user_tables, as role cip):
- **No statistics:** `dim_product`, `fact_sales_sellout`, `fact_inventory_distributor`, `fact_demand_forecast` and `fact_inventory_reconciliation` have `last_analyze` and `last_autoanalyze` NULL. `n_live_tup` is 0 while `reltuples` is 18,168 / 35,608 / 47,411 / 38,625 / 42, so the counters were reset or never collected. `n_mod_since_analyze` is 0-138, far below the autoanalyze threshold, so autoanalyze will not run.
  - The planner has no column statistics for `dim_product`: `tenant_id='default'` is estimated at **45 against 18,177** actual. The NB subplan is estimated at 4,542 against 6,848.
  - Note: `pg_stats` hides rows for tables with row security active, so a 0 there is not evidence.
- **Current statistics on the two hot tables:** `weeks_of_cover_observation` was autoanalyzed on 2026-09-14 with `n_mod_since_analyze = 0`. `fact_inbound_shipment` was autoanalyzed on 09-14 with 26 mods.
- **Conclusion:** stale statistics are **not** the cause on these two paths. The hot table's statistics are current, and the plan shape (seq scan plus full sort) does not depend on the `dim_product` estimates.

**What would deliver the gain** (measured READ ONLY with SET LOCAL on the top statement; nothing changed):

| Option | Statement time | Note |
|---|---|---|
| as is | 1.6-1.9 s unset, 0.6 s NB | sort spills 119 MB |
| `work_mem=256MB` | 0.95 s unset | quicksort in 127 MB of memory. Raising it per query or per role needs a code or config change |
| incremental sort on the existing index `ix_woc_observation_current (tenant_id, distributor_id, product_id, cover_as_of_date DESC)` (forced with `enable_sort=off`, diagnostic only) | **0.56 s** unset | the planner does not choose it at `random_page_cost=4` |
| `random_page_cost=1.1` | 0.83-1.04 s unset; 0.75-0.94 s NB (worse than 0.6) | not a clean global fix |
| narrow rewrite (DISTINCT ON over the ids, then fetch) | 1.36-1.48 s / 0.78 s NB, same ids | no gain as written |

- **Recommended** (a follow-up perf node, not N-0065): stop sorting 194k wide rows to keep 2,481. Options:
  - keep a current-observation flag or table for weeks of cover;
  - or rewrite to a per-(distributor, product) top-1 that uses `ix_woc_observation_current` (about 0.5 s is achievable on that index);
  - or set `work_mem` for this query.
- **ANALYZE** of `dim_product` and the four fact tables (a cip write, which needs Warren's approval) is still worth doing for other paths and for estimate quality. I expect **little gain on these two paths**. I did not run it.

## Residual risks and open items (this run)
1. **Blocking, F1:** `shipment_evidence_current` under a narrow scope returns stale NULL-product observations of identities whose current row is in another line. A no-lines user gets 2,036; an NB user gets 972. Base tables expose 5,876 / 5,896 NULL-product rows to a no-lines user. Needs the view fix and Warren's decision on NULL-product evidence rows (above).
2. Raw Core connections on request paths read the leftover `''` as open. Today they are admin-only or catalogue-only. A future non-admin raw `engine.connect()` would fail open. A grep or test guard would stop that recurring.
3. Still open from earlier rounds: scope for user-triggered background jobs (decision); PUT product-lines accepts `'*'`, `'!'` and comma values; no signed-in live browse.
4. Performance: the wide DISTINCT ON sort on `weeks_of_cover_observation` (about 1.6 s) dominates both paths; and five tables have no statistics (ANALYZE needs approval).

## Files written by this run (audit only, no product source)
- Probes, all READ ONLY: `N0065_ver2_scope_probe.py`, `N0065_ver2_view_probe.py`, `N0065_ver2_view_probe2.py`, `N0065_ver2_view_probe3.py`, `N0065_ver2_explain.py`, `N0065_ver2_capture.py`, `N0065_ver2_captop.py`, `N0065_ver2_stats.py`, `N0065_ver2_rewrite.py`.
- Runners and tools: `N0065_ver2_run_cip_test.py` (cip_test), `N0065_ver2_mutate.py` (temporary mutation, restored).
- Outputs: `N0065_ver2_*_output.txt`, `N0065_ver2_explain_*.txt`, `N0065_ver2_cap_a.json`, `N0065_ver2_cap_b.json`, `N0065_ver2_parity.json`.
- Ledger payloads: `N0065_ver2_*.json`.

## Ledger (run RUN-20261008-N0065-VER2)

| Event | Payload | Node rev | Programme rev |
|---|---|---|---|
| node.verification behavioral, state **fail** | `N0065_ver2_behavioral.json` | 34 -> 35 | 1804 |
| node.verification referent, state pass, path `apps/api/alembic/versions/20261007_0025_product_line_rls_inline.py` | `N0065_ver2_referent.json` | 35 -> 36 | 1805 |
| node.stage -> verify, stage_note gives the FAILED (narrow) verdict | `N0065_ver2_stage_verify.json` | 36 -> 37 | 1806 |

- No lease was needed (the node had none), and no completion was set.
- The first try passed `--run` after the subcommand and was rejected as a usage error. No event was written. It was re-sent with `--run` before `event`.
- The behavioral fail should route N-0065, or a child node, to the F1 view fix and Warren's decision on NULL-product evidence rows. Everything else in D-0056 passed on cip.
