# N-0068 Multi-catalogue column sets (BACKLOG-198) - implementation run

Run: RUN-20261009-N0068-IMPL (2026-10-09). Lenses: backend-engineer (owner), database-specialist, test-engineering-specialist.
Decision applied: D-0060 (keep multiple catalogues; catalog_product stays; per-line column maps overlay
`source_definition.column_mapping_memory.mapping_profile.by_product_line`; `tenant_column_grain` holds one row per
business; duplicate EAN stays a FLAG, no unique index; sellable grain = every `dim_product.product_line`).
Status: node at stage `validate`, lease released. Not verified (GOV-008 is a later, different run).

Session note: the first session (07:11Z-07:35Z) did discovery, design and implementation and wrote the tests, then
was cut off by a usage limit before the cip_test DB test. A second session (11:45Z onward) ran the tests, added the
admin-only UI test, re-probed cip read-only and wrote this file.

## Discovery (AS-IS before this run)

- Committed in b1696b02: per-line PM maps under `mapping_profile.by_product_line`; the PM job state offers sellable
  product-line chips; validate flags duplicate EAN on `import_job.staged_metadata` (FLAG, not BLOCK).
- Dirty tree before this run (from N-0065/N-0068 work): `tenant_column_grain` table (untracked migration
  `apps/api/alembic/versions/20261006_0024_product_line_access.py`, PK `tenant_id`, `grain` default `product_line`,
  not blank), `TenantColumnGrain` model (`apps/api/app/models/product_line_access.py`), admin-only
  GET/PUT `/api/v1/auth/column-grain` (`apps/api/app/api/v1/endpoints/auth.py`), grain panel in
  `apps/web/src/features/administration/UsersWorkspace.tsx`, and the save path writing `by_grain` for non-product_line grains.
- Gaps found:
  - G1: suggestions always read `by_product_line`, while a save under another grain wrote `by_grain`, so read and write disagreed.
  - G2: PUT mapping accepted any `product_line` string as a memory key, not only a sellable `dim_product.product_line`.
  - G3: the grain was free text that becomes a JSON key.
  - G4: no tests for the grain, the column-grain endpoints, the admin-only UI or the no-unique-EAN rule.

## Changes (this run, no migration, no cip writes)

| File | Change |
|---|---|
| `apps/api/app/services/imports/pm_mapping_memory.py` | `DEFAULT_COLUMN_GRAIN = "product_line"`; `tenant_column_grain_sync(db, tenant_id)` (PK get, blank or missing row means product_line); `load_by_header_norm(..., grain=)` reads `by_product_line` or `by_grain.<grain>`; `merge_memory_from_pm_save(..., grain=)` writes the same axis. |
| `apps/api/app/services/imports/product_master_workflow.py` | `suggest_mapping_decisions(..., *, grain=)` passes the grain to the loader (G1); `save_mapping_sync` resolves the job tenant's grain through the helper. |
| `apps/api/app/api/v1/endpoints/imports_product_master.py` | State endpoint resolves the tenant grain, suggests on it and returns `column_grain`; PUT mapping strips `product_line` and, under the product_line grain, requires a sellable line (one forced refresh of `list_sellable_product_lines`), else 400 "Unknown product line" (G2). Both routes stay `require_roles(Role.ADMIN)`. |
| `apps/api/app/api/v1/endpoints/auth.py` | `ColumnGrainBody` validator: lowercases and requires `[a-z][a-z0-9_]{0,63}` (G3). |
| `apps/api/tests/test_column_grain_n0068.py` (new) | 24 unit tests (no DB). |
| `apps/api/tests/test_column_grain_n0068_db.py` (new) | 4 cip_test-only DB tests in one rolled-back transaction. |
| `apps/api/tests/conftest.py` | `test_column_grain_n0068_db.py` added to `_WRITE_CAPABLE_TEST_MODULES`, so the conftest refuses it on cip (it is not on `_CIP_WRITE_ALLOWLIST`). |
| `apps/web/src/features/administration/UsersWorkspace.columnGrain.test.tsx` (new, this session) | 5 vitest cases for the admin-only grain panel. |

Untouched: `catalog_product` / `product_catalog` code and data, `dim_product` indexes, alembic, `app/db/session*.py`,
`product_line_scope.py`, `features/reports/**`, workbench-ui charts/HeadlineFigure, the web proxy route, imports.py RBAC lines.
The `git diff` of the three service/endpoint files contains no `catalog_product` or index change.

## Validation evidence (2026-10-09, second session)

| Check | Command (from repo, bare or subshell) | Result |
|---|---|---|
| cip_test DB tests | `apps/api/.venv/Scripts/python.exe .eif/audit/PROGRAMME_20261009/n0068/run_db_tests.py` (PYTHONPATH=apps/api, run in apps/api) | Printed `DATABASE_URL db = cip_test`, `DATABASE_URL_SYNC db = cip_test`, `current_database() = cip_test`, role `cip` super False bypassrls False, alembic `20261009_0027`. **4 passed** in 9.22s. |
| cip_test leftovers | `.eif/audit/PROGRAMME_20261009/n0068/cip_test_leftover_check.py` (read-only) | `current_database() = cip_test`; N0068 dim_product 0, tenant 0, import_job 0, sources with N0068 line keys 0. |
| API unit + touched areas | `pytest tests/test_column_grain_n0068.py tests/test_product_master_workflow.py tests/test_pm_mapper_commercial.py tests/test_rbac_r1c_admin_gates.py tests/test_pm_mapper_regression_full.py tests/test_po_management.py` | **77 passed** in 40.1s. |
| API adjacent (auth, PM) | `pytest tests/test_auth_password_roles.py tests/test_auth_tenant_commercial_profile_api.py tests/test_auth_login_throttle.py tests/test_pm_dataframe_sanitize.py tests/test_product_master_gap_resolve_b072.py tests/test_product_master_pipeline_retired.py tests/test_cpor_rbac_r1_auth.py` | **47 passed** in 102s. |
| Web grain panel | `npx vitest run .../UsersWorkspace.columnGrain.test.tsx` | **5 passed** (first attempt 4/5: test race where the loaded grain overwrote the edit; test fixed to wait for the load, no product change). |
| Web existing users page | `npx vitest run users/list/page` | 1 passed. |
| Typecheck | `npx tsc --noEmit` in apps/web | exit 0. |
| Lint (changed web files) | `ESLINT_USE_FLAT_CONFIG=false npx eslint UsersWorkspace.tsx UsersWorkspace.columnGrain.test.tsx` | exit 0. Plain `npx eslint` fails in this repo (ESLint 9 finds no flat config; config is `eslintConfig` in package.json), a pre-existing tooling gap. |
| cip read-only probe | `.eif/audit/PROGRAMME_20261009/n0068/cip_readonly_probe.py` (SET TRANSACTION READ ONLY, rollback) | `current_database() = cip` printed first; alembic `20261009_0026`; `tenant_column_grain` = `[('default','product_line')]`; no dim_product index mentions ean; only unique constraints `uq_dim_product_part_number`, `uq_dim_product_sku`; `catalog_product` 18157 rows, `product_catalog` 1 (same as baseline BLN-N0068); 56 duplicate EAN values; no source has a mapping_profile or by_grain overlay yet. |

### Acceptance points

- **EAN has no unique index; duplicates flag.** cip probe (no ean index, only part_number/sku unique) and cip_test DB
  test `test_dim_product_ean_has_no_unique_rule_and_duplicates_load` (no unique index on ean, no unique expression index
  mentioning ean, two rows with one EAN insert). The FLAG surfaces as `duplicate_ean_flag` / `duplicate_ean_count` on the
  PM job state (unit test `test_pm_state_suggests_on_tenant_grain_and_reports_it`).
- **catalog_product untouched.** No code diff touches it; cip row counts equal the baseline; DB test `test_catalog_product_is_kept`.
- **Per-line map applied for the right line.** DB test `test_pm_mapping_save_lands_on_the_line_and_reads_back`: a real
  `save_mapping_sync` for line MB on the real Product Master `source_definition` lands under
  `mapping_profile.by_product_line.MB`, not NB, and the next `suggest_mapping_decisions` for MB returns the learned target.
  The admin imports page passes `product_line` to the state GET and the mapping PUT, so the job's saved mapping (used by
  validate/commit) starts from that line's set. Unit tests cover the read/write axis (G1), sellable-line check (G2),
  grain validation (G3).
- **Admin-only.** API: column-grain GET/PUT return 403 for steward, planner and viewer (parametrised unit test);
  PM mapping PUT returns 403 for steward. UI: the grain panel renders only for admin; for steward/planner/viewer the
  workspace shows "Admin role required" and never calls `/auth/column-grain` (vitest).
- **Nothing written to cip.** cip was only read in a read-only transaction after printing `current_database()`.

## Open items and findings (not fixed in this run)

1. **Grain is free text in the UI.** The admin types a grain name; only `product_line` has any consumer meaning today
   (other grains write `by_grain.<name>` keyed by the same product-line value). A select with the supported grains would
   be safer. UX/content finding; not changed because D-0060 only names product_line.
2. **Copy says "super user"** in the grain panel, but the gate is the admin role. Content finding for the naming owner.
3. **No audit line when the grain changes.** PUT /auth/column-grain commits without a log or audit event. Observability gap.
4. **Not rendered.** No browser inspection of the grain panel or the PM line chips in this run (no restarts allowed;
   not attempted). Rendered, UX, a11y and content quality stay pending.
5. **ESLint 9 config gap** (above) means `pnpm lint` does not run as configured; out of scope.
6. Mixed dirty tree: many unrelated node changes share the working tree; N-0068 files are listed above.

## Ledger (RUN-20261009-N0068-IMPL)

First session: `node.lease.acquire` (seq 1829), `baseline.add` BLN-N0068 (1830), `node.baseline` (1831), `node.stage`
challenge (1832), design (1833), implement (1834). The lease expired at 09:11:38Z during the usage-limit gap.
Second session (actor gov-001, payloads in `.eif/audit/PROGRAMME_20261009/n0068/`):

| Seq | Event | Note |
|---|---|---|
| 1851 | `node.lease.acquire` (rev 7) | Re-acquired after the expired lease. |
| 1852-1858 | `evidence.add` x7 | This file, DB test, unit tests, vitest, pm_mapping_memory.py, imports_product_master.py, cip read-only probe. |
| 1859 | `node.quality` testing = pass | Self-verification; GOV-008 still required. |
| 1860-1864 | `node.quality` observability, ux, a11y, rendered, content = pending | With rationale (open items 1-4). |
| 1865 | `finding.defer` DOES_NOT_FIT | Open items 1-5. |
| 1866 | `node.stage` validate (rev 14) | Stage note summarises the evidence. |
| 1867 | `node.lease.release` (rev 15) | Lease released. |

`program.py verify`: `integrity_ok: true`; `gates_ok: false` only from acknowledged gate debt on N-0006, N-0013,
N-0014, N-0015 and N-0016, none on N-0068. No `node.verification` and no `complete` were recorded. Not committed.

Note: acceptance criterion 1 on the node ("Blocked on Warren's catalog_product grain decision (BACKLOG-198)") is out of
date since D-0060; it was left as is (changing criteria is the orchestrator's call).
